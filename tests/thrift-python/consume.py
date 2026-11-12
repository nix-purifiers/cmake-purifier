# SPDX-License-Identifier: MIT
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import zipfile

spec = json.loads(Path(sys.argv[1]).read_text())
out = Path(sys.argv[2]);out.mkdir()
results = []
for index, case in enumerate(spec['versions']):
    model = json.loads((Path(case['proof'])/'thrift-python.json').read_text())
    for name, expected in model['capturedHashes'].items():
        assert hashlib.sha256((Path(model['resources'])/'files'/name).read_bytes()).hexdigest()==expected
    wheel = Path(case['package'])/model['wheel']
    assert hashlib.sha256(wheel.read_bytes()).hexdigest()==model['wheelSha256']
    for provided in Path(case['runtimeRepository']).glob('*.whl'):
        assert provided.read_bytes()==(Path(case['repository'])/provided.name).read_bytes()
    destination=Path(f'installed-{index}').resolve()
    subprocess.run([sys.executable,'-m','pip','--isolated','install','--no-index','--no-compile','--find-links',case['repository'],'--target',str(destination),'thrift-proof'],check=True)
    program='''import hashlib,importlib.metadata,json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from main_value.ttypes import Envelope
from common_value.ttypes import Value
from main_value import AnswerService
from thrift.transport.TTransport import TMemoryBuffer
from thrift.protocol.TBinaryProtocol import TBinaryProtocol,TBinaryProtocolAccelerated
import thrift,main_value.ttypes,common_value.ttypes
def roundtrip(protocol):
 buffer=TMemoryBuffer();Envelope(value=Value(answer=42)).write(protocol(buffer));wire=buffer.getvalue()
 decoded=Envelope();decoded.read(protocol(TMemoryBuffer(wire)));assert decoded.value.answer==42
 return wire.hex()
native_path=None
if sys.argv[2]=='1':
 import thrift.protocol.fastbinary as fastbinary
 native_path=fastbinary.__file__
 accelerated_protocol=TBinaryProtocolAccelerated(TMemoryBuffer())
 assert accelerated_protocol._fast_encode is not None and accelerated_protocol._fast_decode is not None
wire=roundtrip(TBinaryProtocol);accelerated=roundtrip(TBinaryProtocolAccelerated);assert wire==accelerated
request=TMemoryBuffer();AnswerService.Client(TBinaryProtocol(request)).send_answer(1)
class Handler:
 def answer(self,delta):return 42+delta
response=TMemoryBuffer();AnswerService.Processor(Handler()).process(TBinaryProtocol(TMemoryBuffer(request.getvalue())),TBinaryProtocol(response))
result=AnswerService.Client(TBinaryProtocol(TMemoryBuffer(response.getvalue()))).recv_answer();assert result==43
base=Path(sys.argv[1]);files={str(p.relative_to(base)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(base.rglob('*')) if p.is_file() and (p.suffix=='.py' or p.name.endswith(('.so','.pyd','.dylib')))}
print(json.dumps({'answer':42,'rpc':result,'wire':wire,'acceleratedWire':accelerated,'nativeExtension':native_path,'files':files,'version':importlib.metadata.version('thrift-proof'),'runtimeVersion':importlib.metadata.version('thrift'),'requirements':importlib.metadata.requires('thrift-proof')}))
'''
    actual=json.loads(subprocess.check_output([sys.executable,'-I','-c',program,str(destination),'1' if model['runtime']['nativeExtensions'] else '0'],text=True))
    for name,expected in model['generatedHashes'].items():assert actual['files'][name]==expected
    for name,expected in model['runtime']['runtimeSources'].items():assert actual['files'][name]==expected
    for name,expected in model['runtime']['nativeExtensions'].items():assert actual['files'][name]==expected
    assert actual['runtimeVersion'] in str(actual['requirements']) and '+nix' in actual['version'] and '+nix' in actual['runtimeVersion']
    assert model['nativeModels']['value']['structs'][0]['fields'][0]['key']==index+1
    flags=subprocess.check_output(['pkg-config','--cflags','--libs',case['cpp']+'/lib/pkgconfig/thrift_proof.pc'],text=True)
    binary=Path(f'cpp-{index}')
    subprocess.run(['c++',str(spec['cppConsumer']),'-o',str(binary),*spec['dlLibs'],*shlex.split(flags)],check=True)
    cpp=subprocess.check_output(['./'+str(binary)],text=True).splitlines()
    assert cpp[0]=='42:'+actual['wire'] and cpp[1]=='43'
    assert Path(cpp[2]).resolve().parent==Path(case['cpp'])/'lib'
    assert Path(cpp[3]).resolve().parent==Path(model['sdk'])/'lib'
    results.append({'case':case,'model':model,'actual':actual,'cpp':cpp})
assert results[0]['actual']['wire']!=results[1]['actual']['wire']
assert results[0]['actual']['version']!=results[1]['actual']['version']
# Removing the supplied SDK runtime must fail through the real offline installer.
missing=Path('missing-runtime');missing.mkdir()
for wheel in Path(spec['versions'][0]['repository']).glob('thrift_proof-*.whl'):shutil.copy(wheel,missing/wheel.name)
run=subprocess.run([sys.executable,'-m','pip','--isolated','install','--no-index','--find-links',str(missing),'--target',str(Path('unexpected-runtime').resolve()),'thrift-proof'],capture_output=True,text=True)
assert run.returncode and 'No matching distribution found' in run.stderr and 'thrift==' in run.stderr
(out/'missing-runtime.stderr').write_text(run.stderr)
from importlib.util import spec_from_file_location,module_from_spec
loader=spec_from_file_location('generator',spec['generator']);generator=module_from_spec(loader);loader.loader.exec_module(generator)
model=results[0]['model']
def bundle(name):
 p=Path(name).resolve();shutil.copytree(model['resources'],p)
 for path in p.rglob('*'):
  if path.is_dir():path.chmod(0o755)
  elif not path.is_symlink():path.chmod(0o644)
 return p
def attempt(name,resources):
 import os
 folder=Path(name).resolve();folder.mkdir();destination=folder/'wheel';proof=folder/'proof';destination.mkdir();proof.mkdir();prior=Path.cwd()
 try:
  os.chdir(folder)
  generator.generate({'resources':str(resources),'sdk':model['sdk'],'runtimeProof':model['runtimeProof'],'name':'thrift-proof','version':'1.0.0'},destination,proof)
 finally:os.chdir(prior)
missing=bundle('missing-import');(missing/'files/common/value.thrift').unlink()
try:attempt('unexpected-import',missing)
except subprocess.CalledProcessError as error:
 assert 'common/value.thrift' in error.stdout+error.stderr or 'value.Value' in error.stdout+error.stderr
 (out/'missing-import.stderr').write_text(error.stderr)
 (out/'missing-import.stdout').write_text(error.stdout)
else:raise AssertionError('native compiler accepted missing schema import')
corrupt=bundle('changed-source');path=corrupt/'files/common/value.thrift';path.write_text(path.read_text()+'// uncaptured source change\n')
try:attempt('unexpected-source',corrupt)
except ValueError as error:assert 'does not match captured resource hash' in str(error)
else:raise AssertionError('accepted mismatched captured source hash')
outside=bundle('outside-import');foreign=Path('external/value.thrift').resolve();foreign.parent.mkdir();foreign.write_text((outside/'files/common/value.thrift').read_text().replace('i32','i64'))
path=outside/'files/main.thrift';path.write_text(path.read_text().replace('common/value.thrift',str(foreign)));catalog=json.loads((outside/'catalog.json').read_text());catalog['files']['main.thrift']['sha256']=hashlib.sha256(path.read_bytes()).hexdigest();(outside/'catalog.json').write_text(json.dumps(catalog))
try:attempt('unexpected-outside',outside)
except ValueError as error:assert 'native compiler input escapes' in str(error)
else:raise AssertionError('accepted outside native input sharing captured program basename')
collision=bundle('runtime-collision');path=collision/'files/common/value.thrift';path.write_text(path.read_text().replace('namespace py common_value','namespace py thrift'));catalog=json.loads((collision/'catalog.json').read_text());catalog['files']['common/value.thrift']['sha256']=hashlib.sha256(path.read_bytes()).hexdigest();(collision/'catalog.json').write_text(json.dumps(catalog))
try:attempt('unexpected-collision',collision)
except ValueError as error:assert 'collides with native Thrift runtime' in str(error)
else:raise AssertionError('accepted generated namespace shadowing selected SDK runtime')
overlap=bundle('generated-collision');path=overlap/'files/main.thrift';path.write_text(path.read_text().replace('namespace py main_value','namespace py common_value'));catalog=json.loads((overlap/'catalog.json').read_text());catalog['files']['main.thrift']['sha256']=hashlib.sha256(path.read_bytes()).hexdigest();(overlap/'catalog.json').write_text(json.dumps(catalog))
try:attempt('unexpected-generated-collision',overlap)
except ValueError as error:assert 'native generated Python outputs collide' in str(error)
else:raise AssertionError('accepted distinct programs overwriting the same generated module')
(out/'verification.json').write_text(json.dumps({'consumers':results,'missingRuntimeRejected':True,'missingImportRejected':True,'changedSourceRejected':True,'outsideCompilerInputRejected':True,'runtimeNamespaceCollisionRejected':True,'generatedModuleCollisionRejected':True},indent=2)+'\n')
