# SPDX-License-Identifier: MIT
import hashlib,json,os,shlex,shutil,subprocess,sys
from pathlib import Path
spec=json.loads(Path(sys.argv[1]).read_text());out=Path(sys.argv[2]);out.mkdir();results=[]
for index,case in enumerate(spec['versions']):
 package=Path(case['package']);model=json.loads((package/'thrift-go.json').read_text());repository=Path(case['repository']);catalog=json.loads((repository/'.catalog').read_text());versions={m['path']:m['version'] for m in catalog['modules']};assert set(versions)=={'example.org/schemas',model['runtimeModule']['path']}
 root=Path(str(index)).resolve();root.mkdir();shutil.copyfile(spec['consumer'],root/'main.go');env=dict(os.environ,HOME=str(root/'home'),GOPATH=str(root/'go'),GOCACHE=str(root/'cache'),GOMODCACHE=str(root/'modcache'),GOTOOLCHAIN='local',GOWORK='off',GOSUMDB='off',GOPROXY='file://'+str(repository)+',off');Path(env['HOME']).mkdir()
 def run(args):return subprocess.run([str(a) for a in args],cwd=root,env=env,check=True,capture_output=True,text=True).stdout
 run(['go','mod','init','example.org/consumer']);run(['go','get','example.org/schemas/main_value@'+versions['example.org/schemas']]);run(['go','build','-o',str(root/'consumer'),'.']);actual=json.loads(run([root/'consumer']))
 assert actual['answer']==42 and actual['rpc']==43
 assert model['nativeModels']['value']['structs'][0]['fields'][0]['key']==index+1
 runtime_proxy=Path(case['runtimeCatalog']).parent;provided=[]
 for path in runtime_proxy.rglob('*'):
  if path.is_file() and path.name!='.catalog':
   relative=path.relative_to(runtime_proxy);assert path.read_bytes()==(repository/relative).read_bytes();provided.append(str(relative))
 assert provided
 for kind,module,base in [('owned','example.org/schemas',package/'module'),('runtime',model['runtimeModule']['path'],Path(model['sdkSource']))]:
  origin=Path(actual[kind]);expected_root=Path(env['GOMODCACHE'])/(module+'@'+versions[module]);assert origin.is_relative_to(expected_root);relative=origin.relative_to(expected_root);assert origin.read_bytes()==(base/relative).read_bytes()
 flags=subprocess.check_output(['pkg-config','--cflags','--libs',case['cpp']+'/lib/pkgconfig/thrift_proof.pc'],text=True);binary=root/'cpp';subprocess.run(['c++',spec['cppConsumer'],'-o',str(binary),*spec['dlLibs'],*shlex.split(flags)],check=True);cpp=subprocess.check_output([binary],text=True).splitlines();assert cpp[0]=='42:'+actual['wire'] and cpp[1]=='43'
 (out/f'{index}-go.sum').write_bytes((root/'go.sum').read_bytes());info=run(['go','version','-m',root/'consumer']);assert all(v in info for v in versions.values());(out/f'{index}-build-info.txt').write_text(info)
 for logical,expected in model['capturedHashes'].items():assert hashlib.sha256((Path(model['resources'])/'files'/logical).read_bytes()).hexdigest()==expected
 for logical,expected in model['generatedHashes'].items():assert hashlib.sha256((package/'module'/logical).read_bytes()).hexdigest()==expected
 results.append({'case':case,'model':model,'actual':actual,'modules':versions,'cpp':cpp,'providedRuntimeFilesUnchanged':provided})
assert results[0]['actual']['wire']!=results[1]['actual']['wire'];assert results[0]['modules']['example.org/schemas']!=results[1]['modules']['example.org/schemas'];assert results[0]['modules'][results[0]['model']['runtimeModule']['path']]==results[1]['modules'][results[1]['model']['runtimeModule']['path']]
# A genuine Go importer must reject a repository without the required SDK module.
model=results[0]['model'];repository=Path(spec['versions'][0]['repository']);missing=Path('missing-runtime').resolve();missing.mkdir();owned=repository/'example.org/schemas';shutil.copytree(owned,missing/'example.org/schemas')
root=Path('missing-client').resolve();root.mkdir();(root/'main.go').write_text('package main; import _ "example.org/schemas/main_value"; func main(){}\n');env=dict(os.environ,HOME=str(root/'home'),GOPATH=str(root/'go'),GOCACHE=str(root/'cache'),GOMODCACHE=str(root/'modcache'),GOTOOLCHAIN='local',GOWORK='off',GOSUMDB='off',GOPROXY='file://'+str(missing)+',off');Path(env['HOME']).mkdir();subprocess.run(['go','mod','init','example.org/missing'],cwd=root,env=env,check=True,capture_output=True)
failed=subprocess.run(['go','get','example.org/schemas/main_value@'+results[0]['modules']['example.org/schemas']],cwd=root,env=env,capture_output=True,text=True)
assert failed.returncode and model['runtimeModule']['path'] in failed.stderr;(out/'missing-runtime.stderr').write_text(failed.stderr)
from importlib.util import spec_from_file_location,module_from_spec
loader=spec_from_file_location('generator',spec['generator']);generator=module_from_spec(loader);loader.loader.exec_module(generator)
def bundle(name):
 p=Path(name).resolve();shutil.copytree(model['resources'],p)
 for path in p.rglob('*'):
  if path.is_dir():path.chmod(0o755)
  elif not path.is_symlink():path.chmod(0o644)
 return p
def update(bundle,logical,text):
 path=bundle/'files'/logical;path.write_text(text);catalog=json.loads((bundle/'catalog.json').read_text());record=dict(next(iter(catalog['files'].values())));record['sha256']=hashlib.sha256(path.read_bytes()).hexdigest();catalog['files'][logical]=record;(bundle/'catalog.json').write_text(json.dumps(catalog))
def attempt(name,resources):
 folder=Path(name).resolve();folder.mkdir();prior=Path.cwd()
 try:
  os.chdir(folder)
  generator.generate({'resources':str(resources),'sdk':model['sdk'],'sdkSource':model['sdkSource'],'runtimeCatalog':spec['runtimeCatalog'],'modulePath':'example.org/schemas'},folder/'out')
 finally:os.chdir(prior)
missing=bundle('missing-import');(missing/'files/common/value.thrift').unlink()
try:attempt('unexpected-import',missing)
except subprocess.CalledProcessError:pass
else:raise AssertionError('native compiler accepted absent schema import')
corrupt=bundle('changed-source');path=corrupt/'files/common/value.thrift';path.write_text(path.read_text()+'// uncaptured source change\n')
try:attempt('unexpected-source',corrupt)
except ValueError as error:assert 'does not match captured resource hash' in str(error)
else:raise AssertionError('accepted changed captured schema')
outside=bundle('outside-import');foreign=Path('external/value.thrift').resolve();foreign.parent.mkdir();foreign.write_text((outside/'files/common/value.thrift').read_text().replace('i32','i64'));update(outside,'main.thrift',(outside/'files/main.thrift').read_text().replace('common/value.thrift',str(foreign)))
try:attempt('unexpected-outside',outside)
except ValueError as error:assert 'native compiler input escapes' in str(error)
else:raise AssertionError('accepted outside compiler input')
overlap=bundle('output-collision');update(overlap,'other.thrift','namespace go common_value\nstruct Value { 1: i64 other }\n');catalog=json.loads((overlap/'catalog.json').read_text());catalog['schema']['entrypoints'].append('other.thrift');(overlap/'catalog.json').write_text(json.dumps(catalog))
attempt('duplicate-go-types',overlap)
duplicate=Path('duplicate-go-types/out/module').resolve();env=dict(os.environ,HOME=str(duplicate/'home'),GOPATH=str(duplicate/'go'),GOCACHE=str(duplicate/'cache'),GOMODCACHE=str(duplicate/'modcache'),GOTOOLCHAIN='local',GOWORK='off',GOSUMDB='off',GOPROXY='file://'+str(repository)+',off');Path(env['HOME']).mkdir()
subprocess.run(['go','mod','tidy'],cwd=duplicate,env=env,check=True,capture_output=True)
failed=subprocess.run(['go','build','./...'],cwd=duplicate,env=env,capture_output=True,text=True)
assert failed.returncode and 'redeclared' in failed.stderr and 'Value' in failed.stderr;(out/'duplicate-types.stderr').write_text(failed.stderr)
ambiguous=bundle('ambiguous-program');path=ambiguous/'files/other/value.thrift';path.parent.mkdir();path.write_text('struct Other { 1: i32 other }\n');catalog=json.loads((ambiguous/'catalog.json').read_text());catalog['files']['other/value.thrift']={'sha256':hashlib.sha256(path.read_bytes()).hexdigest()};(ambiguous/'catalog.json').write_text(json.dumps(catalog))
try:attempt('unexpected-ambiguous',ambiguous)
except ValueError as error:assert 'ambiguous native program output name' in str(error)
else:raise AssertionError('accepted ambiguous native program source names')
(out/'verification.json').write_text(json.dumps({'consumers':results,'missingRuntimeRejected':True,'missingImportRejected':True,'changedSourceRejected':True,'outsideCompilerInputRejected':True,'ambiguousProgramRejected':True,'duplicateGoTypesRejected':True},indent=2)+'\n')
