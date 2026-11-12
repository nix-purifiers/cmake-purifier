# SPDX-License-Identifier: MIT
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
spec=json.loads(Path(sys.argv[1]).read_text());out=Path(sys.argv[2]);out.mkdir();source=Path(__file__).parent;results=[]
for index,name in enumerate(spec['packages']):
 package=Path(name);share=package/'share/thrift_proof';model=json.loads((share/'thrift-products.json').read_text())
 for group,base in [('capturedHashes',Path(model['resources'])/'files'),('generatedHashes',share),('libraryHashes',package)]:
  for path,expected in model[group].items():assert hashlib.sha256((base/path).read_bytes()).hexdigest()==expected
 assert model['nativeModels']['main']['includes']==['value']
 assert model['nativeModels']['value']['structs'][0]['fields'][0]['key']==index+1
 build=Path(f'build-{index}')
 subprocess.run(['cmake','-S',str(source),'-B',str(build),'-G','Ninja','-DCMAKE_PREFIX_PATH='+str(package)+';'+model['sdk']],check=True)
 subprocess.run(['cmake','--build',str(build)],check=True)
 lines=subprocess.check_output([str(build/'consumer')],text=True).splitlines();assert lines[0].startswith('42:') and lines[1]=='43'
 assert Path(lines[2]).resolve().parent==(package/'lib').resolve()
 assert Path(lines[3]).resolve().parent==(Path(model['sdk'])/'lib').resolve()
 flags=subprocess.check_output(['pkg-config','--cflags','--libs',str(package/'lib/pkgconfig/thrift_proof.pc')],text=True)
 binary=Path(f'pkg-consumer-{index}')
 subprocess.run(['c++','-std=c++98','-MD','-MF',f'headers-{index}.d',str(source/'consumer.cpp'),'-o',str(binary),*spec['dlLibs'],*shlex.split(flags)],check=True)
 assert subprocess.check_output(['./'+str(binary)],text=True).splitlines()==lines
 deps=Path(f'headers-{index}.d').read_text();assert str(package/'include/main_types.h') in deps and str(package/'include/value_types.h') in deps and model['sdk']+'/include/thrift/' in deps
 shutil.copy(build/'compile_commands.json',out/f'compile_commands-{index}.json');shutil.copy(f'headers-{index}.d',out/f'headers-{index}.d')
 results.append({'package':str(package),'lines':lines,'model':model,'sdkStandard':(share/'sdk-standard.txt').read_text(),'pkgConfigFlags':flags})
assert results[0]['lines'][0]!=results[1]['lines'][0]
from importlib.util import spec_from_file_location,module_from_spec
loader=spec_from_file_location('generator',spec['generator']);generator=module_from_spec(loader);loader.loader.exec_module(generator)
def bundle(name):
 p=Path(name);shutil.copytree(results[0]['model']['resources'],p)
 for path in p.rglob('*'):
  if path.is_dir():path.chmod(0o755)
  elif not path.is_symlink():path.chmod(0o644)
 return p
missing=bundle('missing');(missing/'files/common/value.thrift').unlink()
try:generator.generate({'resources':str(missing),'sdk':results[0]['model']['sdk'],'name':'thrift_proof','version':'1.0.0'},Path('unexpected-missing'))
except subprocess.CalledProcessError:pass
else:raise AssertionError('native Thrift accepted missing import')
corrupt=bundle('corrupt');p=corrupt/'files/common/value.thrift';p.write_text(p.read_text()+'// uncaptured change\n')
try:generator.generate({'resources':str(corrupt),'sdk':results[0]['model']['sdk'],'name':'thrift_proof','version':'1.0.0'},Path('unexpected-corrupt'))
except ValueError as error:assert 'does not match captured resource hash' in str(error)
else:raise AssertionError('accepted changed schema against captured hash')
outside=bundle('outside');external=Path('external');external.mkdir();foreign=external/'value.thrift';foreign.write_text((outside/'files/common/value.thrift').read_text().replace('i32','i64'))
p=outside/'files/main.thrift';p.write_text(p.read_text().replace('common/value.thrift',str(foreign.resolve())))
catalog=json.loads((outside/'catalog.json').read_text());catalog['files']['main.thrift']['sha256']=hashlib.sha256(p.read_bytes()).hexdigest();(outside/'catalog.json').write_text(json.dumps(catalog))
try:generator.generate({'resources':str(outside),'sdk':results[0]['model']['sdk'],'name':'thrift_proof','version':'1.0.0'},Path('unexpected-outside'))
except ValueError as error:assert 'native compiler input escapes' in str(error)
else:raise AssertionError('accepted outside compiler input with matching program basename')
ambiguous=bundle('ambiguous');p=ambiguous/'files/other/value.thrift';p.parent.mkdir();p.write_text('struct Other { 1: i32 value }\n');catalog=json.loads((ambiguous/'catalog.json').read_text());catalog['files']['other/value.thrift']={'sha256':hashlib.sha256(p.read_bytes()).hexdigest()};(ambiguous/'catalog.json').write_text(json.dumps(catalog))
try:generator.generate({'resources':str(ambiguous),'sdk':results[0]['model']['sdk'],'name':'thrift_proof','version':'1.0.0'},Path('unexpected-ambiguous'))
except ValueError as error:assert 'ambiguous native C++ program output name' in str(error)
else:raise AssertionError('accepted colliding native output basenames')
(out/'verification.json').write_text(json.dumps({'consumers':results,'missingImportRejected':True,'changedSchemaRejected':True,'outsideCompilerInputRejected':True,'ambiguousOutputRejected':True},indent=2)+'\n')
