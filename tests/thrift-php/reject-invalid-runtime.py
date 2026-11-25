# SPDX-License-Identifier: MIT
"""Exercise rejection with the actual installed SDK, not fabricated metadata."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

spec = json.loads(Path(sys.argv[1]).read_text())
work = Path.cwd()
original = spec['runtime']
results = {}


def reject(name, current, diagnostic):
    request = work / (name + '.json')
    request.write_text(json.dumps(current))
    run = subprocess.run([sys.executable, spec['verifier'], str(request),
                          str(work / (name + '-proof.json'))], capture_output=True, text=True)
    assert run.returncode and diagnostic in run.stderr, run.stdout + run.stderr
    results[name] = diagnostic


installed = work / 'installed'
shutil.copytree(original['installedRoot'], installed, symlinks=True)
for path in installed.rglob('*'):
    if not path.is_symlink():
        path.chmod(path.stat().st_mode | 0o200)
current = dict(original, producer=str(installed), installedRoot=str(installed))
lock = json.loads((installed / 'composer.lock').read_text())
lock.update(packages=[], **{'packages-dev': []})
(installed / 'composer.lock').write_text(json.dumps(lock))
(installed / 'vendor/composer/installed.json').write_text('{"packages": []}')
reject('missing-original-requirements', current, 'native SDK dependency missing or incompatible')

proof = json.loads(Path(spec['proof']).read_text())
runtime_file = installed / next(iter(proof['sourceFiles']))
runtime_file.write_bytes(runtime_file.read_bytes() + b'\n// changed runtime bytes\n')
reject('changed-sdk-bytes', current, 'SDK PHP source or installed method bytes changed')
reject('foreign-producer', dict(original, producer=str(work)),
       'outside its original producer output')

collision = work / 'collision'
collision.mkdir()
(collision / 'TBinaryProtocol.php').write_text(
    '<?php namespace Thrift\\Protocol; class TBinaryProtocol {}\n')
paths = work / 'class-paths.json'
paths.write_text(json.dumps(proof['autoloadRoots'] + [str(collision)]))
run = subprocess.run([original['php'], spec['classes'], spec['autoload'], str(paths)],
                     capture_output=True, text=True)
assert run.returncode and 'native PHP class collision' in run.stdout + run.stderr, run.stdout + run.stderr
results['sdk-class-shadow'] = 'native PHP class collision'
Path(sys.argv[2]).write_text(json.dumps(results, indent=2) + '\n')
