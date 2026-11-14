# SPDX-License-Identifier: MIT
"""Generate native Thrift Java packages and publish their native Gradle runtime dependency."""
import hashlib,json,re,shutil,subprocess,sys,tarfile,zipfile
from pathlib import Path,PurePosixPath


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(spec,out):
    output=out.resolve()
    bundle=Path(spec['resources']);root=(bundle/'files').resolve(strict=True)
    catalog=json.loads((bundle/'catalog.json').read_text())
    if catalog['format']!='purifier-resources-v1' or catalog['schema']['format']!='thrift':
        raise ValueError('expected an explicitly selected Thrift schema bundle')
    names={}
    for name in catalog['files']:
        path=PurePosixPath(name)
        if path.suffix=='.thrift':
            if path.stem in names:
                raise ValueError('ambiguous native program output name: '+path.stem)
            names[path.stem]=name
    sdk=Path(spec['sdk']);compiler=str(sdk/'bin/thrift')
    version=subprocess.check_output([compiler,'--version'],text=True).strip()
    native_version=re.fullmatch(r'Thrift version (\d+\.\d+\.\d+)',version)
    if native_version is None:raise ValueError('cannot read native Thrift SDK version: '+version)
    output.mkdir(parents=True,exist_ok=True);generated=output/'generated';ast=output/'ast';generated.mkdir();ast.mkdir()
    commands=[];native_inputs={}
    def compile(entry,target,folder,recursive):
        path=(root/entry).resolve(strict=True)
        if not path.is_relative_to(root):raise ValueError('entrypoint escapes captured schema tree')
        command=[compiler,'-v']+(['-r'] if recursive else [])+['-I',str(root),'--gen',target,'-out',str(folder),str(path)]
        result=subprocess.run(command,cwd=root,check=True,text=True,capture_output=True);commands.append(command)
        evidence={phase:set() for phase in ['Scanning','Parsing','Program']}
        for line in result.stdout.splitlines():
            match=re.fullmatch(r'(Scanning|Parsing) (.+) for (?:includes|types)',line)
            if match:phase,source=match.groups()
            elif line.startswith('Program: '):phase,source='Program',line[len('Program: '):]
            else:continue
            actual=Path(source).resolve(strict=True)
            if not actual.is_relative_to(root):raise ValueError('native compiler input escapes captured schema tree: '+source)
            logical=actual.relative_to(root).as_posix()
            if logical not in catalog['files']:raise ValueError('native compiler input absent from captured catalog: '+logical)
            if names.get(actual.stem)!=logical:raise ValueError('ambiguous native program source: '+logical)
            evidence[phase].add(logical)
        if not evidence['Program'] or evidence['Scanning']!=evidence['Parsing']:
            raise ValueError('incomplete native compiler input evidence')
        if recursive:
            if evidence['Program']!=evidence['Parsing']:raise ValueError('incomplete recursive generation evidence')
        elif evidence['Program']!={path.relative_to(root).as_posix()} or not evidence['Program']<=evidence['Parsing']:
            raise ValueError('native compiler did not generate selected program alone')
        native_inputs[f'{entry}:{target}']={phase:sorted(paths) for phase,paths in evidence.items()}
        (folder/(Path(entry).stem+'-compiler.log')).write_text(result.stdout+result.stderr)
    for entry in catalog['schema']['entrypoints']:compile(entry,'json',ast,True)
    models={p.stem:json.loads(p.read_text()) for p in sorted(ast.glob('*.json'))}
    if not models:raise ValueError('native Thrift compiler produced no schema models')
    for name,model in models.items():
        if name not in names:raise ValueError('native schema model has no captured source: '+name)
        for imported in model['includes']:
            if imported not in models:raise ValueError('native compiler omitted imported program: '+imported)
    # Keep every selected source byte. Native recursive compilation determines
    # the used program graph; this adapter does not lex or resolve Thrift IDL.
    hashes={}
    for name,record in catalog['files'].items():
        path=root/name
        if not path.resolve(strict=True).is_relative_to(root):raise ValueError('captured resource escapes schema tree')
        actual=digest(path)
        if actual!=record['sha256']:raise ValueError('schema does not match captured resource hash: '+name)
        hashes[name]=actual

    isolated=output/'programs';isolated.mkdir()
    for name in sorted(models):
        folder=isolated/name;folder.mkdir()
        compile(names[name],'java:jakarta_annotations,generated_annotations=undated',folder,False)
        for path in sorted(folder.rglob('*.java')):
            target=generated/path.relative_to(folder)
            if target.exists():
                if target.read_bytes()!=path.read_bytes():raise ValueError('native generated Java outputs collide: '+str(path.relative_to(folder)))
            else:
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    import xml.etree.ElementTree as ET
    publication=spec['publication'];relative=publication['groupId'].replace('.','/')+'/'+publication['artifactId']
    poms=list((Path(spec['runtimeNativeRepository'])/relative).glob('*/*.pom'))
    if len(poms)!=1:raise ValueError('SDK runtime has no unique native Maven POM')
    ns={'m':'http://maven.apache.org/POM/4.0.0'};native=ET.parse(poms[0]).getroot();coordinate={field:native.find('m:'+field,ns).text for field in ['groupId','artifactId','version']}
    if coordinate['groupId']!=publication['groupId'] or coordinate['artifactId']!=publication['artifactId'] or coordinate['version']!=native_version[1]:raise ValueError('native SDK publication differs from selected compiler')
    catalog=json.loads(Path(spec['runtimeCatalog']).read_text());selected=[m for m in catalog['modules'] if m['group']==coordinate['groupId'] and m['name']==coordinate['artifactId'] and m['originalVersion']==coordinate['version']]
    if len(selected)!=1:raise ValueError('SDK runtime has no unique typed Maven publication')
    sdk_jar=poms[0].with_suffix('.jar')
    with zipfile.ZipFile(sdk_jar) as jar:
        bytecode=jar.read('org/apache/thrift/TBase.class');release=int.from_bytes(bytecode[6:8],'big')-44
        for name,source in [('META-INF/LICENSE.txt','LICENSE'),('META-INF/NOTICE.txt','NOTICE')]:
            if jar.read(name)!=(Path(spec['sdkSource'])/source).read_bytes():raise ValueError('native runtime omitted SDK license resource')
    package=out/'package';java=package/'src/main/java';java.mkdir(parents=True);shutil.copytree(generated,java,dirs_exist_ok=True)
    properties={'repository':spec['runtimeRepository'],'coordinate':':'.join([selected[0]['group'],selected[0]['name'],selected[0]['version']]),'group':spec['package']['groupId'],'name':spec['package']['artifactId'],'version':spec['package']['version'],'release':release,'publication':str(out/'repository')}
    (package/'config.json').write_text(json.dumps(properties));(package/'settings.gradle').write_text('rootProject.name='+json.dumps(properties['name'])+'\n')
    (package/'build.gradle').write_text("""import groovy.json.JsonOutput
plugins { id 'java-library'; id 'maven-publish' }
def selected=new groovy.json.JsonSlurper().parse(file('config.json'))
group=selected.group
version=selected.version
repositories { maven { url=uri(selected.repository); metadataSources { mavenPom(); artifact() } } }
configurations { sdkRuntime { canBeResolved=true; canBeConsumed=false } }
dependencies { api(selected.coordinate); sdkRuntime(selected.coordinate) }
sourceSets.main.compileClasspath += configurations.sdkRuntime
tasks.withType(JavaCompile).configureEach { options.release=selected.release }
tasks.withType(AbstractArchiveTask).configureEach { preserveFileTimestamps=false; reproducibleFileOrder=true }
java { withSourcesJar() }
publishing { publications { mavenJava(MavenPublication) { from components.java } }; repositories { maven { name='purifier'; url=uri(selected.publication) } } }
tasks.register('retainNativeModel') { dependsOn 'jar'; doLast {
 file('native-gradle-model.json').text=JsonOutput.toJson([
  runtimeArtifacts:configurations.sdkRuntime.resolvedConfiguration.resolvedArtifacts.collect { [group:it.moduleVersion.id.group,name:it.name,version:it.moduleVersion.id.version,classifier:it.classifier,file:it.file.canonicalPath] },
  compileClasspath:sourceSets.main.compileClasspath.files.collect { it.canonicalPath },
  sources:sourceSets.main.java.files.collect { it.canonicalPath },
  release:tasks.compileJava.options.release.get(),publication:[group:project.group.toString(),name:project.name,version:project.version.toString()]
 ])
} }
""")
    command=['gradle','--offline','--no-daemon','--console=plain','publishMavenJavaPublicationToPurifierRepository','retainNativeModel']
    result=subprocess.run(command,cwd=package,capture_output=True,text=True);print(result.stdout,end='');print(result.stderr,end='',file=sys.stderr);result.check_returncode()
    native_model=json.loads((package/'native-gradle-model.json').read_text())
    source_hashes={str(p.relative_to(java)):digest(p) for p in sorted(java.rglob('*.java'))}
    if not source_hashes:raise ValueError('native compiler generated no Java sources')
    if set(native_model['sources'])!={str(java/name) for name in source_hashes}:raise ValueError('native Gradle compiled another source graph')
    source_archives=list((out/'repository').rglob('*-sources.jar'))
    if len(source_archives)!=1:raise ValueError('native Gradle omitted unique source publication')
    with zipfile.ZipFile(source_archives[0]) as jar:
        for name,expected in source_hashes.items():
            if __import__('hashlib').sha256(jar.read(name)).hexdigest()!=expected:raise ValueError('native source archive changed generated Java')
    # Native publication indexes aggregate available versions and contain the
    # wall clock's lastUpdated. Export the versioned component files instead.
    component=(out/'repository'/spec['package']['groupId'].replace('.','/')/spec['package']['artifactId'])
    indexes=[]
    for path in sorted(component.glob('maven-metadata.xml*')):
        if path.name=='maven-metadata.xml':print('Raw native Maven repository index:\n'+path.read_text(),file=sys.stderr)
        indexes.append(str(path.relative_to(out/'repository')));path.unlink()
    record={'format':'purifier-thrift-java-v1','resources':str(bundle),'sdk':str(sdk),'sdkSource':spec['sdkSource'],'compilerVersion':version,'nativeInputs':native_inputs,'nativeModels':models,'programSources':{name:names[name] for name in models},'capturedHashes':hashes,'generatedHashes':source_hashes,'commands':commands,'runtimePublicationModel':publication,'runtimeNativeRepository':spec['runtimeNativeRepository'],'runtimeRepository':spec['runtimeRepository'],'runtimeCatalog':spec['runtimeCatalog'],'runtimeNativePublication':coordinate,'runtimeModule':selected[0],'runtimeSource':spec['runtimeSource'],'nativeRuntimeJar':str(sdk_jar),'nativeRuntimeJarSha256':digest(sdk_jar),'nativeRelease':release,'nativeGradleModel':native_model,'gradleCommand':command,'omittedUnversionedRepositoryIndexes':indexes}
    (out/'thrift-java.json').write_text(json.dumps(record,sort_keys=True,indent=2)+'\n')
    # Publications, sources and the native model are exported; Gradle's working
    # caches and intermediate outputs are not part of this library artifact.
    for directory in [package/'.gradle',package/'build']:
        if directory.exists():shutil.rmtree(directory)


if __name__=='__main__':generate(json.loads(Path(sys.argv[1]).read_text()),Path(sys.argv[2]))
