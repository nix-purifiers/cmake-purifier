# SPDX-License-Identifier: MIT
"""Generate native Thrift Go packages and bind their exact SDK module identity."""
import hashlib,json,re,shutil,subprocess,sys
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

    # Generate every native program separately. This exposes output collisions
    # before the recursive generator could silently overwrite a shared namespace.
    isolated=output/'programs';isolated.mkdir()
    for name in sorted(models):
        folder=isolated/name;folder.mkdir()
        compile(names[name],'go:package_prefix='+spec['modulePath']+'/',folder,False)
        for path in sorted(folder.rglob('*')):
            if not path.is_file() or path.name.endswith('-compiler.log'):continue
            target=generated/path.relative_to(folder)
            if target.exists():
                if target.read_bytes()!=path.read_bytes():raise ValueError('native generated Go outputs collide: '+str(path.relative_to(folder)))
            else:
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    sdk_mod=json.loads(subprocess.check_output(['go','mod','edit','-json',str(Path(spec['sdkSource'])/'go.mod')],text=True))
    catalog=json.loads(Path(spec['runtimeCatalog']).read_text())
    if catalog['format']!='go':raise ValueError('runtime catalog is not a native Go module proxy')
    selected=[m for m in catalog['modules'] if m['path']==sdk_mod['Module']['Path']]
    if len(selected)!=1:raise ValueError('native SDK runtime has no unique projected module identity')
    module=out/'module';module.mkdir();shutil.copytree(generated,module,dirs_exist_ok=True)
    subprocess.run(['go','mod','init',spec['modulePath']],cwd=module,check=True)
    subprocess.run(['go','mod','edit','-go='+sdk_mod['Go'],'-require='+selected[0]['path']+'@'+selected[0]['version']],cwd=module,check=True)
    sources={str(p.relative_to(module)):digest(p) for p in sorted(module.rglob('*.go'))}
    if not sources:raise ValueError('native Thrift compiler generated no Go sources')
    record={'format':'purifier-thrift-go-v1','resources':str(bundle),'sdk':str(sdk),'sdkSource':spec['sdkSource'],'compilerVersion':version,'nativeInputs':native_inputs,'nativeModels':models,'programSources':{name:names[name] for name in models},'capturedHashes':hashes,'generatedHashes':sources,'commands':commands,'runtimeModule':selected[0],'runtimeGoVersion':sdk_mod['Go'],'modulePath':spec['modulePath']}
    (out/'thrift-go.json').write_text(json.dumps(record,sort_keys=True,indent=2)+'\n')


if __name__=='__main__':generate(json.loads(Path(sys.argv[1]).read_text()),Path(sys.argv[2]))
