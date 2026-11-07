# SPDX-License-Identifier: MIT
from pathlib import Path
import gzip
import hashlib
import io
import shutil
import tarfile


def make_fixture(work, origin):
    work = Path(work)
    templates = Path(__file__).resolve().parent / "fixture"
    archives = work / "origin"
    archives.mkdir(parents=True, exist_ok=True)
    identity = (templates / "identity.py").read_bytes()

    def archive(name, replacements):
        files = {"identity.py": identity}
        for path in (templates / name).iterdir():
            data = path.read_text()
            for before, after in replacements.items():
                data = data.replace(before, after)
            files[path.name.removesuffix(".in")] = data.encode()
        output = archives / (name + ".tar.gz")
        with output.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped, tarfile.open(fileobj=zipped, mode="w") as tar:
            for filename, data in sorted(files.items()):
                entry = tarfile.TarInfo(name + "/" + filename)
                entry.size, entry.mode, entry.mtime = len(data), 0o644, 0
                tar.addfile(entry, io.BytesIO(data))
        return hashlib.sha256(output.read_bytes()).hexdigest()

    leaf_hash = archive("leaf", {})
    middle_hash = archive("middle", {"@ORIGIN@": origin, "@LEAF_SHA@": leaf_hash})
    source = work / "source"
    source.mkdir()
    for path in (templates / "root").iterdir():
        (source / path.name.removesuffix(".in")).write_text(path.read_text().replace("@ORIGIN@", origin).replace("@MIDDLE_SHA@", middle_hash))
    (source / "identity.py").write_bytes(identity)
    return source, {"leaf": leaf_hash, "middle": middle_hash}
