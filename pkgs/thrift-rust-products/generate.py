# SPDX-License-Identifier: MIT
"""Generate native Thrift Rust crates and bind their exact SDK module identity."""
import hashlib,json,re,shutil,subprocess,sys,tomllib
from pathlib import Path,PurePosixPath


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(spec,out):
    output=out.resolve()
    bundle=Path(spec['resources']);root=(bundle/'files').resolve(strict=True)
    catalog=json.loads((bundle/'catalog.json').read_text())
    if catalog['format']!='purifier-resources-v1' or catalog['schema']['format']!='thrift':
        raise ValueError('expected an explicitly selected Thrift schema bundle')
    names={}
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
            if names.setdefault(actual.stem,logical)!=logical:raise ValueError('ambiguous active native program source: '+logical)
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

    runtime_manifest=tomllib.loads((Path(spec['runtime'])/'Cargo.toml').read_text())['package']
    if runtime_manifest['name']!='thrift' or runtime_manifest['version']!=native_version[1]:
        raise ValueError('native Rust runtime differs from selected compiler')
    runtime_catalog=json.loads(Path(spec['runtimeCatalog']).read_text())
    runtime_packages=[p for p in runtime_catalog['packages'] if p['name']==runtime_manifest['name']]
    if len(runtime_packages)!=1:raise ValueError('runtime has no unique native Cargo publication')
    isolated=output/'programs';isolated.mkdir()
    for name in sorted(models):
        folder=isolated/name;folder.mkdir()
        compile(names[name],'rs',folder,False)
        sources=sorted(folder.glob('*.rs'))
        if len(sources)!=1 or sources[0].stem!=name:
            raise ValueError('native Rust program output differs from native input model')
        for path in sources:
            target=generated/path.name
            if target.exists():raise ValueError('native generated Rust outputs collide: '+path.name)
            shutil.copyfile(path,target)
    crate=out/'crate'
    subprocess.run(['cargo','init','--lib','--name',spec['name'],'--edition',runtime_manifest['edition'],'--vcs','none',str(crate)],check=True)
    (crate/'.cargo').mkdir();config=crate/'.cargo/config.toml'
    config.write_text('[source.crates-io]\nreplace-with="sdk"\n[source.sdk]\nlocal-registry='+json.dumps(spec['runtimeRepository'])+'\n')
    subprocess.run(['cargo','add','--offline',runtime_packages[0]['name']+'@='+runtime_packages[0]['version']],cwd=crate,check=True)
    sources=sorted(generated.glob('*.rs'))
    if not sources:raise ValueError('native Thrift compiler generated no Rust sources')
    modules=[]
    (crate/'src/generated').mkdir()
    for path in sources:
        if not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',path.stem) or path.stem in ['self','super','crate','Self']:
            raise ValueError('native Rust program has no valid crate module identifier')
        shutil.copyfile(path,crate/'src/generated'/path.name)
        modules.append('#[path = '+json.dumps('generated/'+path.name)+']\npub mod r#'+path.stem+';')
    (crate/'src/lib.rs').write_text('\n'.join(modules)+'\n')
    subprocess.run(['cargo','generate-lockfile','--offline'],cwd=crate,check=True)
    metadata=json.loads(subprocess.check_output(['cargo','metadata','--offline','--locked','--format-version=1'],cwd=crate,text=True))
    config.unlink();config.parent.rmdir()
    record={'format':'purifier-thrift-rust-v1','resources':str(bundle),'sdk':str(sdk),'sdkSource':spec['sdkSource'],'compilerVersion':version,'nativeInputs':native_inputs,'nativeModels':models,'programSources':{name:names[name] for name in models},'capturedHashes':hashes,'generatedHashes':{p.name:digest(p) for p in sources},'crateSourceHashes':{str(p.relative_to(crate)):digest(p) for p in (crate/'src').rglob('*.rs')},'runtime':runtime_packages[0],'runtimeManifest':str(Path(spec['runtime'])/'Cargo.toml'),'runtimeSource':spec['runtime'],'commands':commands,'metadata':metadata,'upstreamRustTargetWarning':'Selected native Thrift compiler warns that Rust is deprecated due to lack of active maintainers; raw compiler logs retained.'}
    (out/'thrift-rust.json').write_text(json.dumps(record,sort_keys=True,indent=2)+'\n')


if __name__=='__main__':generate(json.loads(Path(sys.argv[1]).read_text()),Path(sys.argv[2]))
