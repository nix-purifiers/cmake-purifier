# SPDX-License-Identifier: MIT
import hashlib
import json
from pathlib import Path
import sys
import zipfile
import xml.etree.ElementTree as ET

source, source_proof, product, proof, runtime_proof, consumer = map(Path, sys.argv[1:])
generated = json.loads((source_proof / 'thrift-haxe.json').read_text())
installed = json.loads((proof / 'installed-package.json').read_text())
runtime = json.loads((runtime_proof / 'runtime.json').read_text())
typing = json.loads((proof / 'native-typing.json').read_text())
root = Path(installed['classRoot'])
typed_files = {Path(item.get('file')).resolve() for item in ET.parse(consumer / 'typed.xml').iter() if item.get('file')}
joins = {}
with zipfile.ZipFile(product / 'library.zip') as archive:
    for relative, expected in generated['generatedHashes'].items():
        payload = (source_proof / 'generated' / relative).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == expected
        packaged = str(Path(generated['classPath']) / relative)
        assert (source / packaged).read_bytes() == payload
        assert archive.read(packaged) == payload
        assert (root / relative).read_bytes() == payload
        assert (root / relative).resolve() in typed_files
        joins[relative] = expected
sdk = runtime['sdk']['name']
node = runtime['nodes'][sdk]
sdk_root = product / 'repository' / node['folder']
sdk_root = (Path((sdk_root / '.dev').read_text().strip()) if node['marker'] == '.dev'
            else sdk_root / (sdk_root / '.current').read_text().strip().replace('.', ','))
for relative, expected in runtime['sourceFiles'].items():
    assert hashlib.sha256((sdk_root / relative).read_bytes()).hexdigest() == expected
assert typing['target'] == 'neko' and joins
print(json.dumps({'generated': joins, 'originalSdk': runtime['sourceFiles'],
                  'nativeTypedInputs': len(typing['inputs'])}, indent=2))
