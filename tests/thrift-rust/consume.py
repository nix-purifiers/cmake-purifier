# SPDX-License-Identifier: MIT
import hashlib,json,os,shlex,shutil,subprocess,sys,tarfile
from pathlib import Path
spec=json.loads(Path(sys.argv[1]).read_text());out=Path(sys.argv[2]);out.mkdir();results=[]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
vendor_inventory={}
for index,case in enumerate(spec['versions']):
 for path in Path(case['nativeVendor']).rglob('*'):
  if path.is_file():
   relative=path.relative_to(Path(case['nativeVendor']));assert path.read_bytes()==(Path(case['vendor'])/relative).read_bytes();vendor_inventory[str(relative)]=sha(path)
 generated=Path(case['generated']);model=json.loads((generated/'thrift-rust.json').read_text());repository=Path(case['repository']);catalog=json.loads((repository/'.catalog').read_text());packages={p['name']:p for p in catalog['packages']};assert 'proof_schemas' in packages and 'thrift' in packages
 project=Path(f'consumer-{index}');subprocess.run(['cargo','init','--bin','--name',f'consumer_{index}','--edition','2021','--vcs','none',str(project)],check=True);(project/'.cargo').mkdir();(project/'.cargo/config.toml').write_text('[source.crates-io]\nreplace-with="provided"\n[source.provided]\nlocal-registry='+json.dumps(str(repository))+'\n')
 subprocess.run(['cargo','add','--offline',*['%s@=%s'%(name,packages[name]['version']) for name in ['proof_schemas','thrift']]],cwd=project,check=True);shutil.copy(spec['consumer'],project/'src/main.rs')
 subprocess.run(['cargo','build','--offline','--locked'],cwd=project,check=True)
 flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs',case['cpp']+'/lib/pkgconfig/thrift_proof.pc'],text=True));cpp=Path(f'cpp-{index}').resolve();subprocess.run(['c++',spec['cppConsumer'],'-o',str(cpp),*spec['dlLibs'],*flags],check=True);cpp_result=subprocess.check_output([cpp],text=True).splitlines();assert cpp_result[0].startswith('42:') and cpp_result[1]=='43'
 wire=cpp_result[0].split(':',1)[1];result=subprocess.check_output([str(project/'target/debug'/f'consumer_{index}'),wire],text=True).strip();assert result=='42:'+wire+':43:7:8'
 assert model['nativeModels']['value']['structs'][0]['fields'][0]['key']==index+1
 for logical,expected in model['generatedHashes'].items():assert sha(generated/'generated'/logical)==expected and (generated/'generated'/logical).read_bytes()==(generated/'crate/src/generated'/logical).read_bytes()
 metadata=json.loads(subprocess.check_output(['cargo','metadata','--offline','--locked','--format-version=1'],cwd=project,text=True));owned=next(p for p in metadata['packages'] if p['name']=='proof_schemas');runtime=next(p for p in metadata['packages'] if p['name']=='thrift');compiled=Path(owned['manifest_path']).parent;sdk=Path(runtime['manifest_path']).parent;deps='\n'.join(p.read_text() for p in (project/'target/debug/deps').glob('proof_schemas-*.d'))
 for name,expected in model['crateSourceHashes'].items():assert sha(compiled/name)==expected and str(compiled/name) in deps
 for path in (Path(model['runtimeSource'])/'src').rglob('*.rs'):assert path.read_bytes()==(sdk/path.relative_to(Path(model['runtimeSource']))).read_bytes()
 for name in ['LICENSE','NOTICE']:assert (sdk/name).read_bytes()==(Path(model['sdkSource'])/'lib/rs'/name).read_bytes()
 for name in ['proof_schemas','thrift']:
  entry=packages[name];archive=repository/entry['archive'];assert sha(archive)==entry['checksum']
  with tarfile.open(archive) as tar:
   source=generated/'crate' if name=='proof_schemas' else Path(model['runtimeSource'])
   for member in tar:
    if '/src/' in member.name and member.isfile():assert tar.extractfile(member).read()==(source/('src/'+member.name.split('/src/',1)[1])).read_bytes()
 (out/f'Cargo-{index}.lock').write_bytes((project/'Cargo.lock').read_bytes());(out/f'depfiles-{index}.txt').write_text(deps);(out/f'metadata-{index}.json').write_text(json.dumps(metadata,indent=2)+'\n');results.append({'case':case,'model':model,'output':result,'cpp':cpp_result,'ownedManifest':owned['manifest_path'],'runtimeManifest':runtime['manifest_path']})
assert results[0]['output']!=results[1]['output']

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
 path=bundle/'files'/logical;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text);catalog=json.loads((bundle/'catalog.json').read_text())
 record=dict(next(iter(catalog['files'].values())));record['sha256']=sha(path);catalog['files'][logical]=record;(bundle/'catalog.json').write_text(json.dumps(catalog))
def attempt(name,resources,runtime=None):
 folder=Path(name).resolve();folder.mkdir();prior=Path.cwd()
 try:
  os.chdir(folder)
  generator.generate({'resources':str(resources),'sdk':model['sdk'],'sdkSource':model['sdkSource'],'runtime':str(runtime or model['runtimeSource']),'runtimeCatalog':str(Path(spec['versions'][0]['repository'])/'.catalog'),'runtimeRepository':spec['versions'][0]['repository'],'name':'proof_schemas'},folder/'generated')
 finally:os.chdir(prior)
def reject(name,resources,exception,message=None,runtime=None):
 try:attempt('reject-'+name,resources,runtime)
 except exception as error:
  if message:assert message in str(error),str(error)
  controls[name]=str(error)
 else:raise AssertionError('accepted '+name)
missing=bundle('missing-import');(missing/'files/common/value.thrift').unlink();reject('missing-import',missing,subprocess.CalledProcessError)
corrupt=bundle('changed-source');path=corrupt/'files/common/value.thrift';path.write_text(path.read_text()+'// uncaptured change\n');reject('changed-source',corrupt,ValueError,'does not match captured resource hash')
outside=bundle('outside-import');foreign=Path('external/value.thrift').resolve();foreign.parent.mkdir();foreign.write_text((outside/'files/common/value.thrift').read_text());update(outside,'main.thrift',(outside/'files/main.thrift').read_text().replace('common/value.thrift',os.path.relpath(foreign,outside/'files')));reject('outside-import',outside,ValueError,'native compiler input escapes')
unused=bundle('unused-program');update(unused,'other/value.thrift','struct Value { 1: i32 other }');attempt('unused-program-accepted',unused)
mismatch=Path('mismatched-sdk').resolve();shutil.copytree(model['runtimeSource'],mismatch);mismatch.chmod(0o755);manifest=mismatch/'Cargo.toml';manifest.chmod(0o644);manifest.write_text(manifest.read_text().replace('version = "0.24.0"','version = "0.25.0"'));reject('runtime-version-mismatch',Path(model['resources']),ValueError,'native Rust runtime differs',mismatch)
# A fresh ordinary Cargo consumer cannot resolve the generated crate without its SDK runtime.
missing_runtime=Path('missing-runtime').resolve();shutil.copytree(spec['versions'][0]['repository'],missing_runtime);missing_runtime.chmod(0o755)
for path in missing_runtime.rglob('*'):
 if path.is_dir():path.chmod(0o755)
 elif not path.is_symlink():path.chmod(0o644)
runtime_entry=next(p for p in json.loads((missing_runtime/'.catalog').read_text())['packages'] if p['name']=='thrift')
(missing_runtime/runtime_entry['archive']).unlink()
project=Path('missing-runtime-consumer');subprocess.run(['cargo','init','--bin','--name','missing_runtime','--vcs','none',str(project)],check=True);(project/'.cargo').mkdir();(project/'.cargo/config.toml').write_text('[source.crates-io]\nreplace-with="provided"\n[source.provided]\nlocal-registry='+json.dumps(str(missing_runtime))+'\n')
# Isolate Cargo's extraction cache from previous successful consumers.
env=dict(os.environ,CARGO_HOME=str(Path('missing-runtime-cargo-home').resolve()))
run=subprocess.run(['cargo','add','--offline','proof_schemas@='+next(p['version'] for p in json.loads((missing_runtime/'.catalog').read_text())['packages'] if p['name']=='proof_schemas')],cwd=project,env=env,capture_output=True,text=True)
assert run.returncode==0,run.stderr
run=subprocess.run(['cargo','build','--offline','--locked'],cwd=project,env=env,capture_output=True,text=True)
assert run.returncode and 'thrift' in run.stderr,run.stderr
print(run.stderr,file=sys.stderr);controls['missing-runtime']={'command':['cargo','build','--offline','--locked'],'exitCode':run.returncode,'requiredSdk':'thrift','diagnosticMentionsSdk':True}
(out/'verification.json').write_text(json.dumps({'consumers':results,'rejectionControls':controls,'unusedDuplicateProgramAccepted':True,'preservedNativeVendorFileHashes':vendor_inventory},indent=2)+'\n')
