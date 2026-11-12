# SPDX-License-Identifier: MIT
import hashlib,json,shlex,subprocess,sys,xml.etree.ElementTree as ET,zipfile,shutil,os
from pathlib import Path
spec=json.loads(Path(sys.argv[1]).read_text());out=Path(sys.argv[2]);out.mkdir();results=[]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def run(args,label):
 result=subprocess.run([str(a) for a in args],capture_output=True,text=True)
 (out/(label+'.stdout')).write_text(result.stdout);(out/(label+'.stderr')).write_text(result.stderr)
 if result.returncode:raise AssertionError((args,result.stdout,result.stderr))
 return result.stdout
for index,case in enumerate(spec['versions']):
 package=Path(case['package']);runtime=Path(case['runtime']);model=json.loads((package/'proof/model.json').read_text());sdk=json.loads((runtime/'proof/model.json').read_text())
 assert model['runtime']==sdk and sha(runtime/'runtime.jar')==sdk['jarSha256'] and sha(package/'bindings.jar')==model['jarSha256']
 for logical,expected in model['schemaHashes'].items():assert sha(Path(model['resources'])/'files'/logical)==expected
 for logical,expected in model['generatedHashes'].items():assert sha(package/'generated'/logical)==expected
 for logical,expected in sdk['sourceHashes'].items():assert sha(Path(sdk['sdkSource'])/logical)==expected
 assert not set(model['classes'])&set(sdk['classes'])
 objects=model['nativeSchemas']['main.fbs']['schema']['objects'];field=next(o for o in objects if o['name']=='proof.Value')['fields'][0]
 assert field['type']['base_type']==('Int' if case['bits']==32 else 'Long')
 catalog=json.loads(Path(case['catalog']).read_text());modules=catalog['modules'];assert len(modules)==2
 own=next(m for m in modules if m['group']=='org.example.schemas' and m['name']=='answer');foreign=next(m for m in modules if m['group']==sdk['coordinates']['groupId'] and m['name']==sdk['coordinates']['artifactId'])
 coordinate=':'.join(own[k] for k in ['group','name','version']);assert '-nix-' in own['version'] and '-nix-' in foreign['version']
 folder=Path(f'gradle-{index}');folder.mkdir();(folder/'settings.gradle').write_text("rootProject.name='flatbuffers-consumer'\n")
 (folder/'build.gradle').write_text('repositories { maven { url = uri('+json.dumps(case['maven'])+') } }\nconfigurations { proof }\ndependencies { proof '+json.dumps(coordinate)+' }\ntasks.register("resolve") { doLast { configurations.proof.resolve().sort().each { println("RESOLVED\\t" + it.absolutePath) } } }\n')
 resolved=run(['gradle','--offline','--no-daemon','--console=plain','-g',str(folder/'home'),'-p',str(folder),'resolve'],str(index)+'-gradle')
 paths=[Path(line.split('\t',1)[1]) for line in resolved.splitlines() if line.startswith('RESOLVED\t')];assert len(paths)==2,paths
 owned=next(p for p in paths if p.name.startswith('answer-'));support=next(p for p in paths if p.name.startswith('flatbuffers-java-'))
 assert sha(owned)==model['jarSha256'] and sha(support)==sdk['jarSha256']
 pom=Path(case['maven'])/own['group'].replace('.','/')/own['name']/own['version']/(own['name']+'-'+own['version']+'.pom');tree=ET.parse(pom);ns={'m':'http://maven.apache.org/POM/4.0.0'};dependencies=tree.findall('./m:dependencies/m:dependency',ns);assert len(dependencies)==1;assert dependencies[0].findtext('m:version',namespaces=ns)=='['+foreign['version']+']'
 flags=shlex.split(run(['pkg-config','--cflags',case['cpp']+'/lib/pkgconfig/schema_proof.pc'],str(index)+'-cpp-flags'))
 cpp=Path(f'cpp-{index}').resolve();run(['c++','-std=c++11',f'-DEXPECT_BITS={case["bits"]}',spec['cppConsumer'],'-o',cpp,*flags],str(index)+'-cpp-compile')
 wire=run([cpp],str(index)+'-cpp').strip().split(':');assert wire[:2]==['42',str(case['bits'])]
 classes=Path(f'consumer-{index}');classes.mkdir();classpath=str(owned)+':'+str(support)
 run(['javac','-cp',classpath,'-d',classes,spec['consumer']],str(index)+'-javac')
 names=Path(f'classes-{index}.txt');names.write_text('\n'.join(sorted(model['classes']))+'\n')
 answer=run(['java','-cp',str(classes)+':'+classpath,'Consumer',wire[2],owned,support,str(case['bits']),names],str(index)+'-java')
 actual=[]
 for line in answer.splitlines():
  if line.startswith('CLASS\t'):
   _,entry,origin,digest=line.split('\t');assert digest==(model['classes']|sdk['classes'])[entry];actual.append({'entry':entry,'origin':origin,'sha256':digest})
 assert len(actual)==len(model['classes'])+3
 java_wire=next(line.split('\t')[1] for line in answer.splitlines() if line.startswith('WIRE\t'));buffer=Path(f'java-{index}.bin');buffer.write_bytes(bytes.fromhex(java_wire));assert run([cpp,buffer],str(index)+'-cpp-java').strip()=='42'
 missing=subprocess.run(['java','-cp',str(classes)+':'+str(owned),'Consumer',wire[2],str(owned),str(support),str(case['bits']),str(names)],capture_output=True,text=True);assert missing.returncode and 'NoClassDefFoundError' in missing.stderr;(out/(str(index)+'-missing-runtime.stderr')).write_text(missing.stderr)
 broken=Path(f'missing-value-{index}.jar')
 with zipfile.ZipFile(owned) as source,zipfile.ZipFile(broken,'w') as target:
  for entry in source.infolist():
   if entry.filename not in ['proof/Value.class','proof/Value$Vector.class']:target.writestr(entry,source.read(entry.filename))
 missing_type=subprocess.run(['java','-cp',str(classes)+':'+str(broken)+':'+str(support),'Consumer',wire[2],str(broken),str(support),str(case['bits']),str(names)],capture_output=True,text=True)
 assert missing_type.returncode and 'NoClassDefFoundError' in missing_type.stderr and 'proof/Value' in missing_type.stderr
 (out/(str(index)+'-missing-value.stderr')).write_text(missing_type.stderr)
 results.append({'case':case,'model':model,'runtime':sdk,'ownedJar':str(owned),'runtimeJar':str(support),'classOrigins':actual,'cppWire':wire[2],'javaWire':java_wire,'coordinate':coordinate,'runtimeCoordinate':':'.join(foreign[k] for k in ['group','name','version']),'missingRuntimeRejected':True,'missingSchemaTypeRejected':True})
assert results[0]['javaWire']!=results[1]['javaWire'] and results[0]['coordinate']!=results[1]['coordinate']
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
 path=bundle/'files'/logical;path.write_text(text);catalog=json.loads((bundle/'catalog.json').read_text());record=dict(next(iter(catalog['files'].values())));record['sha256']=sha(path);catalog['files'][logical]=record;(bundle/'catalog.json').write_text(json.dumps(catalog))
def attempt(name,resources):
 folder=Path(name).resolve();folder.mkdir();prior=Path.cwd()
 try:
  os.chdir(folder)
  generator.generate({'resources':str(resources),'sdk':model['sdk'],'sdkSource':model['runtime']['sdkSource'],'runtime':model['runtimePath'],'jdk':model['jdk'],'maven':model['maven'],'publisherSource':spec['publisherSource'],'groupId':'org.example.schemas','artifactId':'answer','version':'1.0.0'},folder/'out')
 finally:os.chdir(prior)
missing=bundle('missing-import');(missing/'files/common/value.fbs').unlink()
try:attempt('unexpected-import',missing)
except subprocess.CalledProcessError as error:
 assert 'common/value.fbs' in error.stderr
 (out/'missing-import.stderr').write_text(error.stderr)
else:raise AssertionError('native compiler accepted missing schema import')
corrupt=bundle('changed-source');path=corrupt/'files/common/value.fbs';path.write_text(path.read_text()+'// uncaptured source change\n')
try:attempt('unexpected-source',corrupt)
except ValueError as error:assert 'differs from captured hash' in str(error)
else:raise AssertionError('accepted changed captured source')
outside=bundle('outside-import');foreign=Path('external/value.fbs').resolve();foreign.parent.mkdir();foreign.write_text((outside/'files/common/value.fbs').read_text().replace('answer:int','answer:long'))
update(outside,'main.fbs',(outside/'files/main.fbs').read_text().replace('common/value.fbs',os.path.relpath(foreign,outside/'files')))
try:attempt('unexpected-outside',outside)
except ValueError as error:assert 'native schema input escapes' in str(error)
else:raise AssertionError('accepted native input outside captured schema tree')
collision=bundle('runtime-collision');update(collision,'shadow.fbs','namespace com.google.flatbuffers; table Table { other:int; }\n');catalog=json.loads((collision/'catalog.json').read_text());catalog['schema']['entrypoints'].append('shadow.fbs');(collision/'catalog.json').write_text(json.dumps(catalog))
try:attempt('unexpected-collision',collision)
except ValueError as error:assert 'generated Java type collides with native runtime' in str(error)
else:raise AssertionError('accepted generated type shadowing native runtime')
overlap=bundle('generated-collision');update(overlap,'other.fbs','namespace proof; table Value { other:int; }\n');catalog=json.loads((overlap/'catalog.json').read_text());catalog['schema']['entrypoints'].append('other.fbs');(overlap/'catalog.json').write_text(json.dumps(catalog))
try:attempt('unexpected-output',overlap)
except ValueError as error:assert 'native generated Java outputs collide' in str(error)
else:raise AssertionError('accepted conflicting generated Java outputs')
(out/'verification.json').write_text(json.dumps({'consumers':results,'missingImportRejected':True,'changedSourceRejected':True,'outsideCompilerInputRejected':True,'runtimeTypeCollisionRejected':True,'generatedTypeCollisionRejected':True},indent=2)+'\n')
