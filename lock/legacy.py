# SPDX-License-Identifier: MIT
"""Acquisition-only legacy profile. Native CMake owns the dependency build."""
import argparse
import base64
import hashlib
import json
import os
import re
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse

PROFILE = "legacy-external-v1"
VERSION = 4


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_hash(lock):
    return "sha256:" + hashlib.sha256(canonical({k: v for k, v in lock.items() if k != "contentHash"}).encode()).hexdigest()


def read_lock(path):
    from urls import url_path
    lock = json.loads(Path(path).read_text())
    expected = {"version", "nativeProfile", "sdk", "project", "definitionHash", "cmakeFlags", "artifacts", "outputs", "dependencyMetadataAvailable", "targetMetadataAvailable", "contentHash"}
    if set(lock) != expected or lock["version"] != VERSION or lock["nativeProfile"] != PROFILE:
        raise ValueError("not a legacy-external-v1 format4 lock")
    sdk, project = lock["sdk"], lock["project"]
    if (not isinstance(sdk, dict) or set(sdk) != {"moduleRoot", "package", "version", "source"}
            or not all(isinstance(sdk[key], str) and sdk[key] for key in ["package", "version"])
            or not isinstance(sdk["moduleRoot"], str)
            or re.fullmatch(r"[A-Za-z0-9_+-][A-Za-z0-9_.+-]*(/[A-Za-z0-9_+-][A-Za-z0-9_.+-]*)*", sdk["moduleRoot"]) is None
            or not isinstance(sdk["source"], dict) or set(sdk["source"]) != {"url", "sha256"}
            or not isinstance(sdk["source"]["url"], str)
            or not isinstance(sdk["source"]["sha256"], str)
            or len(sdk["source"]["sha256"]) != 64
            or any(char not in "0123456789abcdef" for char in sdk["source"]["sha256"])):
        raise ValueError("legacy lock has no valid native SDK source identity")
    if not isinstance(project, dict) or set(project) != {"name", "version"} or not isinstance(project["name"], str) or not project["name"] or project["version"] != "":
        raise ValueError("legacy project records its native name, with version metadata unavailable")
    if not isinstance(lock["cmakeFlags"], list) or not all(isinstance(flag, str) for flag in lock["cmakeFlags"]):
        raise ValueError("legacy configure definitions must be an argument list")
    checked_flags(lock["cmakeFlags"])
    if lock["contentHash"] != content_hash(lock):
        raise ValueError("legacy lock content hash differs; restore or explicitly relock")
    if lock["dependencyMetadataAvailable"] is not False or lock["targetMetadataAvailable"] is not False:
        raise ValueError("legacy acquisition profile has no named dependency or target metadata")
    if not isinstance(lock["artifacts"], list) or not lock["artifacts"]:
        raise ValueError("legacy capture has no observed HTTP acquisition")
    for entry in lock["artifacts"]:
        if not isinstance(entry, dict) or set(entry) != {"path", "url", "mirrors", "hash"} or entry["mirrors"] != [] or not all(isinstance(entry[key], str) for key in ["path", "url", "hash"]):
            raise ValueError("invalid legacy HTTP artifact")
        parts = urllib.parse.urlsplit(entry["url"])
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            raise ValueError("unsupported legacy acquisition URL")
        if entry["path"] != url_path(entry["url"]) or any(part in {".", ".."} for part in entry["path"].split("/")) or any(char in entry["path"] for char in "\n\r\t"):
            raise ValueError("legacy artifact path differs from its URL or escapes replay tree")
        if not entry["hash"].startswith("sha256-") or len(base64.b64decode(entry["hash"][7:], validate=True)) != 32:
            raise ValueError("legacy artifact needs an exact SHA256")
    if set(lock["outputs"]) != {"files"} or not isinstance(lock["outputs"]["files"], list):
        raise ValueError("legacy outputs contain installed files only")
    for name in lock["outputs"]["files"]:
        if not isinstance(name, str) or not name or name.startswith("/") or ".." in Path(name).parts or "\n" in name:
            raise ValueError("legacy installed path escapes the install prefix")
    return lock


def run(command, **kwargs):
    return subprocess.run(command, check=True, **kwargs)


def source_files(source):
    for directory, dirs, names in os.walk(source, followlinks=False):
        directory = Path(directory)
        dirs[:] = [name for name in dirs if name not in {".git", ".cmake-purifier"}
                   and not (directory / name).is_symlink()
                   and not (directory / name / "CMakeCache.txt").exists()]
        for name in names:
            path = directory / name
            if path.is_file() and not path.is_symlink():
                yield path


def definition_hash(config, source):
    # Mirror definition-hash.nix's source tree, including an untracked
    # project nested inside another checkout. Never inherit its git index.
    definitions = {}
    for path in source_files(source):
        if path.name == "CMakeLists.txt" or path.name.endswith((".cmake", ".cmake.in")):
            definitions[str(path.relative_to(source))] = hashlib.sha256(path.read_bytes()).hexdigest()
    body = "".join(definitions[name] + " " + name + "\n" for name in sorted(definitions))
    return hashlib.sha256(body.encode()).hexdigest()


def source_snapshot(source):
    return {str(path.relative_to(source)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in source_files(source)}


def identity(context, command, root, version, project, current_source, root_source, current_build, root_build):
    context = Path(context)
    config = json.loads(context.read_text())
    actual = str(Path("/proc", str(os.getppid()), "exe").resolve(strict=True))
    expected = config["sdk"]
    if (Path(current_source).resolve() != Path(root_source).resolve()
            or Path(current_build).resolve() != Path(root_build).resolve()
            or str(Path(root_source).resolve()) != config["sourceDirectory"]
            or str(Path(root_build).resolve()) != config["buildDirectory"]
            or Path(str(context) + ".identity").exists()):
        raise ValueError("legacy native startup hook must run once at the selected root")
    if (actual != str(Path(expected["package"], "bin/cmake").resolve())
            or str(Path(command).resolve()) != actual
            or str(Path(root).resolve()) != str(Path(expected["package"], expected["moduleRoot"]).resolve())
            or version != expected["version"] or project != config["projectName"]):
        raise ValueError("native executable/module root/version/project differs from the explicit source-owned SDK")
    Path(str(context) + ".identity").write_text(canonical(dict(executable=actual, moduleRoot=root, version=version, project=project)))


def free_port():
    with socket.socket() as stream:
        stream.bind(("127.0.0.1", 0))
        return stream.getsockname()[1]


def await_proxy(port, process):
    for _ in range(100):
        if process.poll() is not None:
            raise ValueError("legacy acquisition proxy exited at startup")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                return
        except OSError:
            time.sleep(0.1)
    raise ValueError("legacy acquisition proxy did not start")


def proxy_environment(port, certificate):
    env = os.environ.copy()
    for name in ["http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY"]:
        env[name] = "http://127.0.0.1:" + str(port)
    for name in ["ALL_PROXY", "all_proxy"]:
        env.pop(name, None)
    for name in ["no_proxy", "NO_PROXY"]:
        env[name] = "localhost,127.0.0.1,::1"
    for name in ["SSL_CERT_FILE", "NIX_SSL_CERT_FILE", "CURL_CA_BUNDLE"]:
        env[name] = str(certificate)
    return env


def checked_flags(flags):
    for flag in flags:
        if "\n" in flag or "\r" in flag:
            raise ValueError("native CMake2.8 cannot persist newline configure definitions in its cache")
        if not flag.startswith("-D") or "=" not in flag:
            raise ValueError("legacy profile accepts configure definitions only as -Dname=value")
        name = flag[2:].split("=", 1)[0].split(":", 1)[0]
        if not name or name.startswith("CMAKE_PURIFIER_") or name.startswith("CMAKE_PROJECT_") or name in {"CMAKE_COMMAND", "CMAKE_ROOT", "CMAKE_INSTALL_PREFIX", "CMAKE_HOME_DIRECTORY"}:
            raise ValueError("configure flag replaces the native observation/install context: " + name)
    return flags


def native_lifecycle(config, source, flags, work, env, prefix=None):
    build = work / "build"
    prefix = Path(prefix) if prefix is not None else work / "prefix"
    build.mkdir()
    context = work / "context.json"
    context.write_text(canonical(config | {"sourceDirectory": str(source.resolve()), "buildDirectory": str(build.resolve())}))
    cmake = str(Path(config["sdk"]["package"], "bin/cmake"))
    arguments = [cmake, str(source), "-DCMAKE_INSTALL_PREFIX=" + str(prefix),
                 "-DCMAKE_PROJECT_" + config["projectName"] + "_INCLUDE=" + config["projectHook"],
                 "-DCMAKE_PURIFIER_LEGACY_PYTHON=" + sys.executable,
                 "-DCMAKE_PURIFIER_LEGACY_DRIVER=" + str(Path(__file__).resolve()),
                 "-DCMAKE_PURIFIER_LEGACY_CONTEXT=" + str(context)] + checked_flags(flags)
    run(arguments, cwd=build, env=env)
    if not Path(str(context) + ".identity").is_file():
        raise ValueError("native project startup hook did not run; no capture accepted")
    run([cmake, "--build", ".", "--", "-j2"], cwd=build, env=env)
    run([str(Path(config["sdk"]["package"], "bin/ctest")), "--output-on-failure"], cwd=build, env=env)
    run([cmake, "--build", ".", "--target", "install"], cwd=build, env=env)
    manifest = build / "install_manifest.txt"
    if not manifest.is_file():
        raise ValueError("native install wrote no install manifest")
    files = []
    for line in manifest.read_text().splitlines():
        path = Path(line)
        try:
            relative = path.relative_to(prefix)
        except ValueError:
            raise ValueError("native install manifest escapes captured prefix") from None
        if not path.exists() or path.is_symlink() and not path.resolve().is_relative_to(prefix):
            raise ValueError("native install manifest names a missing or escaping file")
        files.append(str(relative))
    return sorted(set(files))


def capture(config, source, lockfile, flags, update):
    from records import file_artifacts
    with tempfile.TemporaryDirectory(prefix="cmake-purifier-legacy-") as temporary:
        work = Path(temporary)
        record = work / "http.jsonl"
        port = free_port()
        env = os.environ.copy()
        env["PURIFIER_RECORD"] = str(record)
        command = [config["mitmdump"], "-q", "--listen-host", "127.0.0.1", "--listen-port", str(port),
                   "--set", "confdir=" + str(work / "ca"), "-s", config["recorder"]]
        process = subprocess.Popen(command, env=env, stdout=sys.stderr, stderr=sys.stderr)
        before = definition_hash(config, source)
        original_sources = source_snapshot(source)
        try:
            await_proxy(port, process)
            files = native_lifecycle(config, source, flags, work, proxy_environment(port, work / "ca/mitmproxy-ca-cert.pem"))
        finally:
            process.terminate()
            process.wait()
        if original_sources != source_snapshot(source):
            raise ValueError("original project source bytes changed during native capture")
        if before != definition_hash(config, source):
            raise ValueError("project build definitions changed during native capture")
        responses = [json.loads(line) for line in record.read_text().splitlines()] if record.exists() else []
        artifacts = sorted(file_artifacts(responses).values(), key=lambda entry: entry["path"])
        lock = dict(version=VERSION, nativeProfile=PROFILE, sdk=config["sdk"],
                    project=dict(name=config["projectName"], version=""), definitionHash=before,
                    cmakeFlags=flags, artifacts=artifacts, outputs=dict(files=files),
                    dependencyMetadataAvailable=False, targetMetadataAvailable=False)
        lock["contentHash"] = content_hash(lock)
        if lockfile.exists() and not update:
            previous = read_lock(lockfile)
            old = {entry["url"]: entry["hash"] for entry in previous["artifacts"]}
            if any(entry["url"] in old and old[entry["url"]] != entry["hash"] for entry in artifacts):
                raise ValueError("locked URL returned different bytes; use explicit update")
        # Validate before atomic replacement; a failed capture preserves the old lock.
        pending = work / "validated-lock.json"
        pending.write_text(canonical(lock))
        read_lock(pending)
        lockfile.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", dir=lockfile.parent, prefix=".legacy-lock-", delete=False) as output:
            output.write(json.dumps(lock, sort_keys=True, indent=2, ensure_ascii=False) + "\n")
            staged = Path(output.name)
        staged.replace(lockfile)


def check_context(config, source, lockfile):
    lock = read_lock(lockfile)
    if lock["sdk"] != config["sdk"] or lock["project"]["name"] != config["projectName"]:
        raise ValueError("legacy lock differs from live source-owned SDK/project scope")
    if definition_hash(config, source) != lock["definitionHash"]:
        raise ValueError("legacy lock is older than project build definitions")
    return lock


def prefetch(config, source, lockfile, state):
    check_context(config, source, lockfile)
    state.mkdir(parents=True, exist_ok=True)
    (state / ".gitignore").write_text("*\n")
    command = ["nix-build", config["prefetchExpression"], "--argstr", "nixpkgs", config["nixpkgs"],
               "--argstr", "purifier", config["purifier"], "--argstr", "lockFile", str(lockfile),
               "--out-link", str(state / "sources-root")]
    run(command)
    stamp = state / "lock-hash.tmp"
    stamp.write_text(read_lock(lockfile)["contentHash"] + "\n")
    stamp.replace(state / "lock-hash")


def replay(config, source, lockfile, state, arguments):
    lock = check_context(config, source, lockfile)
    if not (state / "lock-hash").exists() or (state / "lock-hash").read_text().strip() != lock["contentHash"]:
        raise ValueError("prefetched acquisition tree belongs to another lock; prefetch again")
    if arguments and arguments[0] == "--":
        arguments = arguments[1:]
    if not arguments or not (state / "sources-root").exists():
        raise ValueError("replay needs prefetched acquisitions and a command after --")
    ca = state / "ca"
    ca.mkdir(exist_ok=True)
    key, cert = ca / "ca.key", ca / "ca.cer"
    if not key.exists() or not cert.exists():
        run([config["openssl"], "genrsa", "-out", str(key), "2048"], stdout=sys.stderr, stderr=sys.stderr)
        run([config["openssl"], "req", "-x509", "-new", "-nodes", "-key", str(key), "-sha256", "-days", "3650", "-out", str(cert), "-subj", "/CN=cmake-purifier"], stdout=sys.stderr, stderr=sys.stderr)
    port = free_port()
    process = subprocess.Popen([config["replay"], "-l", "127.0.0.1:" + str(port), "-k", str(key), "-c", str(cert), "replay", str((state / "sources-root").resolve())], stdout=sys.stderr, stderr=sys.stderr)
    try:
        await_proxy(port, process)
        run(arguments, env=proxy_environment(port, cert))
    finally:
        process.terminate()
        process.wait()


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "build":
        _, _, config_file, source, work, lockfile, prefix = sys.argv
        config = json.loads(Path(config_file).read_text())
        lock = read_lock(lockfile)
        if lock["sdk"] != config["sdk"] or lock["project"]["name"] != config["projectName"]:
            raise ValueError("legacy lock SDK/project differs from live source-owned scope")
        if definition_hash(config, Path(source)) != lock["definitionHash"]:
            raise ValueError("legacy lock is older than project build definitions")
        work = Path(work)
        work.mkdir()
        original_sources = source_snapshot(Path(source))
        files = native_lifecycle(config, Path(source), lock["cmakeFlags"], work, os.environ.copy(), prefix)
        if original_sources != source_snapshot(Path(source)):
            raise ValueError("original project source bytes changed during native rebuild")
        if files != lock["outputs"]["files"]:
            raise ValueError("native installed file manifest differs from legacy lock")
        return
    if len(sys.argv) > 1 and sys.argv[1] == "identity":
        identity(*sys.argv[2:])
        return
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("command", choices=["lock", "update", "prefetch", "replay"])
    parser.add_argument("-S", dest="source", default=".")
    parser.add_argument("--lockfile")
    options, flags = parser.parse_known_args()
    config = json.loads(Path(options.config).read_text())
    source = Path(options.source).resolve()
    lockfile = Path(options.lockfile or os.environ.get("CMAKE_PURIFIER_LOCKFILE", source / "cmake-purifier.lock.json")).resolve()
    state = lockfile.parent / ".cmake-purifier"
    if options.command == "prefetch":
        if flags:
            raise ValueError("prefetch accepts source and lockfile only")
        prefetch(config, source, lockfile, state)
    elif options.command == "replay":
        replay(config, source, lockfile, state, flags)
    else:
        if lockfile.exists():
            previous = read_lock(lockfile)
            if previous["sdk"] != config["sdk"] or previous["project"]["name"] != config["projectName"]:
                raise ValueError("existing legacy lock differs from live SDK/project scope")
            if not flags:
                flags = previous["cmakeFlags"]
        capture(config, source, lockfile, flags, options.command == "update")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, TypeError, KeyError, subprocess.CalledProcessError) as error:
        print("cmake-purifier:", error, file=sys.stderr)
        sys.exit(1)
