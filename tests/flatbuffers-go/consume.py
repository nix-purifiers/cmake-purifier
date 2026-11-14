# SPDX-License-Identifier: MIT
import hashlib,json,os,shlex,shutil,subprocess,sys
from pathlib import Path
spec=json.loads(Path(sys.argv[1]).read_text());out=Path(sys.argv[2]);out.mkdir();results=[]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for index,case in enumerate(spec['versions']):
 package=Path(case['generated']);model=json.loads((package/'flatbuffers-go.json').read_text());repository=Path(case['repository']);catalog=json.loads((repository/'.catalog').read_text());versions={m['path']:m['version'] for m in catalog['modules']};assert set(versions)=={'example.org/schemas',model['runtimeModule']['path']}
 root=Path(str(index)).resolve();root.mkdir();shutil.copyfile(spec['consumer'],root/'main.go');env=dict(os.environ,HOME=str(root/'home'),GOPATH=str(root/'go'),GOCACHE=str(root/'cache'),GOMODCACHE=str(root/'modcache'),GOTOOLCHAIN='local',GOWORK='off',GOSUMDB='off',GOPROXY='file://'+str(repository)+',off');Path(env['HOME']).mkdir()
 def run(args):return subprocess.run([str(a) for a in args],cwd=root,env=env,check=True,capture_output=True,text=True).stdout
 run(['go','mod','init','example.org/consumer']);run(['go','get','example.org/schemas/proof@'+versions['example.org/schemas']]);run(['go','build','-o',str(root/'consumer'),'.'])
 flags=shlex.split(subprocess.check_output(['pkg-config','--cflags',case['cpp']+'/lib/pkgconfig/schema_proof.pc'],text=True));cpp=root/'cpp';subprocess.run(['c++','-std=c++11',f'-DEXPECT_BITS={case["bits"]}',spec['cppConsumer'],'-o',str(cpp),*flags],check=True);cpp_result=subprocess.check_output([cpp],text=True).strip().split(':');assert cpp_result[:2]==['42',str(case['bits'])]
 buffer=root/'go.bin';actual=json.loads(run([root/'consumer',cpp_result[2],buffer]));assert actual['answer']==42 and actual['bits']==case['bits'] and actual['other']==44 and actual['qualified']==[7,8];assert subprocess.check_output([cpp,buffer],text=True).strip()=='42'
 for kind,module,base in [('owned','example.org/schemas',package/'module'),('runtime',model['runtimeModule']['path'],Path(model['runtimeSource']))]:
  origin=Path(actual[kind]);expected_root=Path(env['GOMODCACHE'])/(module+'@'+versions[module]);assert origin.is_relative_to(expected_root);relative=origin.relative_to(expected_root);assert origin.read_bytes()==(base/relative).read_bytes()
  for path in base.rglob('*.go'):assert path.read_bytes()==(expected_root/path.relative_to(base)).read_bytes()
 for logical,expected in model['schemaHashes'].items():assert sha(Path(model['resources'])/'files'/logical)==expected
 for logical,expected in model['generatedHashes'].items():assert sha(package/'module'/logical)==expected
 (out/f'{index}-go.sum').write_bytes((root/'go.sum').read_bytes());info=run(['go','version','-m',root/'consumer']);assert all(v in info for v in versions.values());(out/f'{index}-build-info.txt').write_text(info)
 runtime_proxy=Path(case['runtimeCatalog']).parent;provided=[]
 for path in runtime_proxy.rglob('*'):
  if path.is_file() and path.name!='.catalog':
   relative=path.relative_to(runtime_proxy);assert path.read_bytes()==(repository/relative).read_bytes();provided.append(str(relative))
 assert provided
 for path in (Path(model['sdkSource'])/'go').rglob('*.go'):assert path.read_bytes()==(Path(model['runtimeSource'])/path.relative_to(Path(model['sdkSource'])/'go')).read_bytes()
 results.append({'case':case,'model':model,'actual':actual,'modules':versions,'cpp':cpp_result,'providedRuntimeFilesUnchanged':provided})
assert results[0]['actual']['wire']!=results[1]['actual']['wire'];assert results[0]['modules']['example.org/schemas']!=results[1]['modules']['example.org/schemas']
# Exercise the actual native generator against incomplete and conflicting inputs.
from importlib.util import spec_from_file_location,module_from_spec
loader=spec_from_file_location('generator',spec['generator']);generator=module_from_spec(loader);loader.loader.exec_module(generator)
model=results[0]['model'];controls={}
def bundle(name):
 p=Path(name).resolve();shutil.copytree(model['resources'],p)
 for path in p.rglob('*'):
  if path.is_dir():path.chmod(0o755)
  elif not path.is_symlink():path.chmod(0o644)
 return p
def update(bundle,logical,text):
 path=bundle/'files'/logical;path.write_text(text);catalog=json.loads((bundle/'catalog.json').read_text())
 record=dict(next(iter(catalog['files'].values())));record['sha256']=sha(path);catalog['files'][logical]=record;(bundle/'catalog.json').write_text(json.dumps(catalog))
def attempt(name,resources):
 folder=Path(name).resolve();folder.mkdir();prior=Path.cwd()
 try:
  os.chdir(folder)
  generator.generate({'resources':str(resources),'sdk':model['sdk'],'sdkSource':str(Path(model['reflectionSchema']).parent.parent),'runtimeSource':model['runtimeSource'],'runtimeCatalog':spec['versions'][0]['runtimeCatalog'],'runtimeModulePath':model['runtimeModule']['path'],'modulePath':'example.org/schemas'},folder/'generated')
 finally:os.chdir(prior)
def reject(name,resources,exception,message=None):
 try:attempt('reject-'+name,resources)
 except exception as error:
  if message:assert message in str(error),str(error)
  controls[name]=str(error)
 else:raise AssertionError('accepted '+name)
missing=bundle('missing-import');(missing/'files/common/value.fbs').unlink();reject('missing-import',missing,subprocess.CalledProcessError)
corrupt=bundle('changed-source');path=corrupt/'files/common/value.fbs';path.write_text(path.read_text()+'// uncaptured change\n');reject('changed-source',corrupt,ValueError,'differs from captured hash')
outside=bundle('outside-import');foreign=Path('external/value.fbs').resolve();foreign.parent.mkdir();foreign.write_text((outside/'files/common/value.fbs').read_text());update(outside,'main.fbs',(outside/'files/main.fbs').read_text().replace('common/value.fbs',os.path.relpath(foreign,outside/'files')));reject('outside-import',outside,ValueError,'native schema input escapes')
overlap=bundle('generated-collision');update(overlap,'other.fbs','namespace proof; table Value { other:int; } root_type Value;');reject('generated-collision',overlap,ValueError,'native generated Go outputs collide')
# The native Go consumer must fail when its required runtime module is absent.
repository=Path(spec['versions'][0]['repository']);missing=Path('missing-runtime').resolve();missing.mkdir();shutil.copytree(repository/'example.org/schemas',missing/'example.org/schemas')
root=Path('missing-client').resolve();root.mkdir();(root/'main.go').write_text('package main; import _ "example.org/schemas/proof"; func main(){}\n');env=dict(os.environ,HOME=str(root/'home'),GOPATH=str(root/'go'),GOCACHE=str(root/'cache'),GOMODCACHE=str(root/'modcache'),GOTOOLCHAIN='local',GOWORK='off',GOSUMDB='off',GOPROXY='file://'+str(missing)+',off');Path(env['HOME']).mkdir();subprocess.run(['go','mod','init','example.org/missing'],cwd=root,env=env,check=True,capture_output=True)
failed=subprocess.run(['go','get','example.org/schemas/proof@'+results[0]['modules']['example.org/schemas']],cwd=root,env=env,capture_output=True,text=True)
assert failed.returncode and model['runtimeModule']['path'] in failed.stderr;(out/'missing-runtime.stderr').write_text(failed.stderr);controls['missing-runtime']=failed.stderr
(out/'verification.json').write_text(json.dumps({'consumers':results,'rejectionControls':controls},indent=2)+'\n')
