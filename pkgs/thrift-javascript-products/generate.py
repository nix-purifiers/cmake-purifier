# SPDX-License-Identifier: MIT
"""Generate native Thrift JavaScript packages and bind their exact SDK module identity."""
import hashlib,json,re,shutil,subprocess,sys,tarfile
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

    options=spec['package'];exports=options['entrypoints']
    if any(not re.fullmatch(r'[A-Za-z_$][A-Za-z0-9_$]*',key) or not re.fullmatch(r'[A-Za-z0-9_-]+',value) for key,value in exports.items()):
        raise ValueError('npm entrypoints require explicit native module filenames and JavaScript identifiers')
    runtime_graph=json.loads(Path(spec['runtimeGraph']).read_text())
    native_manifest=json.loads((Path(spec['sdkSource'])/'package.json').read_text())
    if native_manifest['name']!='thrift' or native_manifest['version']!=native_version[1]:
        raise ValueError('native npm runtime differs from selected compiler')
    native_roots=[node for key,node in runtime_graph['nodes'].items() if key in runtime_graph['primaries'].values() and node['name']==native_manifest['name']]
    if len(native_roots)!=1 or native_roots[0]['package']!=native_manifest:
        raise ValueError('native runtime publication differs from selected SDK manifest')
    runtime_catalog=json.loads(Path(spec['runtimeCatalog']).read_text())
    sdk_modules=[module for module in runtime_catalog['modules'] if module['name']==native_manifest['name'] and module['primary']]
    if len(sdk_modules)!=1 or sdk_modules[0]['sourceVersion']!=native_manifest['version']:
        raise ValueError('runtime has no unique matched native npm publication')
    selected={};sources={}
    for view in [{'repository':spec['runtimeRepository'],'catalog':spec['runtimeCatalog']},*spec['extraInputs']]:
        for module in json.loads(Path(view['catalog']).read_text())['modules']:
            name=module['name']
            if name in selected and selected[name]['version']!=module['version']:
                raise ValueError('ambiguous provided native npm package: '+name)
            selected[name]=module;sources[name]=str(Path(view['repository'])/module['archive'])
    dependency_names={native_manifest['name'],*native_manifest.get('dependencies',{})}
    for view in spec['extraInputs']:
        dependency_names.update(m['name'] for m in json.loads(Path(view['catalog']).read_text())['modules'] if m['primary'])
    if not dependency_names<=set(selected):raise ValueError('SDK runtime dependency absent from captured native npm catalog')
    # Isolate each native program so a service name cannot overwrite another.
    isolated=output/'programs';isolated.mkdir();owners={}
    for name in sorted(models):
        folder=isolated/name;folder.mkdir();compile(names[name],'js:node,ts,es6',folder,False)
        for path in sorted(folder.iterdir()):
            if path.suffix not in ['.js','.ts']:continue
            if path.name in owners:raise ValueError('native generated JavaScript outputs collide: '+path.name)
            owners[path.name]=name;shutil.copyfile(path,generated/path.name)
    for alias,module in exports.items():
        if not (generated/(module+'.js')).is_file() or not (generated/(module+'.d.ts')).is_file():
            raise ValueError('explicit npm entrypoint absent from native generated outputs: '+module)
    package=out/'package';package.mkdir();shutil.copytree(generated,package/'generated')
    subprocess.run(['npm','init','--yes','--offline'],cwd=package,check=True)
    subprocess.run(['npm','pkg','delete','license','author','scripts','description','keywords'],cwd=package,check=True)
    manifest=json.loads((package/'package.json').read_text());manifest.update({'name':options['name'],'version':options['version'],'main':'index.cjs','types':'index.d.ts','files':['generated','index.cjs','index.mjs','index.d.ts'],'dependencies':{name:selected[name]['version'] for name in sorted(dependency_names)},'exports':{'.':{'types':'./index.d.ts','import':'./index.mjs','require':'./index.cjs'},**{'./'+alias:{'types':'./generated/'+module+'.d.ts','require':'./generated/'+module+'.js','import':'./generated/'+module+'.js'} for alias,module in exports.items()}}})
    (package/'package.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (package/'index.cjs').write_text(''.join('Object.defineProperty(exports, '+json.dumps(alias)+', {enumerable:true, value:require('+json.dumps('./generated/'+module+'.js')+')});\n' for alias,module in exports.items()))
    (package/'index.mjs').write_text(''.join('import __entry'+str(i)+' from '+json.dumps('./generated/'+module+'.js')+'; export { __entry'+str(i)+' as '+alias+' };\n' for i,(alias,module) in enumerate(exports.items())))
    (package/'index.d.ts').write_text(''.join('export * as '+alias+' from '+json.dumps('./generated/'+module+'.js')+';\n' for alias,module in exports.items()))
    for filename in ['index.cjs','index.mjs']:subprocess.run(['node','--check',str(package/filename)],check=True)
    archives=out/'archives';archives.mkdir();packed=json.loads(subprocess.check_output(['npm','pack','--offline','--ignore-scripts','--json','--pack-destination',str(archives)],cwd=package,text=True));archive=archives/packed[0]['filename']
    generated_hashes={p.name:digest(p) for p in generated.iterdir()}
    with tarfile.open(archive) as tar:
        if json.loads(tar.extractfile('package/package.json').read())!=manifest:raise ValueError('native npm publication differs from manifest')
        for name,expected in generated_hashes.items():
            if hashlib.sha256(tar.extractfile('package/generated/'+name).read()).hexdigest()!=expected:raise ValueError('native npm changed generated JavaScript or declarations')
    # Native npm resolves the supplied immutable archive closure. The native
    # capturer records transitive edges rather than inventing catalog joins.
    subprocess.run(['npm','install','--offline','--ignore-scripts','--no-save','--no-package-lock','--no-audit','--no-fund',*sorted(sources.values())],cwd=package,check=True)
    if json.loads((package/'package.json').read_text())!=manifest:raise ValueError('native npm changed the owned publication manifest')
    own=out/'native-packages.json';own.write_text(json.dumps([{'name':manifest['name'],'version':manifest['version'],'dir':''}]))
    # The capturer's release naming is the ordinary native purifier contract.
    canonical=archives/(manifest['name'].replace('@','').replace('/','__')+'.tgz')
    if canonical!=archive:shutil.copyfile(archive,canonical)
    capture=out/'native-capture'
    subprocess.run(['node',spec['captureTool'],str(package),str(archives),str(capture),str(own)],check=True)
    shutil.copyfile(capture/'graph.json',out/'graph.json')
    shutil.copytree(capture/'archives',archives,dirs_exist_ok=True)
    shutil.rmtree(package/'node_modules')
    record={'format':'purifier-thrift-javascript-v1','resources':str(bundle),'sdk':str(sdk),'sdkSource':spec['sdkSource'],'compilerVersion':version,'nativeModels':models,'nativeInputs':native_inputs,'capturedHashes':hashes,'generatedHashes':generated_hashes,'generatedOwners':owners,'nativeRuntimeManifest':native_manifest,'runtime':sdk_modules[0],'runtimeGraph':spec['runtimeGraph'],'runtimeRepository':spec['runtimeRepository'],'runtimeCatalog':spec['runtimeCatalog'],'extraInputs':spec['extraInputs'],'dependencyPublications':{name:selected[name] for name in sorted(dependency_names)},'nativePackage':manifest,'nativePack':packed,'commands':commands,'entrypoints':exports,'packageSourceHashes':{str(p.relative_to(package)):digest(p) for p in package.rglob('*') if p.is_file()}}
    (out/'thrift-javascript.json').write_text(json.dumps(record,sort_keys=True,indent=2)+'\n')

if __name__=='__main__':generate(json.loads(Path(sys.argv[1]).read_text()),Path(sys.argv[2]))
