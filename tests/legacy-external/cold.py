# SPDX-License-Identifier: MIT
"""Run under unshare -rn with loopback enabled, after run.py stops origin."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
from run import execute, verify_install, snapshot


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", required=True)
    parser.add_argument("--inside", action="store_true")
    parser.add_argument("--corrupt", action="store_true")
    parser.add_argument("--source")
    options = parser.parse_args()
    work = Path(options.work).resolve()
    fixture = json.loads((work / "fixture.json").read_text())
    source, sdk, cli = Path(options.source or fixture["source"]), fixture["sdk"], fixture["cli"]
    if not options.inside:
        before = snapshot(source)
        execute([cli, "replay", "-S", str(source), "--", sys.executable, "-B", str(Path(__file__).resolve()), "--work", str(work), "--inside"], work, "cold-replay")
        assert before == snapshot(source)
        # Missing acquisitions fail through the real native HTTP client.
        lock = json.loads((source / "cmake-purifier.lock.json").read_text())
        unknown = lock["artifacts"][0]["url"].rsplit("/", 1)[0] + "/not-locked.tar.gz"
        script = work / "unknown-download.cmake"
        script.write_text('file(DOWNLOAD "' + unknown + '" "' + str(work / "unknown-download") + '" STATUS result)\nlist(GET result 0 code)\nif(NOT code EQUAL 0)\n message(FATAL_ERROR "unknown acquisition rejected: ${result}")\nendif()\n')
        execute([cli, "replay", "-S", str(source), "--", sdk + "/bin/cmake", "-P", str(script)], work, "unknown-url", fails=True)
        # Replay must never reuse a tree rooted for another lock.
        stamp = source / ".cmake-purifier/lock-hash"
        saved = stamp.read_bytes()
        stamp.write_text("sha256:wrong-lock\n")
        try:
            execute([cli, "replay", "-S", str(source), "--", sdk + "/bin/cmake", "--version"], work, "stale-cache", fails=True)
        finally:
            stamp.write_bytes(saved)
        corrupt_source = work / "corrupt-source"
        shutil.copytree(source, corrupt_source, ignore=shutil.ignore_patterns(".cmake-purifier"))
        corrupt_cache = work / "corrupt-cache"
        shutil.copytree((source / ".cmake-purifier/sources-root").resolve(), corrupt_cache)
        leaf = next(entry for entry in lock["artifacts"] if entry["url"].endswith("/leaf.tar.gz"))
        archive = corrupt_cache / leaf["path"]
        archive.write_bytes(archive.read_bytes() + b"changed")
        state = corrupt_source / ".cmake-purifier"
        state.mkdir()
        (state / "sources-root").symlink_to(corrupt_cache)
        (state / "lock-hash").write_bytes(saved)
        execute([cli, "replay", "-S", str(corrupt_source), "--", sys.executable, "-B", str(Path(__file__).resolve()), "--work", str(work), "--inside", "--corrupt", "--source", str(corrupt_source)], work, "corrupt-cache", fails=True)
        assert "file DOWNLOAD HASH mismatch" in (work / "corrupt-native-1.log").read_text()
        assert (corrupt_source / "cmake-purifier.lock.json").read_bytes() == (source / "cmake-purifier.lock.json").read_bytes()
        print("Cold native replay, installed consumer, unknown URL, stale-cache and corrupt-byte controls passed")
        return
    label = "corrupt" if options.corrupt else "cold"
    build = work / (label + "-build")
    build.mkdir()
    prefix = work / (label + "-install")
    commands = [[sdk + "/bin/cmake", str(source), "-DCMAKE_INSTALL_PREFIX=" + str(prefix)] + fixture["flags"],
                [sdk + "/bin/cmake", "--build", str(build), "--", "-j2"],
                [sdk + "/bin/ctest", "--output-on-failure"],
                [sdk + "/bin/cmake", "--build", str(build), "--target", "install"]]
    for index, command in enumerate(commands):
        result = subprocess.run(command, cwd=build, capture_output=True, text=True)
        (work / (label + "-native-" + str(index) + ".log")).write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result.stderr
    verify_install(prefix, sdk)
    installed_consumer = work / "installed-consumer"
    command = ["cc", str(source / "main.c"), str(prefix / "lib/libmiddle.a"), str(prefix / "lib/libleaf.a"), "-o", str(installed_consumer)]
    execute(command, work, "installed-consumer-link")
    execute([str(installed_consumer)], work, "installed-consumer-run")
    execute(["cc", str(source / "main.c"), str(prefix / "lib/libmiddle.a"), "-o", str(work / "missing-leaf")], work, "missing-transitive-library", fails=True)
    (work / "cold-identity.json").write_text(json.dumps({name: json.loads((prefix / ("share/legacy-proof/" + name + "-identity.json")).read_text()) for name in ["root", "middle", "leaf"]}, indent=2) + "\n")


if __name__ == "__main__":
    main()
