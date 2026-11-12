# SPDX-License-Identifier: MIT
import hashlib,json,os,shlex,shutil,subprocess,sys,zipfile
from pathlib import Path
spec=json.loads(Path(sys.argv[1]).read_text());out=Path(sys.argv[2]);out.mkdir();results=[]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for index,case in enumerate(spec['versions']):
 package=Path(case['package']);model=json.loads((package/'thrift-java.json').read_text());repository=Path(case['repository']);catalog=json.loads(Path(case['catalog']).read_text());roots=[m for m in catalog['modules'] if m['group']==model['nativeGradleModel']['publication']['group'] and m['name']==model['nativeGradleModel']['publication']['name'] and m['originalVersion']==model['nativeGradleModel']['publication']['version']];assert len(roots)==1;selected=roots[0];root=Path(str(index)).resolve();root.mkdir()
 (root/'settings.gradle').write_text("rootProject.name='thrift-java-consumer'\n");(root/'config.json').write_text(json.dumps({'repository':str(repository),'coordinate':':'.join([selected['group'],selected['name'],selected['version']])}))
 (root/'build.gradle').write_text("def selected=new groovy.json.JsonSlurper().parse(file('config.json'))\nrepositories { maven { url=uri(selected.repository); metadataSources { mavenPom(); artifact() } } }\nconfigurations { runtime }\ndependencies { runtime(selected.coordinate) }\ntasks.register('resolveRuntime') { doLast { file('classpath.txt').text=configurations.runtime.files.collect { it.canonicalPath }.sort().join(File.pathSeparator) } }\n")
 env=dict(os.environ,HOME=str(root/'home'),GRADLE_USER_HOME=str(root/'gradle-home'));Path(env['HOME']).mkdir();run=subprocess.run(['gradle','--offline','--no-daemon','--console=plain','resolveRuntime'],cwd=root,env=env,capture_output=True,text=True);assert run.returncode==0,(run.stdout,run.stderr)
 classpath=(root/'classpath.txt').read_text();subprocess.run(['javac','-cp',classpath,'-d',str(root/'classes'),spec['consumer']],check=True)
 flags=subprocess.check_output(['pkg-config','--cflags','--libs',case['cpp']+'/lib/pkgconfig/thrift_proof.pc'],text=True);cpp=root/'cpp';subprocess.run(['c++',spec['cppConsumer'],'-o',str(cpp),*spec['dlLibs'],*shlex.split(flags)],check=True);cpp_result=subprocess.check_output([cpp],text=True).splitlines();assert cpp_result[0].startswith('42:') and cpp_result[1]=='43';wire=cpp_result[0].split(':')[1]
 buffer=root/'java.bin';actual=subprocess.check_output(['java','-cp',str(root/'classes')+os.pathsep+classpath,'consumer.Consumer',wire,str(buffer)],text=True).splitlines();assert actual[:2]==['42:'+wire,'43'] and actual[4]=='7:8'
 own=Path(actual[2]);runtime=Path(actual[3]);assert own.is_file() and runtime.is_file()
 def published(module):return repository/module['group'].replace('.','/')/module['name']/module['version']/(module['name']+'-'+module['version']+'.jar')
 assert own.read_bytes()==published(selected).read_bytes();assert runtime.read_bytes()==published(model['runtimeModule']).read_bytes()

 for jar in [own,runtime]:
  with zipfile.ZipFile(jar) as archive:
   if jar==own:
    for name in model['generatedHashes']:assert name[:-5]+'.class' in archive.namelist()
   else:
    for name,source in [('META-INF/LICENSE.txt','LICENSE'),('META-INF/NOTICE.txt','NOTICE')]:assert archive.read(name)==(Path(model['sdkSource'])/source).read_bytes()
    with zipfile.ZipFile(model['nativeRuntimeJar']) as native:
     for name in archive.namelist():
      if name.endswith('.class'):assert archive.read(name)==native.read(name)
 with zipfile.ZipFile(Path(model['nativeRuntimeJar']).with_name('libthrift-'+model['runtimeNativePublication']['version']+'-sources.jar')) as archive:
  names=[name for name in archive.namelist() if name.endswith('.java')];source=Path(model['sdkSource'])/'lib/java/src/main/java';assert set(names)=={str(p.relative_to(source)) for p in source.rglob('*.java')}
  for name in names:assert archive.read(name)==(source/name).read_bytes()
 for name,expected in model['generatedHashes'].items():assert sha(package/'package/src/main/java'/name)==expected
 ivy_root=root/'ivy-client';ivy_root.mkdir();(ivy_root/'settings.gradle').write_text("rootProject.name='native-ivy-consumer'\n");(ivy_root/'config.json').write_text(json.dumps({'repository':case['ivy'],'coordinate':':'.join([selected['group'],selected['name'],selected['version']]),'sdk':':'.join([model['runtimeModule']['group'],model['runtimeModule']['name'],model['runtimeModule']['version']])}));(ivy_root/'build.gradle').write_text("def selected=new groovy.json.JsonSlurper().parse(file('config.json'))\nrepositories { ivy {url=uri(selected.repository);patternLayout {ivy '[organisation]/[module]/[revision]/ivys/ivy.xml';artifact '[organisation]/[module]/[revision]/[type]s/[artifact].[ext]'};metadataSources {ivyDescriptor()}} }\nconfigurations {runtime;ownedSources;sdkSources;sdkDocs}\ndependencies {runtime(selected.coordinate);ownedSources(selected.coordinate){targetConfiguration='sources'};sdkSources(selected.sdk){targetConfiguration='sources'};sdkDocs(selected.sdk){targetConfiguration='javadoc'}}\ntasks.register('resolveRuntime') {doLast {file('classpath.txt').text=configurations.runtime.files.collect{it.canonicalPath}.sort().join(File.pathSeparator);[ownedSources:configurations.ownedSources,sdkSources:configurations.sdkSources,sdkDocs:configurations.sdkDocs].each {name,conf->file(name+'.txt').text=conf.singleFile.canonicalPath}}}\n")
 ivy_env=dict(env,GRADLE_USER_HOME=str(root/'ivy-home'));ivy_run=subprocess.run(['gradle','--offline','--no-daemon','--console=plain','resolveRuntime'],cwd=ivy_root,env=ivy_env,capture_output=True,text=True);assert ivy_run.returncode==0,(ivy_run.stdout,ivy_run.stderr);ivy_classpath=(ivy_root/'classpath.txt').read_text();assert sorted(sha(Path(p)) for p in ivy_classpath.split(os.pathsep))==sorted(sha(Path(p)) for p in classpath.split(os.pathsep))
 ivy_actual=subprocess.check_output(['java','-cp',str(root/'classes')+os.pathsep+ivy_classpath,'consumer.Consumer',wire,str(root/'ivy.bin')],text=True).splitlines();assert ivy_actual[:2]==actual[:2] and ivy_actual[4]=='7:8';assert sha(Path(ivy_actual[2]))==sha(own) and sha(Path(ivy_actual[3]))==sha(runtime)
 pub=model['nativeGradleModel']['publication'];raw_sources=package/'repository'/pub['group'].replace('.','/')/pub['name']/pub['version']/(pub['name']+'-'+pub['version']+'-sources.jar');native_sources=Path(model['nativeRuntimeJar']).with_name('libthrift-'+model['runtimeNativePublication']['version']+'-sources.jar');native_docs=Path(model['nativeRuntimeJar']).with_name('libthrift-'+model['runtimeNativePublication']['version']+'-javadoc.jar');classified={}
 for name,expected in [('ownedSources',raw_sources),('sdkSources',native_sources),('sdkDocs',native_docs)]:
  resolved=Path((ivy_root/(name+'.txt')).read_text());assert resolved.read_bytes()==expected.read_bytes();classified[name]=sha(resolved)
 results.append({'case':case,'model':model,'nativeCpp':cpp_result,'actualJava':actual,'actualIvyJava':ivy_actual,'nativeIvyClassifiedArtifacts':classified,'runtimeJarSha256':sha(runtime),'ownedJarSha256':sha(own),'nativeClasspathJars':{Path(p).name:sha(Path(p)) for p in classpath.split(os.pathsep)}})
assert results[0]['actualJava'][0]!=results[1]['actualJava'][0]
controls={}
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
  generator.generate({'resources':str(resources),'sdk':model['sdk'],'sdkSource':model['sdkSource'],'runtimeNativeRepository':model['runtimeNativeRepository'],'runtimeRepository':model['runtimeRepository'],'runtimeCatalog':model['runtimeCatalog'],'runtimeSource':model['runtimeSource'],'publication':model['runtimePublicationModel'],'package':{'groupId':'org.example.schemas','artifactId':'answer','version':'1.0.0'}},folder/'out')
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
controls.update({'missing-import':True,'changed-source':True,'outside-import':True})
overlap=bundle('output-collision');update(overlap,'other.thrift','namespace java proof.common\nstruct Value {1: i64 other}\n');catalog=json.loads((overlap/'catalog.json').read_text());catalog['schema']['entrypoints'].append('other.thrift');(overlap/'catalog.json').write_text(json.dumps(catalog))
try:attempt('reject-output',overlap)
except ValueError as error:assert 'native generated Java outputs collide' in str(error);controls['generated-output-collision']=str(error)
else:raise AssertionError('accepted generated Java namespace collision')
ambiguous=bundle('ambiguous-program');path=ambiguous/'files/other/value.thrift';path.parent.mkdir();path.write_text('struct Other {1:i32 value}');catalog=json.loads((ambiguous/'catalog.json').read_text());catalog['files']['other/value.thrift']={'sha256':sha(path)};(ambiguous/'catalog.json').write_text(json.dumps(catalog))
try:attempt('reject-ambiguous',ambiguous)
except ValueError as error:assert 'ambiguous native program output name' in str(error);controls['ambiguous-program']=str(error)
else:raise AssertionError('accepted ambiguous native program names')
# The native Maven identity must match the compiler's actual SDK release.
import xml.etree.ElementTree as ET
foreign=Path('mismatched-sdk').resolve();pub=model['runtimeNativePublication'];original=next((Path(model['runtimeNativeRepository'])/pub['groupId'].replace('.','/')/pub['artifactId']).glob('*/*.pom'));destination=foreign/original.relative_to(Path(model['runtimeNativeRepository']));destination.parent.mkdir(parents=True);tree=ET.parse(original);tree.getroot().find('{http://maven.apache.org/POM/4.0.0}version').text='0.0.0';tree.write(destination)
try:generator.generate({'resources':model['resources'],'sdk':model['sdk'],'sdkSource':model['sdkSource'],'runtimeNativeRepository':str(foreign),'runtimeRepository':model['runtimeRepository'],'runtimeCatalog':model['runtimeCatalog'],'runtimeSource':model['runtimeSource'],'publication':model['runtimePublicationModel'],'package':{'groupId':'org.example.schemas','artifactId':'answer','version':'1.0.0'}},Path('reject-sdk-version').resolve())
except ValueError as error:assert 'native SDK publication differs' in str(error);controls['mismatched-sdk-release']=str(error)
else:raise AssertionError('accepted unrelated runtime SDK')
# A genuine offline Gradle consumer must fail without the required SDK provider.
case=spec['versions'][0];repository=Path(case['repository']);module=next(m for m in json.loads(Path(case['catalog']).read_text())['modules'] if m['group']=='org.example.schemas' and m['name']=='answer');missing=Path('missing-runtime-repo').resolve();relative=Path(module['group'].replace('.','/'))/module['name']/module['version'];shutil.copytree(repository/relative,missing/relative)
root=Path('missing-runtime-client').resolve();root.mkdir();(root/'settings.gradle').write_text("rootProject.name='missing-runtime'\n");(root/'config.json').write_text(json.dumps({'repository':str(missing),'coordinate':':'.join([module['group'],module['name'],module['version']])}));(root/'build.gradle').write_text("def selected=new groovy.json.JsonSlurper().parse(file('config.json'))\nrepositories { maven { url=uri(selected.repository);metadataSources {mavenPom();artifact()} } }\nconfigurations { runtime }\ndependencies { runtime(selected.coordinate) }\ntasks.register('resolveRuntime') {doLast {configurations.runtime.files}}\n")
env=dict(os.environ,HOME=str(root/'home'),GRADLE_USER_HOME=str(root/'gradle-home'));Path(env['HOME']).mkdir();command=['gradle','--offline','--no-daemon','--console=plain','resolveRuntime'];failed=subprocess.run(command,cwd=root,env=env,capture_output=True,text=True);coordinate=':'.join([model['runtimeModule']['group'],model['runtimeModule']['name'],model['runtimeModule']['version']]);expected='Could not find '+coordinate+'.';assert failed.returncode and expected in failed.stderr,(failed.stdout,failed.stderr)
print('Raw native missing-runtime Gradle stdout:',file=sys.stderr);print(failed.stdout,file=sys.stderr);print('Raw native missing-runtime Gradle stderr:',file=sys.stderr);print(failed.stderr,file=sys.stderr);controls['missing-runtime']={'argv':command,'exitCode':failed.returncode,'nativeDiagnostic':expected,'rawLogs':'retained verbatim in Nix build log'}
(out/'verification.json').write_text(json.dumps({'consumers':results,'rejectionControls':controls},indent=2)+'\n')
