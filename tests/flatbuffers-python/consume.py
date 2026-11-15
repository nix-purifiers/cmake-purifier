# SPDX-License-Identifier: MIT
import hashlib
import json
import shutil
import os
from pathlib import Path
import shlex
import subprocess
import sys

spec=json.loads(Path(sys.argv[1]).read_text());out=Path(sys.argv[2]);out.mkdir();results=[]
for index,case in enumerate(spec['versions']):
    model=json.loads((Path(case['proof'])/'flatbuffers-python.json').read_text())
    for name,expected in model['schemaHashes'].items():
        assert hashlib.sha256((Path(model['resources'])/'files'/name).read_bytes()).hexdigest()==expected
    for wheel in Path(case['runtimeRepository']).glob('*.whl'):
        assert wheel.read_bytes()==(Path(case['repository'])/wheel.name).read_bytes()
    flags=subprocess.check_output(['pkg-config','--cflags',case['cpp']+'/lib/pkgconfig/schema_proof.pc'],text=True)
    binary=Path(f'cpp-{index}').resolve()
    subprocess.run(['c++','-std=c++11',f'-DEXPECT_BITS={case["bits"]}',spec['cppConsumer'],'-o',str(binary),*shlex.split(flags)],check=True)
    cpp=subprocess.check_output([str(binary)],text=True).strip().split(':');assert cpp[:2]==['42',str(case['bits'])]
    destination=Path(f'installed-{index}').resolve()
    subprocess.run([sys.executable,'-m','pip','--isolated','install','--no-index','--no-compile','--find-links',case['repository'],'--target',str(destination),'flatbuffers-proof'],check=True)
    program='''import hashlib,importlib,importlib.metadata,json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1]);base=Path(sys.argv[1]);cpp=bytes.fromhex(sys.argv[2])
import flatbuffers
v=importlib.import_module('proof.Value');e=importlib.import_module('proof.Envelope')
assert e.Envelope.GetRootAs(cpp,0).Value().Answer()==42 and e.Envelope.EnvelopeBufferHasIdentifier(cpp,0)
b=flatbuffers.Builder(0);v.ValueStart(b);v.ValueAddAnswer(b,42);value=v.ValueEnd(b);e.EnvelopeStart(b);e.EnvelopeAddValue(b,value);root=e.EnvelopeEnd(b);b.Finish(root,file_identifier=b'PRF1');wire=bytes(b.Output())
assert e.Envelope.GetRootAs(wire,0).Value().Answer()==42
qualified={}
for name,value in [('a.Value',7),('b.Value',8)]:
 m=importlib.import_module(name);builder=flatbuffers.Builder(0);m.ValueStart(builder);m.ValueAddAnswer(builder,value);offset=m.ValueEnd(builder);builder.Finish(offset);assert m.Value.GetRootAs(builder.Output(),0).Answer()==value;qualified[name]=value
origins={}
for name in ['proof.Value','proof.Envelope','a.Value','b.Value','flatbuffers','flatbuffers.builder','flatbuffers.table']:
 p=Path(sys.modules[name].__file__).resolve();assert p.is_relative_to(base);origins[name]={'relative':str(p.relative_to(base)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
print(json.dumps({'answer':42,'cppDecoded':42,'qualifiedTypes':qualified,'wire':wire.hex(),'origins':origins,'version':importlib.metadata.version('flatbuffers-proof'),'runtimeVersion':importlib.metadata.version('flatbuffers'),'requirements':importlib.metadata.requires('flatbuffers-proof')}))
'''
    actual=json.loads(subprocess.check_output([sys.executable,'-I','-c',program,str(destination),cpp[2]],text=True))
    objects=model['nativeSchemas']['main.fbs']['schema']['objects'];assert {x['name'] for x in objects}>={'a.Value','b.Value','proof.Value','proof.Envelope'}
    answer=next(x for x in objects if x['name']=='proof.Value')['fields'][0]
    assert answer['type']['base_type']==('Int' if case['bits']==32 else 'Long')
    expected=model['generatedHashes']|model['runtime']['runtimeSources']
    for origin in actual['origins'].values():assert origin['sha256']==expected[origin['relative']]
    buffer=Path(f'python-{index}.bin');buffer.write_bytes(bytes.fromhex(actual['wire']))
    assert subprocess.check_output([str(binary),str(buffer)],text=True).strip()=='42'
    assert actual['runtimeVersion'] in str(actual['requirements']) and '+nix' in actual['version']
    results.append({'case':case,'model':model,'actual':actual,'cpp':cpp})
assert results[0]['actual']['wire']!=results[1]['actual']['wire']
assert results[0]['actual']['version']!=results[1]['actual']['version']
# An ordinary offline installer must require the selected runtime provider.
missing=Path('missing-runtime');missing.mkdir()
for wheel in Path(spec['versions'][0]['repository']).glob('flatbuffers_proof-*.whl'):shutil.copy(wheel,missing/wheel.name)
run=subprocess.run([sys.executable,'-m','pip','--isolated','install','--no-index','--find-links',str(missing),'--target',str(Path('unexpected-runtime').resolve()),'flatbuffers-proof'],capture_output=True,text=True)
assert run.returncode and 'No matching distribution found' in run.stderr and 'flatbuffers==' in run.stderr
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
def update(bundle,logical,text):
 path=bundle/'files'/logical;path.write_text(text);catalog=json.loads((bundle/'catalog.json').read_text())
 record=dict(next(iter(catalog['files'].values())));record['sha256']=hashlib.sha256(path.read_bytes()).hexdigest();catalog['files'][logical]=record;(bundle/'catalog.json').write_text(json.dumps(catalog))
def attempt(name,resources):
 folder=Path(name).resolve();folder.mkdir();destination=folder/'wheel';proof=folder/'proof';destination.mkdir();proof.mkdir();prior=Path.cwd()
 try:
  os.chdir(folder)
  generator.generate({'resources':str(resources),'sdk':model['sdk'],'sdkSource':str(Path(model['reflectionSchema']).parent.parent),'runtimeProof':model['runtimeProof'],'name':'flatbuffers-proof','version':'1.0.0'},destination,proof)
 finally:os.chdir(prior)
missing=bundle('missing-import');(missing/'files/common/value.fbs').unlink()
try:attempt('unexpected-import',missing)
except subprocess.CalledProcessError:pass
else:raise AssertionError('native compiler accepted missing schema import')
corrupt=bundle('changed-source');path=corrupt/'files/common/value.fbs';path.write_text(path.read_text()+'// changed uncaptured source\n')
try:attempt('unexpected-source',corrupt)
except ValueError as error:assert 'differs from captured hash' in str(error)
else:raise AssertionError('accepted changed source against captured hash')
outside=bundle('outside-import');foreign=Path('external/value.fbs').resolve();foreign.parent.mkdir();foreign.write_text((outside/'files/common/value.fbs').read_text().replace('answer:int','answer:long'))
update(outside,'main.fbs',(outside/'files/main.fbs').read_text().replace('common/value.fbs',os.path.relpath(foreign,outside/'files')))
try:attempt('unexpected-outside',outside)
except ValueError as error:assert 'native schema input escapes' in str(error)
else:raise AssertionError('accepted outside native schema input')
collision=bundle('runtime-collision');update(collision,'common/value.fbs',(collision/'files/common/value.fbs').read_text().replace('namespace proof','namespace flatbuffers'));update(collision,'main.fbs',(collision/'files/main.fbs').read_text().replace('value:Value','value:flatbuffers.Value'))
try:attempt('unexpected-collision',collision)
except ValueError as error:assert 'namespace collides with native FlatBuffers runtime' in str(error)
else:raise AssertionError('accepted generated package shadowing native runtime')
overlap=bundle('generated-collision');update(overlap,'other.fbs','namespace proof; table Value { other:int; }\n');catalog=json.loads((overlap/'catalog.json').read_text());catalog['schema']['entrypoints'].append('other.fbs');(overlap/'catalog.json').write_text(json.dumps(catalog))
try:attempt('unexpected-output',overlap)
except ValueError as error:assert 'native generated Python outputs collide' in str(error)
else:raise AssertionError('accepted distinct programs overwriting generated module')
(out/'verification.json').write_text(json.dumps({'consumers':results,'missingRuntimeRejected':True,'missingImportRejected':True,'changedSourceRejected':True,'outsideCompilerInputRejected':True,'runtimeNamespaceCollisionRejected':True,'generatedModuleCollisionRejected':True},indent=2)+'\n')
