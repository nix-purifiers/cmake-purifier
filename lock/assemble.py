# SPDX-License-Identifier: MIT
#
# Writes the lockfile from what the lock run recorded.
#
#   python3 -I assemble.py <work dir> <lock version> <lockfile> <nixpkgs>
#     <nix lib dir> <purifier> <git> <hg> <svn> <nix-prefetch-git> <definition hash>
#
# <nix lib dir> is the builder's runtime source tree, with its sibling CLI prefetch expression,
# and <purifier> the source of the shared library it fetches with.
# <definition hash> is the hash of the build definition, which
# pkgs/build-cmake-project/definition-hash.sh computes.
#
# <work dir> is the lock run's scratch directory, which holds:
#
# - observed.json, the record of the dependency provider: the top-level
#   project() and every FetchContent_MakeAvailable() dependency with its
#   declared download and its source directory.
# - http.jsonl, the record of the proxy (record.py), a line per response.
# - git.jsonl, hg.jsonl, svn.jsonl and cvs.jsonl, the records of the tool
#   wrappers, a line per command with its working directory and arguments.
# - flags.json, the configure arguments.
# - build/ and prefix/, the build directory and the install.
#
# records.py reads the records. This script adds what needs the checkouts
# or the network: every git checkout is hashed with nix-prefetch-git, and
# every Mercurial, Subversion and CVS checkout by building the fetcher of
# the sandbox build (pkgs/cmake-purifier/prefetch-vcs.nix).
#
# The outputs come from the install into prefix/: `files` is every file
# the install wrote (install_manifest.txt in build/), relative to prefix/.
# `targets` maps each installed target of the File API's code model in
# build/ to its type and the installed files of its artifacts. When the
# lock run did not build, there is no install and the lockfile records no
# outputs.
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
from typing import NoReturn

# python3 -I leaves the script's own directory out of the module path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import records
from urls import https_of, url_path

(
    work,
    lock_version,
    lockfile,
    nixpkgs,
    nixlib,
    purifier,
    git,
    hg,
    svn,
    prefetch,
    definition_hash,
    pins_file,
) = sys.argv[1:]
with open(pins_file) as f:
    pins = json.load(f)
prefetch_vcs = os.path.join(nixlib, "../cmake-purifier/prefetch-vcs.nix")
build_dir = os.path.join(work, "build")
prefix = os.path.join(work, "prefix")


def fail(message) -> NoReturn:
    print(f"cmake-purifier: {message}", file=sys.stderr)
    sys.exit(1)


def read_lines(name):
    path = os.path.join(work, name)
    if not os.path.exists(path):
        return []
    with open(path) as lines:
        return [json.loads(line) for line in lines if line.strip()]


def run(*command):
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout.strip()


def plain(text):
    """A path component of any text."""
    return re.sub(r"[^A-Za-z0-9+._=-]", "_", text).strip("_") or "_"


with open(os.path.join(work, "observed.json")) as f:
    observed = json.load(f)
with open(os.path.join(work, "flags.json")) as f:
    flags = json.load(f)

try:
    files = records.file_artifacts(read_lines("http.jsonl"))
    git_clones = records.git_clones(read_lines("git.jsonl"))
    hg_clones = records.hg_clones(read_lines("hg.jsonl"))
    svn_checkouts = records.svn_checkouts(read_lines("svn.jsonl"))
    cvs_checkouts = records.cvs_checkouts(read_lines("cvs.jsonl"), os.environ.get("CVSROOT", ""))
except records.RecordError as error:
    fail(str(error))

artifacts: dict[str, dict] = {}
by_dir: dict[str, dict] = {}


def vcs_artifact(artifact):
    """Adds the hash of a Mercurial, Subversion or CVS artifact, by
    building its fetcher with a wrong hash and reading the right one."""
    if artifact["path"] in artifacts:
        return artifacts[artifact["path"]]
    print(f"cmake-purifier: hashing {artifact['path']}", file=sys.stderr)
    result = subprocess.run(
        [
            "nix-build", "--no-out-link", prefetch_vcs,
            "--arg", "nixpkgs", nixpkgs,
            "--arg", "purifier", purifier,
            "--argstr", "artifact", json.dumps(artifact),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    found = re.search(r"got:\s+(sha256-[A-Za-z0-9+/=]+)", result.stderr)
    if found is None:
        fail(f"could not hash {artifact['path']}:\n{result.stderr}")
    artifact = {**artifact, "hash": found.group(1)}
    artifacts[artifact["path"]] = artifact
    return artifact


git_table: dict[tuple, dict] = {}
for directory, clone in git_clones.items():
    if not os.path.isdir(directory):
        fail(f"the lock run cloned {clone['url']} into {directory}, which no longer exists")
    rev = run(git, "-C", directory, "rev-parse", "HEAD")
    # The sandbox has no SSH credentials, so a repository cloned over SSH
    # is fetched from the HTTPS URL of the same host when that host serves
    # it there. The checkout keeps the SSH URL, which the shim matches.
    fetch_urls = [u for u in [https_of(clone["url"]), clone["url"]] if u]
    path = "/".join(["git", url_path(fetch_urls[0]), rev])
    if path not in artifacts:
        result = None
        for fetch_url in fetch_urls:
            print(f"cmake-purifier: hashing {fetch_url} at {rev}", file=sys.stderr)
            command_line = [prefetch, "--quiet", "--url", fetch_url, "--rev", rev]
            if clone["submodules"]:
                command_line.append("--fetch-submodules")
            result = subprocess.run(command_line, capture_output=True, text=True, check=False)
            if result.returncode == 0:
                break
        if result is None or result.returncode != 0:
            fail(f"could not fetch {clone['url']} at {rev}:\n{result.stderr if result else ''}")
        artifacts[path] = {
            "path": path,
            # The shim answers every command a build makes on a checkout,
            # so no checkout needs a real .git.
            "git": {
                "url": fetch_url,
                "rev": rev,
                "submodules": clone["submodules"],
                "leaveDotGit": False,
                "commitObject": None,
            },
            "hash": json.loads(result.stdout)["hash"],
        }
    by_dir[directory] = artifacts[path]
    ref = clone["ref"] or rev
    git_table[(clone["url"], ref)] = {"url": clone["url"], "ref": ref, "artifact": path}

hg_table: dict[tuple, dict] = {}
for directory, clone in hg_clones.items():
    node = run(hg, "--cwd", directory, "log", "-r", ".", "-T", "{node}")
    subrepos = os.path.exists(os.path.join(directory, ".hgsub"))
    artifact = vcs_artifact({
        "path": "/".join(["hg", url_path(clone["url"]), node]),
        "hg": {"url": clone["url"], "rev": node, "subrepos": subrepos},
    })
    by_dir[directory] = artifact
    hg_table[(clone["url"], clone["ref"])] = {
        "repo": clone["url"], "ref": clone["ref"], "artifact": artifact["path"],
    }

svn_table: dict[tuple, dict] = {}
for checkout in svn_checkouts:
    rev = int(run(svn, "info", "--show-item", "revision", checkout["dir"]))
    artifact = vcs_artifact({
        "path": "/".join(["svn", url_path(checkout["url"]), str(rev)]),
        # ExternalProject's `svn co` fetches externals and expands keywords.
        "svn": {"url": checkout["url"], "rev": rev, "ignoreExternals": False, "ignoreKeywords": False},
    })
    by_dir[checkout["dir"]] = artifact
    svn_table[(checkout["url"], checkout["ref"])] = {
        "repo": checkout["url"], "ref": checkout["ref"], "artifact": artifact["path"],
    }

# A CVS checkout without a tag or a date locks the date its pin names,
# which pin.py checked out, or else the time of the lock run.
lock_time = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
cvs_pins = {p["repo"]: p["rev"] for p in pins if p["tool"] == "cvs"}
cvs_table: dict[tuple, dict] = {}
for checkout in cvs_checkouts:
    tag = checkout["tag"]
    date = checkout["date"]
    root = checkout["root"]
    module = checkout["module"]
    if tag is None and date is None:
        date = cvs_pins.get(f"{root} {module}", lock_time)
    artifact = vcs_artifact({
        "path": "/".join(["cvs", plain(root), plain(module), plain(tag or date)]),
        "cvs": {"cvsRoot": root, "module": module, "tag": tag, "date": date},
    })
    by_dir[checkout["dir"]] = artifact
    repo = f"{root} {module}"
    cvs_table[(repo, checkout["ref"])] = {"repo": repo, "ref": checkout["ref"], "artifact": artifact["path"]}

# FetchContent_MakeAvailable() dependencies, from the provider's record.
dependencies: list[dict] = []
for dep in observed["dependencies"]:
    if dep["type"] == "url":
        # CMake tries the declared URLs in order and stops at the first
        # that works, so the proxy saw that one; the others are mirrors.
        urls = dep["urls"]
        fetched = [u for u in urls if u in files]
        if not fetched:
            fail(f"the lock run saw no download of {urls[0]} for dependency {dep['name']}")
        artifact = files[fetched[0]]
        artifact["mirrors"] = [u for u in urls if u != fetched[0]]
        dependency = {"name": dep["name"], "artifact": artifact["path"], "extract": dep["extract"]}
    else:
        source_dir = os.path.normpath(dep["sourceDir"])
        if source_dir not in by_dir:
            fail(f"the lock run saw no {dep['type']} checkout into {source_dir} for dependency {dep['name']}")
        dependency = {"name": dep["name"], "artifact": by_dir[source_dir]["path"]}
        # A GIT_SUBMODULES list: the checkout holds every submodule, and
        # the source of the dependency only the listed ones.
        if dep["type"] == "git" and dep.get("submodulePaths"):
            dependency["submodules"] = dep["submodulePaths"]
    # The download as the declaration names it, which the provider of a
    # build from the lockfile compares with the declaration it sees.
    dependency["declared"] = dep["declared"]
    dependencies.append(dependency)

# Outputs, from the install and the File API.
outputs = None
manifest = os.path.join(build_dir, "install_manifest.txt")
if os.path.isdir(prefix) and os.path.exists(manifest):
    root_dir = os.path.realpath(prefix)
    with open(manifest) as lines:
        installed = sorted(
            os.path.relpath(line.strip(), root_dir) for line in lines if line.strip()
        )
    installed_set = set(installed)
    installed_targets: dict[str, dict] = {}
    reply = os.path.join(build_dir, ".cmake", "api", "v1", "reply")
    indexes = sorted(f for f in os.listdir(reply) if f.startswith("index-"))
    if not indexes:
        fail(f"CMake wrote no File API reply in {reply}")
    with open(os.path.join(reply, indexes[-1])) as f:
        index = json.load(f)
    codemodel_file = next(
        o["jsonFile"] for o in index["objects"] if o["kind"] == "codemodel"
    )
    with open(os.path.join(reply, codemodel_file)) as f:
        codemodel = json.load(f)
    for target_ref in codemodel["configurations"][0]["targets"]:
        with open(os.path.join(reply, target_ref["jsonFile"])) as f:
            target = json.load(f)
        if "install" not in target:
            continue
        names = {os.path.basename(a["path"]) for a in target.get("artifacts", [])}
        target_files = sorted(
            os.path.join(d["path"], n)
            for d in target["install"]["destinations"]
            for n in names
            if os.path.join(d["path"], n) in installed_set
        )
        if target_files:
            installed_targets[target["name"]] = {"type": target["type"], "files": target_files}
    outputs = {"files": installed, "targets": installed_targets}


def by_repo_ref(table):
    return sorted(table.values(), key=lambda c: (c.get("url", c.get("repo")), c["ref"]))


def content_hash(document):
    """The hash of a lockfile without its contentHash: the SHA-256 of its
    JSON with sorted keys and no spaces, as Nix's builtins.toJSON writes
    it, so that lib-overlays/default/lock.nix can check it."""
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


lock = {
    "version": int(lock_version),
    "project": observed["project"],
    "definitionHash": definition_hash,
    "cmakeFlags": flags,
    "artifacts": sorted([*files.values(), *artifacts.values()], key=lambda a: a["path"]),
    "dependencies": sorted(dependencies, key=lambda d: d["name"]),
    "gitCheckouts": by_repo_ref(git_table),
    "hgCheckouts": by_repo_ref(hg_table),
    "svnCheckouts": by_repo_ref(svn_table),
    "cvsCheckouts": by_repo_ref(cvs_table),
    "outputs": outputs,
}
lock["contentHash"] = content_hash(lock)
with open(lockfile + ".tmp", "w") as out:
    json.dump(lock, out, indent=2)
    out.write("\n")
os.replace(lockfile + ".tmp", lockfile)
print(
    f"cmake-purifier: wrote {lockfile} with {len(files)} files and "
    f"{len(artifacts)} checkouts",
    file=sys.stderr,
)
