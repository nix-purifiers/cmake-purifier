# SPDX-License-Identifier: MIT
import json,os,shlex,shutil,subprocess,sys,hashlib,tarfile
from pathlib import Path
spec=json.loads(Path(sys.argv[1]).read_text());out=Path(sys.argv[2]);out.mkdir();results=[]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for index,case in enumerate(spec['versions']):
 root=Path('consumer-'+str(index)).resolve();root.mkdir();catalog=json.loads(Path(case['catalog']).read_text());owned=next(m for m in catalog['modules'] if m['name']=='@proof/thrift-schemas' and m['primary']);view=json.loads(Path(case['installCatalog']).read_text());archive=next(m for m in view['modules'] if m['name']==owned['name'])
 env=dict(os.environ,npm_config_cache=str(root/'cache'))
 def run(args,check=True):
  result=subprocess.run(args,cwd=root,env=env,text=True,capture_output=True)
  if check and result.returncode:
   print(result.stdout,file=sys.stderr);print(result.stderr,file=sys.stderr);result.check_returncode()
  return result
 run(['npm','init','--yes','--offline']);run(['npm','install','--offline','--ignore-scripts','--no-audit','--no-fund',str(Path(case['install'])/archive['archive'])])
 shutil.copyfile(spec['consumer'],root/'consumer.cjs');shutil.copyfile(spec['typescriptConsumer'],root/'consumer.ts')
 flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs',case['cpp']+'/lib/pkgconfig/thrift_proof.pc'],text=True));cpp=root/'cpp';subprocess.run(['c++',spec['cppConsumer'],'-o',str(cpp),*spec['dlLibs'],*flags],check=True);native=subprocess.check_output([cpp],text=True).splitlines();wire=native[0].split(':',1)[1]
 node=run(['node','consumer.cjs',wire,str(root/'rpc.sock')]);actual=json.loads(node.stdout);assert actual['answer']==42 and actual['rpc']==43 and actual['wire']==wire
 typed=run(['tsc','--strict','--target','es2020','--module','commonjs','--moduleResolution','node','--outDir','compiled','--listFiles','consumer.ts']);assert run(['node','compiled/consumer.js']).stdout.strip()=='42 7 8';assert str(root/'node_modules/@types/thrift/index.d.ts') in typed.stdout
 (out/f'typescript-files-{index}.txt').write_text(typed.stdout)
 esm=run(['node','--input-type=module','-e',"import {schema,common} from '@proof/thrift-schemas'; if(new schema.Envelope({value:new common.Value({answer:42})}).value.answer!==42) throw Error('esm'); console.log(42)"]);assert esm.stdout.strip()=='42'
 model=json.loads((Path(case['generated'])/'thrift-javascript.json').read_text());assert model['nativeModels']['value']['structs'][0]['fields'][0]['key']==index+1
 package=root/'node_modules/@proof/thrift-schemas'
 for name,expected in model['generatedHashes'].items():assert sha(package/'generated'/name)==expected
 for path in Path(spec['originalTypes']).glob('*.d.ts'):assert path.read_bytes()==(root/'node_modules/@types/thrift'/path.name).read_bytes()
 runtime=Path(actual['runtime']);sdk=Path(model['sdkSource'])/'lib/nodejs/lib/thrift';assert runtime.read_bytes()==(sdk/'index.js').read_bytes()
 for path in sdk.glob('*.js'):assert path.read_bytes()==(runtime.parent/path.name).read_bytes()
 results.append({'case':case,'actual':actual,'model':model,'typescriptCommand':['tsc','--strict','--target','es2020','--module','commonjs','--moduleResolution','node','--outDir','compiled','--listFiles','consumer.ts'],'typescriptOutput':'42 7 8','esmOutput':'42'})
assert results[0]['actual']['wire']!=results[1]['actual']['wire']
# Native syntax validation and safe bindings preserve keyword/prototype aliases.
case=spec['aliases'];root=Path('alias-consumer').resolve();root.mkdir();env=dict(os.environ,npm_config_cache=str(root/'cache'));catalog=json.loads(Path(case['installCatalog']).read_text());entry=next(m for m in catalog['modules'] if m['name']=='@proof/thrift-aliases');subprocess.run(['npm','init','--yes','--offline'],cwd=root,env=env,check=True,capture_output=True);subprocess.run(['npm','install','--offline','--ignore-scripts','--no-audit','--no-fund',str(Path(case['install'])/entry['archive'])],cwd=root,env=env,check=True,capture_output=True)
common="const x=require('@proof/thrift-aliases'); if(new x.default.Envelope({value:new x.class.Value({answer:42})}).value.answer!==42 || !Object.hasOwn(x,'__proto__') || new x.__proto__.Value({answer:7}).answer!==7)throw Error('alias'); console.log(42);"
subprocess.run(['node','-e',common],cwd=root,env=env,check=True,capture_output=True)
esm="import {default as schemas,class as values,__proto__ as a} from '@proof/thrift-aliases';if(new schemas.Envelope({value:new values.Value({answer:42})}).value.answer!==42||new a.Value({answer:7}).answer!==7)throw Error('alias');console.log(42);"
subprocess.run(['node','--input-type=module','-e',esm],cwd=root,env=env,check=True,capture_output=True)
(root/'alias.ts').write_text("import {default as schemas,class as values,__proto__ as a} from '@proof/thrift-aliases';const result:number=new schemas.Envelope({value:new values.Value({answer:42})}).value.answer;const other:number=new a.Value({answer:7}).answer;console.log(result,other);\n")
subprocess.run(['tsc','--strict','--noEmit','--target','es2020','--module','commonjs','--moduleResolution','node','alias.ts'],cwd=root,check=True)
alias_proof={'names':['default','class','__proto__'],'nativeSyntaxChecks':['node --check index.cjs','node --check index.mjs'],'commonjs':42,'esm':42,'strictTypeScriptExit':0}
# Real compiler/type/runtime rejection controls use fresh native workspaces.
from importlib.util import spec_from_file_location,module_from_spec
loader=spec_from_file_location('generator',spec['generator']);generator=module_from_spec(loader);loader.loader.exec_module(generator)
model=results[0]['model'];controls={}
def bundle(name):
 path=Path(name).resolve();shutil.copytree(model['resources'],path)
 for item in [path,*path.rglob('*')]:
  if not item.is_symlink():item.chmod(0o755 if item.is_dir() else 0o644)
 return path
def update(bundle,logical,text):
 path=bundle/'files'/logical;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text);catalog=json.loads((bundle/'catalog.json').read_text());entry=dict(next(iter(catalog['files'].values())));entry['sha256']=sha(path);catalog['files'][logical]=entry;(bundle/'catalog.json').write_text(json.dumps(catalog))
def reject(name,resources,exception,needle=None,sdkSource=None):
 folder=Path('reject-'+name).resolve();folder.mkdir()
 args={'resources':str(resources),'sdk':model['sdk'],'sdkSource':str(sdkSource or model['sdkSource']),'runtimeGraph':model['runtimeGraph'],'runtimeRepository':model['runtimeRepository'],'runtimeCatalog':model['runtimeCatalog'],'extraInputs':model['extraInputs'],'package':{'name':'@proof/rejected','version':'1.0.0','entrypoints':model['entrypoints']}}
 try:generator.generate(args,folder/'generated')
 except exception as error:
  if needle:assert needle in str(error),str(error)
  controls[name]={'exception':type(error).__name__,'reason':str(error)}
 else:raise AssertionError('accepted '+name)
missing=bundle('missing-import');(missing/'files/common/value.thrift').unlink();reject('missing-import',missing,subprocess.CalledProcessError)
changed=bundle('changed-hash');file=changed/'files/common/value.thrift';file.write_text(file.read_text()+'// changed source\n');reject('changed-hash',changed,ValueError,'does not match captured resource hash')
outside=bundle('outside-include');foreign=Path('external/value.thrift').resolve();foreign.parent.mkdir();foreign.write_text((outside/'files/common/value.thrift').read_text());update(outside,'main.thrift',(outside/'files/main.thrift').read_text().replace('common/value.thrift',str(foreign)));reject('outside-include',outside,ValueError,'native compiler input escapes')
ambiguous=bundle('ambiguous-program');update(ambiguous,'other/value.thrift','struct Value { 1: i32 other }');reject('ambiguous-program',ambiguous,ValueError,'ambiguous native program output name')
collision=bundle('service-collision');update(collision,'other.thrift','service AnswerService { i32 answer(1: i32 delta) }');update(collision,'main.thrift','include "other.thrift"\n'+(collision/'files/main.thrift').read_text());reject('service-collision',collision,ValueError,'native generated JavaScript outputs collide')
mismatch=Path('mismatched-runtime').resolve();mismatch.mkdir();metadata=dict(model['nativeRuntimeManifest']);metadata['version']='0.0.0';(mismatch/'package.json').write_text(json.dumps(metadata));reject('runtime-release-mismatch',Path(model['resources']),ValueError,'native npm runtime differs',mismatch)
# Invalid schema field values must fail the real strict TypeScript checker.
root=Path('consumer-0').resolve();bad=root/'bad.ts';bad.write_text('import {common} from "@proof/thrift-schemas"; new common.Value({answer:"wrong"});\n')
failed=subprocess.run(['tsc','--strict','--noEmit','--target','es2020','--module','commonjs','--moduleResolution','node','bad.ts'],cwd=root,text=True,capture_output=True);assert failed.returncode and 'not assignable to type' in failed.stdout,failed.stdout;controls['typed-field-mismatch']={'exitCode':failed.returncode,'nativeDiagnostic':failed.stdout};print(failed.stdout,file=sys.stderr)
# Without explicit runtime declaration inputs, preserve the native SDK's
# default TypeScript behavior and its actual strict-mode diagnostic.
case=spec['noTypes'];root=Path('no-types-consumer').resolve();root.mkdir();env=dict(os.environ,npm_config_cache=str(root/'cache'));catalog=json.loads(Path(case['installCatalog']).read_text());entry=next(m for m in catalog['modules'] if m['name']=='@proof/thrift-schemas')
subprocess.run(['npm','init','--yes','--offline'],cwd=root,env=env,check=True,capture_output=True);subprocess.run(['npm','install','--offline','--ignore-scripts','--no-audit','--no-fund',str(Path(case['install'])/entry['archive'])],cwd=root,env=env,check=True,capture_output=True);shutil.copyfile(spec['typescriptConsumer'],root/'consumer.ts')
base=['tsc','--noEmit','--target','es2020','--module','commonjs','--moduleResolution','node','consumer.ts'];normal=subprocess.run(base,cwd=root,text=True,capture_output=True);assert normal.returncode==0,normal.stdout
strict=subprocess.run(base+['--strict'],cwd=root,text=True,capture_output=True);assert strict.returncode and 'TS7016' in strict.stdout and "module 'thrift'" in strict.stdout,strict.stdout;print(strict.stdout,file=sys.stderr);controls['native-sdk-strict-without-types']={'defaultExitCode':normal.returncode,'strictExitCode':strict.returncode,'diagnostic':'TS7016: selected SDK has no Node runtime declaration; explicit provider required for strict mode'}
# A fresh normal npm importer cannot resolve the package without its runtime.
root=Path('missing-runtime-consumer').resolve();root.mkdir();env=dict(os.environ,npm_config_cache=str(root/'cache'));catalog=json.loads(Path(spec['versions'][0]['catalog']).read_text());repo=Path(spec['versions'][0]['repository']);subprocess.run(['npm','init','--yes','--offline'],cwd=root,env=env,check=True,capture_output=True)
args=['npm','install','--offline','--ignore-scripts','--no-package-lock','--no-audit','--no-fund',*[str(repo/m['archive']) for m in catalog['modules'] if m['name']!=model['runtime']['name']]];failed=subprocess.run(args,cwd=root,env=env,text=True,capture_output=True);assert failed.returncode and ('https://registry.npmjs.org/'+model['runtime']['name']) in failed.stderr,failed.stderr;print(failed.stderr,file=sys.stderr);controls['missing-runtime']={'argv':args,'exitCode':failed.returncode,'requiredRuntime':model['runtime']['name'],'requiredVersion':model['runtime']['version']}
(out/'verification.json').write_text(json.dumps({'consumers':results,'rejectionControls':controls,'aliasProof':alias_proof},indent=2)+'\n')
