# SPDX-License-Identifier: MIT
"""Compile native FlatBuffers Java output against its native Maven SDK runtime."""
import hashlib,json,re,shutil,subprocess,sys,zipfile
from pathlib import Path


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(spec,out):
    bundle = Path(spec['resources'])
    catalog = json.loads((bundle/'catalog.json').read_text())
    if catalog['format'] != 'purifier-resources-v1' or catalog['schema']['format'] != 'flatbuffers':
        raise ValueError('expected an explicitly selected FlatBuffers schema bundle')
    root = (bundle/'files').resolve(strict=True)
    sdk = Path(spec['sdk'])
    compiler = str(sdk/'bin/flatc')
    reflection = Path(spec['sdkSource'])/'reflection/reflection.fbs'
    version = subprocess.check_output([compiler, '--version'], text=True).strip()
    match = re.fullmatch(r'flatc version (\d+\.\d+\.\d+)', version)
    if match is None:
        raise ValueError('cannot read native flatc version')
    runtime = json.loads((Path(spec['runtime'])/'proof/model.json').read_text())
    if runtime['compilerVersion'] != version or runtime['coordinates']['version'] != match[1]:
        raise ValueError('native Java runtime differs from selected flatc')
    out.mkdir();proof=out/'proof';proof.mkdir();generated = out/'generated';generated.mkdir()
    programs = proof/'programs';programs.mkdir()
    commands, models, hashes = [], {}, {}
    def run(command):
        result=subprocess.run(command,capture_output=True,text=True)
        index=len(commands);commands.append(command)
        (proof/f'command-{index}.stdout').write_text(result.stdout)
        (proof/f'command-{index}.stderr').write_text(result.stderr)
        if result.returncode:raise subprocess.CalledProcessError(result.returncode,command,result.stdout,result.stderr)
    for index, entry in enumerate(catalog['schema']['entrypoints']):
        source = (root/entry).resolve(strict=True)
        if not source.is_relative_to(root):
            raise ValueError('entrypoint escapes captured schema tree')
        folder = programs/str(index);folder.mkdir()
        run([compiler, '--binary', '--schema', '--bfbs-absolute-paths', '-I', str(root), '-o', str(folder), str(source)])
        binary = folder/(source.stem+'.bfbs')
        run([compiler, '--json', '--strict-json', '-o', str(folder), str(reflection), '--', str(binary)])
        model = json.loads((folder/(source.stem+'.json')).read_text())
        files = model.get('fbs_files', [])
        if not files:
            raise ValueError('native reflection omitted input file graph')
        selected = set()
        for record in files:
            path = Path(record['filename'])
            if not path.is_absolute():
                raise ValueError('native reflection did not retain absolute input paths')
            path = path.resolve(strict=True)
            if not path.is_relative_to(root):
                raise ValueError('native schema input escapes captured tree: '+str(path))
            logical = path.relative_to(root).as_posix()
            if logical not in catalog['files'] or digest(path) != catalog['files'][logical]['sha256']:
                raise ValueError('native schema input differs from captured hash: '+logical)
            hashes[logical] = digest(path);selected.add(str(path))
        if str(source) not in selected:
            raise ValueError('native reflection omitted selected entrypoint')
        for record in files:
            if any(str(Path(name).resolve(strict=True)) not in selected for name in record.get('included_filenames', [])):
                raise ValueError('native reflection include graph is incomplete')
        models[entry] = {'schema': model, 'binarySha256': digest(binary)}
    # Preserve the compiler's normal per-schema Java package layout.
    for index, logical in enumerate(sorted(hashes)):
        native=programs/('java-'+str(index));native.mkdir()
        run([compiler,'--java','-I',str(root),'-o',str(native),str(root/logical)])
        for path in sorted(native.rglob('*')):
            if not path.is_file():continue
            target=generated/path.relative_to(native)
            if target.exists():
                if target.read_bytes()!=path.read_bytes():raise ValueError('native generated Java outputs collide: '+str(path.relative_to(native)))
            else:
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    runtime_root=Path(spec['runtime']);jdk=Path(spec['jdk']);maven=Path(spec['maven'])
    sources=sorted(generated.rglob('*.java'))
    if not sources:raise ValueError('native compiler generated no Java sources')
    for path in sources:
        if str(path.relative_to(generated).with_suffix('.class')) in runtime['classes']:
            raise ValueError('generated Java type collides with native runtime: '+str(path.relative_to(generated)))
    classes=Path('classes').resolve();classes.mkdir()
    source_list=proof/'javac-sources.txt'
    source_list.write_text('\n'.join('"'+str(p).replace('\\','\\\\').replace('"','\\"')+'"' for p in sources)+'\n')
    release=runtime['classMajor']-44
    run([str(jdk/'bin/javac'),'-verbose','-encoding','UTF-8','--release',str(release),'-cp',str(runtime_root/'runtime.jar'),'-d',str(classes),'@'+str(source_list)])
    manifest=Path('MANIFEST.MF');manifest.write_text('Manifest-Version: 1.0\nImplementation-Version: '+spec['version']+'\n\n')
    jar=out/'bindings.jar'
    run([str(jdk/'bin/jar'),'--create','--date=1980-01-01T00:00:02Z','--file',str(jar),'--manifest',str(manifest),'-C',str(classes),'.'])
    with zipfile.ZipFile(jar) as z:
        compiled={name:hashlib.sha256(z.read(name)).hexdigest() for name in z.namelist() if name.endswith('.class')}
        if set(compiled)&set(runtime['classes']):raise ValueError('compiled Java output shadows SDK runtime class')
        if not compiled or any(int.from_bytes(z.read(name)[6:8],'big')!=runtime['classMajor'] for name in compiled):raise ValueError('compiled Java target differs from native SDK base class target')
    driver=Path('publisher').resolve();driver.mkdir()
    sdk_classpath=str(maven/'maven/lib')+'/*'
    run([str(jdk/'bin/javac'),'-cp',sdk_classpath,'-d',str(driver),spec['publisherSource']])
    c=runtime['coordinates'];repository=out/'repository'/spec['groupId'].replace('.','/')/spec['artifactId']/spec['version'];repository.mkdir(parents=True)
    name=spec['artifactId']+'-'+spec['version']
    run([str(jdk/'bin/java'),'-cp',sdk_classpath+':'+str(driver),'Publish',spec['groupId'],spec['artifactId'],spec['version'],c['groupId'],c['artifactId'],c['version'],str(repository/(name+'.pom'))])
    shutil.copyfile(jar,repository/(name+'.jar'))
    record={'format':'purifier-flatbuffers-java-v1','resources':str(bundle),'sdk':str(sdk),'compilerVersion':version,'reflectionSchema':str(reflection),'reflectionSchemaSha256':digest(reflection),'schemaHashes':hashes,'nativeSchemas':models,'generatedHashes':{str(p.relative_to(generated)):digest(p) for p in sources},'runtime':runtime,'runtimePath':str(runtime_root),'commands':commands,'classMajor':runtime['classMajor'],'classes':compiled,'jarSha256':digest(jar),'jdk':str(jdk),'maven':str(maven)}
    (proof/'model.json').write_text(json.dumps(record,sort_keys=True,indent=2)+'\n')


if __name__=='__main__':generate(json.loads(Path(sys.argv[1]).read_text()),Path(sys.argv[2]))
