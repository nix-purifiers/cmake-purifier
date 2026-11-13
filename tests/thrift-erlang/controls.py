# SPDX-License-Identifier: MIT
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

spec = json.loads(Path(sys.argv[1]).read_text())
loader = importlib.util.spec_from_file_location('native_generator', spec['generator'])
generator = importlib.util.module_from_spec(loader)
loader.loader.exec_module(generator)
model = json.loads((Path(spec['proof']) / 'thrift-erlang.json').read_text())
for name, expected in model['generatedHashes'].items():
    directory = 'src' if name.endswith('.erl') else 'include'
    actual = Path(spec['package']) / 'lib/schema' / directory / name
    assert hashlib.sha256(actual.read_bytes()).hexdigest() == expected, name

def bundle(name):
    root = Path(name).resolve()
    shutil.copytree(spec['resources'], root)
    for path in root.rglob('*'):
        path.chmod(0o755 if path.is_dir() else 0o644)
    return root

def admit(root, name, content):
    path = root / 'files' / name
    path.write_text(content)
    catalog_path = root / 'catalog.json'
    catalog = json.loads(catalog_path.read_text())
    catalog['files'][name]['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    catalog_path.write_text(json.dumps(catalog))

controls = []
def reject(name, root, diagnostic):
    try:
        generator.generate({'resources': str(root), 'sdk': spec['sdk']}, Path(name + '-out'), Path(name + '-proof'))
    except ValueError as error:
        message = str(error)
    except subprocess.CalledProcessError as error:
        message = str(error) + (error.stdout or '') + (error.stderr or '')
    else:
        raise AssertionError('accepted negative control ' + name)
    assert diagnostic in message, (name, message)
    controls.append(name)

changed = bundle('changed')
path = changed / 'files/common/value.thrift'
path.write_text(path.read_text() + '\n// uncaptured change\n')
reject('changed-source', changed, 'does not match captured resource hash')
missing = bundle('missing')
(missing / 'files/common/value.thrift').unlink()
reject('missing-import', missing, 'common/value.thrift')
outside = bundle('outside')
foreign = Path('foreign/value.thrift').resolve()
foreign.parent.mkdir()
foreign.write_text((outside / 'files/common/value.thrift').read_text())
admit(outside, 'main.thrift', (outside / 'files/main.thrift').read_text().replace('common/value.thrift', str(foreign)))
reject('outside-import', outside, 'native compiler input escapes')
collision = bundle('collision')
admit(collision, 'common/value.thrift', (collision / 'files/common/value.thrift').read_text() + '\nservice AnswerService { i32 other() }\n')
reject('generated-collision', collision, 'native generated Erlang output collision')
projection_joins = []
for case in spec['projectedCases']:
    catalog = json.loads(Path(case['catalog']).read_text())
    assert catalog['roots'] == ['schema']
    apps = {app['name']: app for app in catalog['applications']}
    assert set(apps) == {'schema', 'thrift'}
    assert apps['schema']['origin'] == case['producer']
    assert apps['thrift']['origin'] == case['runtime']
    native = json.loads((Path(case['proof']) / 'thrift-erlang.json').read_text())
    assert native['compilerVersion'] == 'Thrift version ' + apps['thrift']['version']
    joined = 0
    for app in apps.values():
        for record in app['files']:
            original = Path(app['originDirectory']) / record['path']
            projected = Path(case['repository']) / app['directory'] / record['path']
            assert original.read_bytes() == projected.read_bytes()
            assert hashlib.sha256(projected.read_bytes()).hexdigest() == record['sha256']
            assert (projected.stat().st_mode & 0o777) == record['mode']
            joined += 1
    projection_joins.append({'repository': case['repository'], 'nativeFileJoins': joined,
        'nativeVersions': {name: app['version'] for name, app in apps.items()}})
Path(sys.argv[2]).write_text(json.dumps({'generatedByteJoins': len(model['generatedHashes']),
    'controls': controls, 'projectionJoins': projection_joins}, indent=2) + '\n')
