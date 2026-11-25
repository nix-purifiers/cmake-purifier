"""Use the owning frozen Composer SDK to install a generated native package."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

spec = json.loads(Path(sys.argv[1]).read_text())
source, installed, proof = map(Path, sys.argv[2:5])
sys.path.insert(0, spec['tools'])
from composer_inputs import bind, packages, sdk_environment
from composer_root import capture

shutil.copytree(source, installed, dirs_exist_ok=True)
for path in [installed, *installed.rglob('*')]:
    if not path.is_symlink():
        path.chmod(path.stat().st_mode | 0o200)
selected = packages(spec['dependencies'])
document = json.loads((source / 'composer.json').read_text())
(installed / 'composer.json').write_text(json.dumps(bind(document, selected), indent=2) + '\n')
environment = sdk_environment(selected, spec['php'], spec['autoload'], base=os.environ)
# Use one original native install environment for the resolve/install and root observation.
os.environ.update(environment)
values = {key: os.environ.get(key) for key in ['COMPOSER_ROOT_VERSION','COMPOSER_HOME','COMPOSER_CACHE_DIR','HOME','COMPOSER']}
raw = json.dumps({'format':'composer-purifier-native-install-env-v1','values':values}, sort_keys=True).encode()
(proof / 'native-install-env.json').write_bytes(raw)
result = subprocess.run([spec['php'], spec['tools'] + '/composer_capture.php', 'update',
                         '--no-interaction', '--no-progress', '--no-audit'],
                        cwd=installed, env=environment, capture_output=True, text=True)
(proof / 'install.stdout').write_text(result.stdout)
(proof / 'install.stderr').write_text(result.stderr)
if result.returncode:
    raise RuntimeError(result.stdout + result.stderr)
shutil.copyfile(installed / 'composer.lock', proof / 'native-composer.lock')
request = dict(spec, src=str(source), installed=str(installed), composerLock=str(proof / 'native-composer.lock'))
context = capture(request, proof / 'native-install-env.json', hashlib.sha256(raw).hexdigest())
(proof / 'root-context.json').write_text(json.dumps(context, indent=2) + '\n')
