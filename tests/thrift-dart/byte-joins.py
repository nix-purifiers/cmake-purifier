# SPDX-License-Identifier: MIT
import hashlib
import json
from pathlib import Path
import sys
import yaml

product, proof, receipt_file = map(Path, sys.argv[1:])
proof = json.loads((proof / 'thrift-dart.json').read_text())
receipt = json.loads(receipt_file.read_text())
joins = {row['owner']: {item['file']: item['sha256'] for item in row['files']}
         for row in receipt['sourceJoins']}
generated = {}
for name, expected in proof['generatedHashes'].items():
    path = product / name
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
    root, relative = name.split('/', 1)
    assert joins[str(product / root)][relative] == expected
    generated[name] = expected
sdk = Path(proof['sdkSource']) / 'lib/dart'
sdk_manifest = yaml.safe_load((sdk / 'pubspec.yaml').read_text())
sdk_files = {}
for path in sdk.rglob('*.dart'):
    relative = path.relative_to(sdk).as_posix()
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    assert joins[str(sdk)][relative] == expected
    sdk_files[relative] = expected
graph = {package['name']: package for package in receipt['activeNativeGraph']['packages']}
native_sdk = graph[sdk_manifest['name']]
assert native_sdk['version'] == str(sdk_manifest['version'])
assert native_sdk['dependencyConstraints'] == sdk_manifest['dependencies']
for name, package in proof['packages'].items():
    assert graph[name]['version'] == package['version']
assert generated and sdk_files
print(json.dumps({'generated': generated, 'originalSdk': sdk_files,
                  'nativeSdkRequirements': native_sdk['dependencyConstraints']}, indent=2))
