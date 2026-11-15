# SPDX-License-Identifier: MIT
"""Join compiled runtime source copies to the selected native Thrift SDK."""
import hashlib
import json
from pathlib import Path
import sys

source, runtime, proof, compiler, erlang = map(Path, sys.argv[1:])
hashes = {}
for directory, suffix in [("src", ".erl"), ("include", ".hrl")]:
    for original in sorted((source / "lib/erl" / directory).glob("*" + suffix)):
        copied = runtime / "lib/thrift" / directory / original.name
        if original.read_bytes() != copied.read_bytes():
            raise ValueError("compiled runtime source differs from selected SDK: " + str(original))
        hashes[directory + "/" + original.name] = hashlib.sha256(original.read_bytes()).hexdigest()
proof.mkdir(parents=True, exist_ok=True)
(proof / "runtime.json").write_text(json.dumps({
    "format": "purifier-thrift-erlang-runtime-v1",
    "sdkSource": str(source), "sdk": str(compiler), "erlang": str(erlang),
    "nativeApplicationTemplateSha256": hashlib.sha256((source / "lib/erl/src/thrift.app.src").read_bytes()).hexdigest(),
    "sourceHashes": hashes,
    "excludedCompilationUnits": [name for name in hashes if name.startswith("src/") and name.endswith("_test.erl")],
    "beamHashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((runtime / "lib/thrift/ebin").glob("*.beam"))},
    "nativeCompilationObservation": str(runtime / "lib/thrift/ebin/otp-observation.term"),
}, indent=2) + "\n")
