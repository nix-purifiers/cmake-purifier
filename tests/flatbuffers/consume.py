# SPDX-License-Identifier: MIT
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

spec = json.loads(Path(sys.argv[1]).read_text())
out = Path(sys.argv[2]); out.mkdir()
source = Path(__file__).parent
results = []
for index, package in enumerate(spec['packages']):
    package = Path(package)
    bits = [32, 64][index]
    model = json.loads((package / 'flatbuffers-products.json').read_text())
    assert set(model['schemaHashes']) == {'main.fbs', 'common/value.fbs'}
    for name, expected in model['schemaHashes'].items():
        assert hashlib.sha256((Path(model['resources']) / 'files' / name).read_bytes()).hexdigest() == expected
    for name, expected in model['generatedHashes'].items():
        assert hashlib.sha256((package / name).read_bytes()).hexdigest() == expected
    build = Path(f'build-{index}')
    subprocess.run(['cmake', '-S', str(source), '-B', str(build), '-G', 'Ninja',
                    '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON', '-DCMAKE_PREFIX_PATH=' + str(package) + ';' + model['sdk'],
                    '-DEXPECT_BITS=' + str(bits)], check=True)
    subprocess.run(['cmake', '--build', str(build)], check=True)
    result = subprocess.check_output([str(build / 'consumer')], text=True).strip()
    assert result.startswith(f'42:{bits}:')
    flags = subprocess.check_output(['pkg-config', '--cflags', '--libs', str(package / 'lib/pkgconfig/schema_proof.pc')], text=True)
    binary = Path(f'pkg-consumer-{index}')
    subprocess.run(['c++', '-DEXPECT_BITS=' + str(bits), '-MD', '-MF', f'headers-{index}.d',
                    str(source / 'consumer.cpp'), '-o', str(binary), *shlex.split(flags)], check=True)
    assert subprocess.check_output(['./' + str(binary)], text=True).strip() == result
    depfile = Path(f'headers-{index}.d').read_text()
    assert str(package / 'include/main_generated.h') in depfile
    assert str(package / 'include/common/value_generated.h') in depfile
    assert model['sdk'] + '/include/flatbuffers/' in depfile
    shutil.copy(build / 'compile_commands.json', out / f'compile_commands-{index}.json')
    shutil.copy(f'headers-{index}.d', out / f'headers-{index}.d')
    results.append({'package': str(package), 'output': result, 'model': model})
assert results[0]['output'].split(':')[2] != results[1]['output'].split(':')[2]
assert results[0]['model']['generatedHashes'] != results[1]['model']['generatedHashes']
bundle = Path('incomplete')
shutil.copytree(Path(results[0]['model']['resources']), bundle)
(bundle / 'files/common').chmod(0o755)
(bundle / 'files/common/value.fbs').unlink()
from importlib.util import spec_from_file_location, module_from_spec
loader = spec_from_file_location('generator', spec['generator']); generator = module_from_spec(loader); loader.loader.exec_module(generator)
try:
    generator.generate({'resources':str(bundle), 'sdk':results[0]['model']['sdk'], 'name':'schema_proof','version':'1.0.0'},Path('unexpected'))
except subprocess.CalledProcessError:
    pass
else:
    raise AssertionError('native flatc accepted missing captured include')
(out / 'verification.json').write_text(json.dumps({'consumers':results,'missingIncludeRejected':True},indent=2)+'\n')
