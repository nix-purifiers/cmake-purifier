# SPDX-License-Identifier: MIT
import hashlib
import json
from pathlib import Path
import sys

source, source_proof, package, proof, consumer = map(Path, sys.argv[1:])
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
model = json.loads((proof / 'native-lua.json').read_text())
compiler = json.loads((source_proof / 'thrift-lua.json').read_text())
raw = {row['path']: Path(row['file']) for row in compiler['ownership']}
generated = {}
for name, digest in model['generatedHashes'].items():
    installed = package / 'share/lua/5.4' / model['installedFiles'][name]
    assert sha(raw[name]) == sha(source / name) == sha(installed) == digest
    generated[str(installed.resolve())] = digest
sdk = Path(model['runtime'])
original = Path(model['originalSDKSource'])
for name, digest in model['originalSDKFiles'].items():
    assert sha(original / name) == sha(sdk / 'runtime-source' / name) == digest
for path in original.glob('*.lua'):
    assert sha(path) == sha(sdk / 'share/lua/5.4' / path.name)
for row in model['nativeLibraries'].values():
    assert sha(Path(row['path'])) == row['sha256']
for name, row in model['compiledSources'].items():
    assert sha(original / name) == row['sha256']
    assert sha(Path(row['dependencyFile'])) == row['dependencySha256']
for row in model['loaded']:
    assert sha(Path(row['path'])) == row['sha256']
origins = {}
for line in (consumer / 'native-modules.tsv').read_text().splitlines():
    name, filename = line.split('\t')
    path = Path(filename).resolve(strict=True)
    assert path.is_relative_to(package) or path.is_relative_to(sdk)
    origins[name] = {'path': str(path), 'sha256': sha(path)}
methods = {}
for line in (consumer / 'native-methods.tsv').read_text().splitlines():
    name, filename = line.split('\t')
    assert filename.startswith('@'), filename
    path = Path(filename[1:]).resolve(strict=True)
    assert path.is_relative_to(package) or path.is_relative_to(sdk)
    if path.is_relative_to(package):
        assert sha(path) == generated[str(path)]
    else:
        assert sha(path) == sha(original / path.name)
    methods[name] = {'path': str(path), 'sha256': sha(path)}
assert len(methods) == 8
print(json.dumps({'generated': model['generatedHashes'], 'SDK': model['originalSDKFiles'],
                  'libraries': model['nativeLibraries'], 'compiledSources': model['compiledSources'],
                  'consumerOrigins': origins, 'nativeMethods': methods}, indent=2))
