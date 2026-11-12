# SPDX-License-Identifier: MIT
import functools,hashlib,http.server,json,os,re,shlex,shutil,subprocess,sys,tarfile,tempfile,threading,zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
spec=json.loads(Path(sys.argv[1]).read_text());out=Path(sys.argv[2]);out.mkdir();results=[]
subprocess.run(['javac','-d','.',spec['javaConsumer']],check=True)
java_classes=str(Path.cwd())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for index,case in enumerate(spec['versions']):
 package=Path(case['generated']);model=json.loads((package/'flatbuffers-typescript.json').read_text());repository=Path(case['repository']);catalog=json.loads(Path(case['catalog']).read_text());modules={m['name']:m for m in catalog['modules']};assert set(modules)=={'proof-schemas','flatbuffers'}
 root=Path(str(index)).resolve();root.mkdir();shutil.copyfile(spec['consumer'],root/'consumer.js');env=dict(os.environ,HOME=str(root/'home'),npm_config_cache=str(root/'cache'));Path(env['HOME']).mkdir()
 def run(args):return subprocess.run([str(a) for a in args],cwd=root,env=env,check=True,capture_output=True,text=True).stdout
 run(['npm','init','--yes','--offline']);run(['npm','install','--offline','--ignore-scripts','--no-package-lock','--no-audit','--no-fund',*[repository/modules[name]['archive'] for name in ['flatbuffers','proof-schemas']]])
 flags=shlex.split(subprocess.check_output(['pkg-config','--cflags',case['cpp']+'/lib/pkgconfig/schema_proof.pc'],text=True));cpp=root/'cpp';subprocess.run(['c++','-std=c++11',f'-DEXPECT_BITS={case["bits"]}',spec['cppConsumer'],'-o',str(cpp),*flags],check=True);cpp_result=subprocess.check_output([cpp],text=True).strip().split(':');assert cpp_result[:2]==['42',str(case['bits'])]
 buffer=root/'javascript.bin';actual=json.loads(run(['node',root/'consumer.js',cpp_result[2],buffer,str(case['bits'])]));assert actual['answer']==42 and actual['bits']==case['bits'] and actual['qualified']==[7,8] and actual['other']==44;assert subprocess.check_output([cpp,buffer],text=True).strip()=='42'
 owned=root/'node_modules/proof-schemas';runtime=root/'node_modules/flatbuffers';assert Path(actual['owned']).is_relative_to(owned) and Path(actual['runtime']).is_relative_to(runtime)
 for name,expected in (model['nativeTypeScriptHashes']|model['compiledHashes']).items():assert sha(owned/name)==expected
 runtime_source=Path(model['runtimeSource'])/'sdk'
 for folder in ['js','mjs','ts']:
  for path in (runtime_source/folder).rglob('*'):
   if path.is_file() and path.suffix in ['.js','.ts']:assert path.read_bytes()==(runtime/path.relative_to(runtime_source)).read_bytes()
 original_runtime=Path(model['runtimeRepository'])/model['runtime']['archive'];assert original_runtime.read_bytes()==(repository/modules['flatbuffers']['archive']).read_bytes()
 manifest=json.loads((owned/'package.json').read_text());assert manifest['dependencies']['flatbuffers']==modules['flatbuffers']['version']
 typed=root/'typed.ts';typed.write_text("import {proof,a,b} from 'proof-schemas'; import {proof as extra} from 'proof-schemas/extra'; import {ByteBuffer} from 'flatbuffers'; const value=proof.Envelope.getRootAsEnvelope(new ByteBuffer(new Uint8Array())).value()!; const answer: "+('bigint' if case['bits']==64 else 'number')+"=value.answer(); const av:number=a.Value.getRootAsValue(new ByteBuffer(new Uint8Array())).answer(); const bv:number=b.Value.getRootAsValue(new ByteBuffer(new Uint8Array())).answer(); const packet:number=extra.Packet.getRootAsPacket(new ByteBuffer(new Uint8Array())).answer();\n")
 tsc=Path(model['runtimeSource'])/'sdk/node_modules/typescript/bin/tsc';typed_log=run(['node',tsc,'--target','ES2020','--module','node16','--moduleResolution','node16','--noEmit','--listFiles',typed]);assert str(owned/'lib') in typed_log and str(runtime) in typed_log;(out/f'{index}-typed-files.txt').write_text(typed_log)
 esm=root/'native-esm.mjs';esm.write_text("import {proof} from 'proof-schemas'; import {proof as extra} from 'proof-schemas/extra'; import * as f from 'flatbuffers';const b=new f.Builder(0);proof.Value.startValue(b);proof.Value.addAnswer(b,"+('42n' if case['bits']==64 else '42')+");b.finish(proof.Value.endValue(b));if(Number(proof.Value.getRootAsValue(new f.ByteBuffer(b.asUint8Array())).answer())!==42)throw Error('ESM');console.log('42');")
 assert run(['node',esm]).strip()=='42'
 # Actual headless Chromium imports native self-contained ESM from HTTP.
 web=root/'site';web.mkdir()
 for entry,bundle in model['browserBundles'].items():
  source=package/'package'/bundle['file'];target=web/Path(bundle['file']).name;shutil.copyfile(source,target)
  assert source.read_bytes()==(Path(case['web'])/target.name).read_bytes()
 first=model['browserBundles']['main.fbs']['file'].split('/')[-1];other=model['browserBundles']['other.fbs']['file'].split('/')[-1]
 shutil.copyfile(package/'package/browser/runtime.mjs',web/'runtime.mjs');assert (web/'runtime.mjs').read_bytes()==(Path(case['web'])/'runtime.mjs').read_bytes()
 html="<p id='answer'>pending</p><script type='module'>import {proof} from './"+first+"';import {proof as extra} from './"+other+"';import {ByteBuffer} from './runtime.mjs';const bytes=new Uint8Array("+json.dumps(list(bytes.fromhex(cpp_result[2])))+");const answer=Number(proof.Envelope.getRootAsEnvelope(new ByteBuffer(bytes)).value().answer());if(answer!==42||!extra.Packet)throw Error('browser');document.getElementById('answer').textContent=String(answer);</script>"
 (web/'index.html').write_text(html)
 browser_dom=None
 if spec['chromium'] is not None:
  class Handler(http.server.SimpleHTTPRequestHandler):
   def log_message(self,*args):pass
  server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(web)));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:
   browser=subprocess.run([spec['chromium'],'--headless','--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--disable-background-networking','--no-first-run','--disable-extensions','--user-data-dir='+str(root/'chromium-profile'),'--virtual-time-budget=3000','--dump-dom','http://127.0.0.1:'+str(server.server_port)+'/index.html'],capture_output=True,text=True,timeout=45)
   assert browser.returncode==0 and 'id="answer">42</p>' in browser.stdout,(browser.stdout,browser.stderr)
  finally:server.shutdown();server.server_close();thread.join()
  browser_dom=browser.stdout
 with zipfile.ZipFile(case['javaResources']) as jar:
  for entry,bundle in (model['browserBundles']|{'runtime':model['browserRuntimeBundle']}).items():assert jar.read(Path(bundle['file']).name)==(package/'package'/bundle['file']).read_bytes()
 java_results=[]
 manifest=root/'resource-hashes.tsv';manifest.write_text(''.join(Path(bundle['file']).name+'\t'+bundle['sha256']+'\n' for bundle in (model['browserBundles']|{'runtime':model['browserRuntimeBundle']}).values()))
 assert subprocess.check_output(['java','-cp',java_classes,'ResourceConsumer',case['javaResources'],str(manifest),''],text=True).strip()=='3'
 for repository_kind in ['maven','ivy']:
  jars=list(Path(case[repository_kind]).rglob('*.jar'));assert len(jars)==1
  with zipfile.ZipFile(jars[0]) as jar:
   for entry,bundle in (model['browserBundles']|{'runtime':model['browserRuntimeBundle']}).items():
    name=Path(bundle['file']).name;matching=[p for p in jar.namelist() if p.startswith('META-INF/resources/webjars/') and p.endswith('/'+name)];assert len(matching)==1 and jar.read(matching[0])==(package/'package'/bundle['file']).read_bytes()
  # Resolve through each native repository's metadata with ordinary offline Gradle.
  repo=Path(case[repository_kind]);project=root/('gradle-'+repository_kind);project.mkdir()
  if repository_kind=='maven':
   document=ET.parse(next(repo.rglob('*.pom'))).getroot();ns={'m':'http://maven.apache.org/POM/4.0.0'};coordinate=':'.join(document.find('m:'+name,ns).text for name in ['groupId','artifactId','version']);repository_config='maven { url=uri(selected.repository); metadataSources { mavenPom(); artifact() } }'
  else:
   info=ET.parse(next(repo.rglob('ivy.xml'))).getroot().find('info');coordinate=':'.join(info.attrib[name] for name in ['organisation','module','revision']);repository_config="ivy { url=uri(selected.repository); patternLayout { ivy '[organisation]/[module]/[revision]/ivys/ivy.xml'; artifact '[organisation]/[module]/[revision]/[type]s/[artifact].[ext]' }; metadataSources { ivyDescriptor() } }"
  (project/'config.json').write_text(json.dumps({'repository':str(repo),'coordinate':coordinate}));(project/'settings.gradle').write_text("rootProject.name='flatbuffers-browser-resources'\n")
  (project/'build.gradle').write_text("def selected=new groovy.json.JsonSlurper().parse(file('config.json'))\nrepositories { "+repository_config+" }\nconfigurations { assets }\ndependencies { assets(selected.coordinate) }\ntasks.register('resolveAssets') { doLast { file('resolved.txt').text=configurations.assets.singleFile.canonicalPath } }\n")
  command=['gradle','--offline','--no-daemon','--console=plain','--gradle-user-home',str(root/('gradle-home-'+repository_kind)),'resolveAssets'];gradle=subprocess.run(command,cwd=project,env=env,text=True,capture_output=True,timeout=180);assert gradle.returncode==0,(gradle.stdout,gradle.stderr)
  resolved=Path((project/'resolved.txt').read_text());assert resolved.read_bytes()==jars[0].read_bytes()
  with zipfile.ZipFile(resolved) as jar:prefix=next(name for name in jar.namelist() if name.endswith('/runtime.mjs'))[:-len('runtime.mjs')]
  assert subprocess.check_output(['java','-cp',java_classes,'ResourceConsumer',str(resolved),str(manifest),prefix],text=True).strip()=='3'
  java_results.append({'repository':repository_kind,'coordinate':coordinate,'resolvedSha256':sha(resolved),'resourceCount':3})
 if case['combinedMaven']:
  combined=Path(case['combinedMaven']);poms=list(combined.rglob('*.pom'));assert len(poms)==3
  coordinates={}
  for pom in poms:
   xml=ET.parse(pom).getroot();ns={'m':'http://maven.apache.org/POM/4.0.0'};group,artifact,version=[xml.find('m:'+name,ns).text for name in ['groupId','artifactId','version']];coordinates[artifact]=':'.join([group,artifact,version])
  assert set(coordinates)=={'answer','flatbuffers-java','proof-schemas'}
  project=root/'combined-gradle';project.mkdir();(project/'settings.gradle').write_text("rootProject.name='combined-schema-browser'\n");(project/'config.json').write_text(json.dumps({'repository':str(combined),'coordinates':list(coordinates.values())}))
  (project/'build.gradle').write_text("def selected=new groovy.json.JsonSlurper().parse(file('config.json'))\nrepositories { maven { url=uri(selected.repository); metadataSources { mavenPom(); artifact() } } }\nconfigurations { assets }\ndependencies { selected.coordinates.each { assets(it) } }\ntasks.register('resolveAssets') { doLast { file('resolved.txt').text=configurations.assets.files.collect { it.canonicalPath }.sort().join('\\n') } }\n")
  gradle=subprocess.run(['gradle','--offline','--no-daemon','--console=plain','--gradle-user-home',str(root/'combined-gradle-home'),'resolveAssets'],cwd=project,env=env,capture_output=True,text=True,timeout=180);assert gradle.returncode==0,(gradle.stdout,gradle.stderr)
  resolved=[Path(path) for path in (project/'resolved.txt').read_text().splitlines()];assert len(resolved)==3
  by_artifact={}
  for artifact,coordinate in coordinates.items():
   candidates=[path for path in resolved if path.name==coordinate.split(':')[1]+'-'+coordinate.split(':')[2]+'.jar'];assert len(candidates)==1;by_artifact[artifact]=candidates[0];expected=next(pom.with_suffix('.jar') for pom in poms if pom.name==artifact+'-'+coordinate.split(':')[2]+'.pom');assert expected.read_bytes()==candidates[0].read_bytes()
  with zipfile.ZipFile(by_artifact['proof-schemas']) as jar:prefix=next(name for name in jar.namelist() if name.endswith('/runtime.mjs'))[:-len('runtime.mjs')]
  assert subprocess.check_output(['java','-cp',java_classes,'ResourceConsumer',str(by_artifact['proof-schemas']),str(manifest),prefix,str(by_artifact['answer']),str(by_artifact['flatbuffers-java']),cpp_result[2]],text=True).strip()=='3'
  java_results.append({'repository':'combined-maven','coordinates':coordinates,'resolvedSha256':{key:sha(value) for key,value in by_artifact.items()},'resourceCount':3,'nativeJavaDecodedAnswer':42,'classOriginsVerified':True})
 native=json.loads(run(['npm','ls','--all','--omit=dev','--json']));assert native['dependencies']['proof-schemas']['version']==modules['proof-schemas']['version']
 results.append({'case':case,'model':model,'actual':actual,'modules':modules,'cpp':cpp_result,'nativeNpmGraph':native,'browserDOM':browser_dom,'javaResourceConsumers':java_results})
assert results[0]['actual']['wire']!=results[1]['actual']['wire'];assert results[0]['modules']['proof-schemas']['version']!=results[1]['modules']['proof-schemas']['version']
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
  generator.generate({'resources':str(resources),'sdk':model['sdk'],'sdkSource':model['sdkSource'],'runtime':model['runtimeSource'],'runtimeCatalog':spec['versions'][0]['runtimeCatalog'],'runtimeRepository':model['runtimeRepository'],'package':dict(model['nativePackage'],entrypoints={'.':'main.fbs','./extra':'other.fbs'})},folder/'generated')
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
# Native npm must resolve the dependency rather than receiving an implicit global runtime.
repository=Path(spec['versions'][0]['repository']);owned=results[0]['modules']['proof-schemas'];root=Path('missing-runtime').resolve();root.mkdir();env=dict(os.environ,HOME=str(root/'home'),npm_config_cache=str(root/'empty-cache'));Path(env['HOME']).mkdir()
subprocess.run(['npm','init','--yes','--offline'],cwd=root,env=env,check=True,capture_output=True)
failed=subprocess.run(['npm','install','--offline','--ignore-scripts','--no-package-lock','--no-audit','--no-fund',str(repository/owned['archive'])],cwd=root,env=env,capture_output=True,text=True)
assert failed.returncode and 'flatbuffers' in failed.stderr
# Keep the raw native diagnostic in the Nix build log. Its observed timestamped
# debug-log location is not an artifact or dependency fact and cannot be stable.
print('Raw native missing-runtime npm stderr:',file=sys.stderr);print(failed.stderr,end='',file=sys.stderr)
pattern=r"npm error A complete log of this run can be found in: /build/missing-runtime/empty-cache/_logs/\d{4}-\d{2}-\d{2}T\d{2}_\d{2}_\d{2}_\d{3}Z-debug-0\.log"
lines=failed.stderr.splitlines(keepends=True);excluded=[line for line in lines if re.fullmatch(pattern,line.rstrip('\n'))];assert len(excluded)==1
stable=''.join(line for line in lines if line not in excluded);controls['missing-runtime']=stable;(out/'missing-runtime.stderr').write_text(stable)
(out/'missing-runtime-command.json').write_text(json.dumps({'argv':['npm','install','--offline','--ignore-scripts','--no-package-lock','--no-audit','--no-fund',str(repository/owned['archive'])],'exitCode':failed.returncode,'excludedTimestampedLogLocationRecords':len(excluded),'rawStderr':'retained verbatim in native Nix build log'},indent=2)+'\n')
# The same native TypeScript invocation must fail if its runtime declarations disappear.
root=Path('0').resolve();runtime=root/'node_modules/flatbuffers'
for path in runtime.rglob('*.d.ts'):path.unlink()
failed=subprocess.run(['node',str(Path(model['runtimeSource'])/'sdk/node_modules/typescript/bin/tsc'),'--strict','--target','ES2020','--module','node16','--moduleResolution','node16','--noEmit',str(root/'typed.ts')],cwd=root,capture_output=True,text=True)
assert failed.returncode and 'flatbuffers' in failed.stdout;controls['missing-runtime-declarations']=failed.stdout;(out/'missing-runtime-declarations.stdout').write_text(failed.stdout)
# Root ownership is explicit and complete; arbitrary npm export paths are rejected.
for label,entries,expected in [('unselected-root',{'.':'absent.fbs'},'every captured schema root'),('invalid-export',{'../escape':'main.fbs','./extra':'other.fbs'},'invalid npm subpath export')]:
 try:generator.generate({'resources':model['resources'],'sdk':model['sdk'],'sdkSource':model['sdkSource'],'runtime':model['runtimeSource'],'runtimeCatalog':spec['versions'][0]['runtimeCatalog'],'runtimeRepository':model['runtimeRepository'],'package':{'name':'proof-schemas','version':'1.0.0','entrypoints':entries}},Path('reject-'+label).resolve())
 except ValueError as error:assert expected in str(error);controls[label]=str(error)
 else:raise AssertionError('accepted '+label)
(out/'verification.json').write_text(json.dumps({'consumers':results,'rejectionControls':controls},indent=2)+'\n')
