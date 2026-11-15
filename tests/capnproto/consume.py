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
for index, value in enumerate(spec['packages']):
    package = Path(value)
    share = package / 'share/capnp_proof'
    model = json.loads((share / 'capnproto-products.json').read_text())
    assert set(model['schemaHashes']) == {'main.capnp', 'common/value.capnp'}
    assert set(model['sdkSchemaHashes']) == {'capnp/c++.capnp'}
    for name, expected in model['schemaHashes'].items():
        assert hashlib.sha256((Path(model['resources']) / 'files' / name).read_bytes()).hexdigest() == expected
    for name, expected in model['sdkSchemaHashes'].items():
        assert hashlib.sha256((Path(model['sdk']) / 'include' / name).read_bytes()).hexdigest() == expected
    for name, expected in model['generatedHashes'].items():
        assert hashlib.sha256((share / name).read_bytes()).hexdigest() == expected
    for name, expected in model['libraryHashes'].items():
        assert hashlib.sha256((package / name).read_bytes()).hexdigest() == expected
    build = Path(f'build-{index}')
    subprocess.run(['cmake', '-S', str(source), '-B', str(build), '-G', 'Ninja',
                    '-DCMAKE_PREFIX_PATH=' + str(package) + ';' + model['sdk']], check=True)
    subprocess.run(['cmake', '--build', str(build)], check=True)
    args = [str(package / 'lib/libcapnp_proof'), model['sdk'] + '/lib/libcapnp']
    result = subprocess.check_output([str(build / 'consumer'), *args], text=True).strip()
    assert result.startswith('42:13876891746931381282:')
    flags = subprocess.check_output(['pkg-config','--cflags','--libs',str(package/'lib/pkgconfig/capnp_proof.pc')],text=True)
    binary = Path(f'pkg-consumer-{index}')
    subprocess.run(['c++','-std=c++11','-MD','-MF',f'headers-{index}.d',str(source/'consumer.cpp'),'-o',str(binary),*spec['dlLibs'],*shlex.split(flags)],check=True)
    assert subprocess.check_output(['./'+str(binary),*args],text=True).strip() == result
    deps = Path(f'headers-{index}.d').read_text()
    assert str(package / 'include/main.capnp.h') in deps
    assert str(package / 'include/common/value.capnp.h') in deps
    assert model['sdk'] + '/include/capnp/' in deps
    shutil.copy(build/'compile_commands.json',out/f'compile_commands-{index}.json')
    shutil.copy(f'headers-{index}.d',out/f'headers-{index}.d')
    features = (share/'sdk-compile-features.txt').read_text()
    results.append({'package':str(package),'output':result,'model':model,'nativeSdkCompileFeatures':features,'pkgConfigFlags':flags})
assert results[0]['output'].split(':')[-1] != results[1]['output'].split(':')[-1]
assert results[0]['model']['libraryHashes'] != results[1]['model']['libraryHashes']
from importlib.util import spec_from_file_location, module_from_spec
loader = spec_from_file_location('generator',spec['generator']); generator = module_from_spec(loader); loader.loader.exec_module(generator)
def private_bundle(name):
    target = Path(name)
    shutil.copytree(results[0]['model']['resources'],target)
    for path in target.rglob('*'):
        if path.is_dir(): path.chmod(0o755)
        elif not path.is_symlink(): path.chmod(0o644)
    return target

def generate(target,output):
    generator.generate({'resources':str(target),'sdk':results[0]['model']['sdk'], 'inspector':spec['inspector'],'name':'capnp_proof','version':'1.0.0'},Path(output))
incomplete = private_bundle('incomplete')
(incomplete/'files/common/value.capnp').unlink()
try:
    generate(incomplete,'unexpected')
except subprocess.CalledProcessError:
    pass
else:
    raise AssertionError('native capnp accepted missing import')
corrupt = private_bundle('corrupt')
changed = corrupt/'files/common/value.capnp'
changed.write_text(changed.read_text()+'# uncaptured change\n')
try:
    generate(corrupt,'unexpected-corrupt')
except ValueError as error:
    assert 'does not match captured resources' in str(error)
else:
    raise AssertionError('accepted changed schema against captured hash')
shadow = private_bundle('shadow')
(shadow/'files/capnp').mkdir()
foreign = shadow/'files/capnp/c++.capnp'
foreign.write_bytes((Path(results[0]['model']['sdk'])/'include/capnp/c++.capnp').read_bytes()+b'# incompatible SDK shadow\n')
catalog = json.loads((shadow/'catalog.json').read_text());catalog['files']['capnp/c++.capnp']={'sha256':hashlib.sha256(foreign.read_bytes()).hexdigest(),'size':foreign.stat().st_size};(shadow/'catalog.json').write_text(json.dumps(catalog))
try:
    generate(shadow,'unexpected-shadow')
except ValueError as error:
    assert 'shadows a different SDK schema' in str(error)
else:
    raise AssertionError('accepted incompatible SDK schema shadow')
(out/'verification.json').write_text(json.dumps({'consumers':results,'missingImportRejected':True,'changedSchemaRejected':True,'sdkShadowRejected':True},indent=2)+'\n')
