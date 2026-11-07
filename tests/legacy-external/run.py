# SPDX-License-Identifier: MIT
"""Real old-native capture, deterministic relock and cold/pure lifecycle proof."""
import argparse
import functools
import hashlib
import http.server
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
from make_fixture import make_fixture

EDGE = {"SEMICOLON": "one;two", "EMPTY": "", "SPACE": "with space", "NEWLINE": "line1\nline2", "DOLLAR": "literal${value}", "ESCAPE": 'quote"slash\\tail'}


def execute(command, work, name, env=None, fails=False, cwd=None):
    result = subprocess.run(command, env=env, cwd=cwd, capture_output=True, text=True)
    (work / (name + ".log")).write_text(result.stdout + result.stderr)
    (work / (name + ".json")).write_text(json.dumps(dict(command=command, returncode=result.returncode, expectedFailure=fails), indent=2) + "\n")
    if (result.returncode == 0) == fails:
        raise AssertionError(name + ": unexpected exit; see " + str(work / (name + ".log")))
    return result


def verify_install(prefix, sdk):
    prefix, sdk = Path(prefix), Path(sdk)
    version_output = subprocess.check_output([str(sdk / "bin/cmake"), "--version"], text=True)
    version = re.search(r"^cmake version (\S+)", version_output).group(1)
    roots = sorted((sdk / "share").glob("cmake-*"))
    assert len(roots) == 1, roots
    expected = dict(executable=str((sdk / "bin/cmake").resolve()), moduleRoot=str(roots[0].resolve()), version=version)
    for name in ["root", "middle", "leaf"]:
        identity = json.loads((prefix / ("share/legacy-proof/" + name + "-identity.json")).read_text())
        assert identity == expected, identity
    for name, value in EDGE.items():
        assert (prefix / ("share/legacy-proof/argument-" + name + ".txt")).read_text() == value
    subprocess.run([str(prefix / "bin/assert_answer")], check=True)


def snapshot(source):
    return {str(path.relative_to(source)): hashlib.sha256(path.read_bytes()).hexdigest() for path in source.rglob("*") if path.is_file() and ".cmake-purifier" not in path.parts}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli", required=True)
    parser.add_argument("--sdk", required=True)
    parser.add_argument("--work", required=True)
    parser.add_argument("--foreign-cli", required=True)
    parser.add_argument("--modern-cmake", required=True)
    parser.add_argument("--port", type=int, default=8765)
    options = parser.parse_args()
    work = Path(options.work).resolve()
    work.mkdir(parents=True)
    cli, sdk = str(Path(options.cli).resolve() / "bin/cmake-purifier"), str(Path(options.sdk).resolve())
    requests = []
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, fmt, *args):
            requests.append(fmt % args)
    origin = http.server.ThreadingHTTPServer(("127.0.0.2", options.port), functools.partial(Handler, directory=str(work / "origin")))
    threading.Thread(target=origin.serve_forever, daemon=True).start()
    source, archive_hashes = make_fixture(work, "http://127.0.0.2:" + str(origin.server_port))
    flags = ["-DEDGE_" + name + "=" + value for name, value in EDGE.items() if name != "NEWLINE"]
    try:
        # The unmodified native command is the independent lifecycle oracle.
        native = work / "native"
        native.mkdir()
        prefix = work / "native-install"
        env = os.environ.copy()
        for name in ["http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"]:
            env.pop(name, None)
        commands = [[sdk + "/bin/cmake", str(source), "-DCMAKE_INSTALL_PREFIX=" + str(prefix)] + flags,
                    [sdk + "/bin/cmake", "--build", str(native), "--", "-j2"],
                    [sdk + "/bin/ctest", "--output-on-failure"],
                    [sdk + "/bin/cmake", "--build", str(native), "--target", "install"]]
        for index, command in enumerate(commands):
            result = subprocess.run(command, cwd=native, env=env, capture_output=True, text=True)
            (work / ("native-" + str(index) + ".log")).write_text(result.stdout + result.stderr)
            assert result.returncode == 0, result.stderr
        verify_install(prefix, sdk)
        newline_build = work / "native-newline-negative"
        newline_build.mkdir()
        result = subprocess.run([sdk + "/bin/cmake", str(source), "-DEDGE_NEWLINE=line1\nline2"], cwd=newline_build, env=env, capture_output=True, text=True)
        (work / "native-newline-negative.log").write_text(result.stdout + result.stderr)
        if result.returncode == 0:
            result = subprocess.run([sdk + "/bin/cmake", str(source)], cwd=newline_build, env=env, capture_output=True, text=True)
            (work / "native-newline-reconfigure-negative.log").write_text(result.stdout + result.stderr)
        assert result.returncode != 0 and "Parse error in cache file" in result.stderr
        original = snapshot(source)
        execute([cli, "lock", "-S", str(source)] + flags, work, "capture")
        lockfile = source / "cmake-purifier.lock.json"
        first = lockfile.read_bytes()
        assert snapshot(source) == original | {"cmake-purifier.lock.json": hashlib.sha256(first).hexdigest()}
        lock = json.loads(first)
        assert len(lock["artifacts"]) == 2 and lock["cmakeFlags"] == flags
        assert lock["dependencyMetadataAvailable"] is False and lock["targetMetadataAvailable"] is False
        before_requests = len(requests)
        execute([cli, "lock", "-S", str(source), "-DEDGE_NEWLINE=line1\nline2"], work, "newline-negative", fails=True)
        assert lockfile.read_bytes() == first and len(requests) == before_requests
        execute([cli, "lock", "-S", str(source)], work, "relock")
        assert lockfile.read_bytes() == first
        relocated = work / "relocated"
        shutil.copytree(source, relocated)
        execute([cli, "lock", "-S", str(relocated)], work, "relocated-relock")
        assert (relocated / lockfile.name).read_bytes() == first
        # A source override must not silently suppress native observation.
        missing = work / "missing-hook"
        shutil.copytree(source, missing)
        definition = missing / "CMakeLists.txt"
        definition.write_text('set(CMAKE_PROJECT_legacy_native_INCLUDE "")\n' + definition.read_text())
        before_requests = len(requests)
        execute([cli, "lock", "-S", str(missing)], work, "missing-hook", fails=True)
        assert (missing / lockfile.name).read_bytes() == first and len(requests) == before_requests
        foreign = work / "foreign-sdk-source"
        shutil.copytree(source, foreign, ignore=shutil.ignore_patterns("cmake-purifier.lock.json", ".cmake-purifier"))
        before_requests = len(requests)
        execute([str(Path(options.foreign_cli) / "bin/cmake-purifier"), "lock", "-S", str(foreign)] + flags, work, "foreign-sdk", fails=True)
        assert not (foreign / lockfile.name).exists() and len(requests) == before_requests
        assert "native executable/module root/version/project differs" in (work / "foreign-sdk.log").read_text()
        modern = work / "modern-control"
        modern.mkdir()
        execute([str(Path(options.modern_cmake) / "bin/cmake"), str(source), "-DCMAKE_POLICY_VERSION_MINIMUM=3.5"], work, "modern-control", env=env, fails=True, cwd=modern)
        assert "export_library_dependencies command has been removed" in (work / "modern-control.log").read_text()
        # Native URL_HASH rejects changed server bytes; old lock remains intact.
        leaf = work / "origin/leaf.tar.gz"
        saved = leaf.read_bytes()
        leaf.write_bytes(saved + b"changed")
        execute([cli, "lock", "-S", str(source)], work, "mutated-origin", fails=True)
        assert lockfile.read_bytes() == first
        leaf.write_bytes(saved)
        # Prefetch the actual URLs while the origin is still available.
        execute([cli, "prefetch", "-S", str(source)], work, "prefetch")
    finally:
        origin.shutdown()
        origin.server_close()
        (work / "origin-requests.json").write_text(json.dumps(requests, indent=2) + "\n")
    assert snapshot(source) == original | {"cmake-purifier.lock.json": hashlib.sha256(first).hexdigest()}
    (work / "fixture.json").write_text(json.dumps(dict(source=str(source), sdk=sdk, cli=cli, archiveHashes=archive_hashes, flags=flags, originalSourceHashes=original), indent=2) + "\n")
    print("Native/capture/relock/relocation/negative/prefetch passed; origin is stopped:", work)


if __name__ == "__main__":
    main()
