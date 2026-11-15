# SPDX-License-Identifier: MIT
"""Bind the native runtime wheel to its compiler's own source release."""
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile

sdk, source, output, proof = map(Path, sys.argv[1:])
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
version = subprocess.check_output([str(sdk/'bin/thrift'), '--version'], text=True).strip()
match = re.fullmatch(r'Thrift version (\d+\.\d+\.\d+)', version)
if match is None:
    raise ValueError('cannot read native compiler version')
wheels = list(output.glob('*.whl'))
if len(wheels) != 1:
    raise ValueError('native SDK backend did not produce exactly one runtime wheel')
with zipfile.ZipFile(wheels[0]) as wheel:
    metadata = [name for name in wheel.namelist() if name.endswith('.dist-info/METADATA')]
    if len(metadata) != 1:
        raise ValueError('ambiguous native runtime metadata')
    model = BytesParser().parsebytes(wheel.read(metadata[0]))
    if model['Name'] != 'thrift' or model['Version'] != match[1]:
        raise ValueError('native runtime wheel differs from selected compiler version')
    # Native setup.py declares package_dir={thrift: src}; validate all retained
    # runtime Python files against that source mapping, without rewriting it.
    owned = {}
    for name in wheel.namelist():
        if name.startswith('thrift/') and name.endswith('.py'):
            path = source/'src'/name[len('thrift/'):]
            if wheel.read(name) != path.read_bytes():
                raise ValueError('runtime Python source differs from native SDK: '+name)
            owned[name] = sha(path)
    if not owned:
        raise ValueError('native runtime wheel contains no Python sources')
    native = {name: hashlib.sha256(wheel.read(name)).hexdigest() for name in wheel.namelist()
              if name.endswith(('.so', '.pyd', '.dylib'))}
record = {'sdk': str(sdk), 'source': str(source), 'compilerVersion': version,
          'name': model['Name'], 'version': model['Version'],
          'wheel': wheels[0].name, 'wheelSha256': sha(wheels[0]),
          'runtimeSources': owned, 'nativeExtensions': native,
          'sourceHashes': {str(p.relative_to(source)): sha(p)
                           for p in sorted(source.rglob('*')) if p.is_file()}}
(proof/'runtime.json').write_text(json.dumps(record, sort_keys=True, indent=2)+'\n')
