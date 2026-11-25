# SPDX-License-Identifier: MIT
import hashlib
import json
from pathlib import Path
import sys

source, native, installed, sdk, runtime = map(Path, sys.argv[1:])
record = json.loads((native / 'thrift-perl.json').read_text())
generated = {}
for name, expected in record['generatedHashes'].items():
    raw = (native / 'generated' / name).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == expected
    assert (source / 'lib' / name).read_bytes() == raw
    assert (installed / 'lib/perl5' / name).read_bytes() == raw
    generated[name] = expected
original = {}
for path in (sdk / 'lib/perl/lib').rglob('*.pm'):
    relative = path.relative_to(sdk / 'lib/perl/lib')
    raw = path.read_bytes()
    assert (runtime / 'lib/perl5' / relative).read_bytes() == raw
    original[str(relative)] = hashlib.sha256(raw).hexdigest()
assert generated and original
print(json.dumps({'generated': generated, 'originalSdk': original}, indent=2))
