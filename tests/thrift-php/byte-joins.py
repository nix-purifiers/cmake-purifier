# SPDX-License-Identifier: MIT
"""Join native output and original SDK bytes through normal Composer install."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

source, native, sdk, runtime_proof, repository, catalog_file, consumer = map(Path, sys.argv[1:])
catalog = json.loads(catalog_file.read_text())
packages = {package['name']: package for package in catalog['packages']}
runtime = json.loads(runtime_proof.read_text())
results = {}
for name, root, files in [
    ('example/native-thrift-php', source,
     {path.relative_to(source).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
      for path in (source / 'src').rglob('*.php')}),
    ('apache/thrift', sdk, runtime['sourceFiles']),
]:
    package = packages[name]
    archive = repository / package['archive']
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == package['checksum']
    joins = {}
    with zipfile.ZipFile(archive) as zipped:
        for relative, expected in files.items():
            original = (root / relative).read_bytes()
            assert hashlib.sha256(original).hexdigest() == expected
            installed = consumer / 'vendor' / name / relative
            assert installed.read_bytes() == original, installed
            members = [member for member in zipped.namelist()
                       if member == relative or member.endswith('/' + relative)]
            assert len(members) == 1, members
            assert zipped.read(members[0]) == original
            if name == 'example/native-thrift-php':
                assert (native / 'generated' / Path(relative).relative_to('src')).read_bytes() == original
            joins[relative] = expected
    assert joins
    results[name] = joins
print(json.dumps(results, indent=2))
