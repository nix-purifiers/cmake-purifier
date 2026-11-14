# SPDX-License-Identifier: MIT
"""Package native FlatBuffers TypeScript modules with a native SDK npm provider."""
import hashlib,json,re,shutil,subprocess,sys,tarfile
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
    options=spec['package'];exports=options['entrypoints']
    if set(exports.values())!=set(catalog['schema']['entrypoints']):raise ValueError('npm entrypoints must select every captured schema root explicitly')
    if any(not re.fullmatch(r'\.|\./[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*',key) for key in exports):raise ValueError('invalid npm subpath export')
    native_runtime=json.loads((Path(spec['runtime'])/'sdk/package.json').read_text())
    if native_runtime['version']!=match[1]:raise ValueError('native npm runtime differs from compiler SDK')
    runtime_catalog=json.loads(Path(spec['runtimeCatalog']).read_text())
    runtime_modules=[m for m in runtime_catalog['modules'] if m['name']==native_runtime['name'] and m['primary']]
    if len(runtime_modules)!=1:raise ValueError('runtime has no unique native npm publication')
    selected_runtime=runtime_modules[0];runtime_archive=Path(spec['runtimeRepository'])/selected_runtime['archive']
    out.mkdir();proof=out/'proof';proof.mkdir()
    generated = proof/'generated';generated.mkdir()
    programs = proof/'programs';programs.mkdir()
    commands, models, hashes = [], {}, {}
    def run(command):
        subprocess.run(command, check=True)
        commands.append(command)
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
    package=out/'package';package.mkdir();sources=package/'src';sources.mkdir()
    entry_paths={};native_files={}
    for index,entry in enumerate(catalog['schema']['entrypoints']):
        native=sources/str(index);native.mkdir()
        run([compiler,'--ts','--gen-all','-I',str(root),'-o',str(native),str(root/entry)])
        # Keep whole native output trees isolated, including namespace barrels.
        entry_file=Path(entry).stem+'.ts'
        if not (native/entry_file).is_file():raise ValueError('native compiler omitted TypeScript root module')
        entry_paths[entry]=str(index)+'/'+entry_file[:-3]
        native_files.update({str(p.relative_to(package)):digest(p) for p in native.rglob('*.ts')})
    subprocess.run(['npm','init','--yes','--offline'],cwd=package,check=True)
    manifest=json.loads((package/'package.json').read_text());
    for field in ['license','author','scripts']:manifest.pop(field,None)
    manifest.update({'name':options['name'],'version':options['version'],'files':['lib','esm','browser','src'],'exports':{key:{'types':'./lib/'+entry_paths[value]+'.d.ts','require':'./lib/'+entry_paths[value]+'.js','import':'./esm/'+entry_paths[value]+'.js','default':'./lib/'+entry_paths[value]+'.js'} for key,value in exports.items()}})
    if '.' in exports:manifest.update({'main':'lib/'+entry_paths[exports['.']]+'.js','types':'lib/'+entry_paths[exports['.']]+'.d.ts'})
    (package/'package.json').write_text(json.dumps(manifest,indent=2)+'\n')
    subprocess.run(['npm','install','--offline','--ignore-scripts','--no-package-lock','--no-audit','--no-fund',str(runtime_archive)],cwd=package,check=True)
    subprocess.run(['npm','pkg','set','dependencies.'+selected_runtime['name']+'='+selected_runtime['version']],cwd=package,check=True)
    native_graph=json.loads(subprocess.check_output(['npm','ls','--all','--omit=dev','--json'],cwd=package,text=True))
    manifest=json.loads((package/'package.json').read_text());installed=json.loads((package/'node_modules'/selected_runtime['name']/'package.json').read_text())
    if native_graph['dependencies'][selected_runtime['name']]['version']!=selected_runtime['version'] or installed['version']!=selected_runtime['version']:raise ValueError('native npm installed another runtime')
    compiler_ts=Path(spec['runtime'])/'sdk/node_modules/typescript/bin/tsc'
    cjs_command=['node',str(compiler_ts),'--target','ES2020','--module','commonjs','--moduleResolution','node','--declaration','--rootDir','src','--outDir','lib','--listFiles',*[str(p.relative_to(package)) for p in sorted(sources.rglob('*.ts'))]]
    typed=subprocess.run(cjs_command,cwd=package,text=True,capture_output=True);print(typed.stdout,end='');print(typed.stderr,end='',file=sys.stderr);typed.check_returncode()
    (proof/'native-typescript-files.txt').write_text(typed.stdout)
    if str(package/'node_modules'/selected_runtime['name']) not in typed.stdout:raise ValueError('native TypeScript did not load selected runtime declarations')
    esm_command=['node',str(compiler_ts),'--target','ES2020','--module','ES2020','--moduleResolution','bundler','--declaration','--rootDir','src','--outDir','esm',*[str(p.relative_to(package)) for p in sorted(sources.rglob('*.ts'))]]
    subprocess.run(esm_command,cwd=package,check=True)
    (package/'esm/package.json').write_text('{"type":"module"}\n')
    browser=package/'browser';browser.mkdir();bundles={}
    for entry,path in entry_paths.items():
        stem=path.split('/')[0];metafile=proof/('browser-'+stem+'.json')
        command=['node',str(Path(spec['runtime'])/'sdk/node_modules/esbuild/bin/esbuild'),'src/'+path+'.ts','--bundle','--format=esm','--platform=browser','--outfile=browser/'+stem+'.mjs','--metafile='+str(metafile)]
        subprocess.run(command,cwd=package,check=True)
        meta=json.loads(metafile.read_text());inputs={}
        for name in meta['inputs']:
            source=(package/name).resolve(strict=True)
            if not source.is_relative_to(package):raise ValueError('browser bundle input escaped native package tree')
            inputs[name]=digest(source)
        if not any(name.startswith('node_modules/'+selected_runtime['name']+'/') for name in inputs):raise ValueError('native browser bundler did not capture runtime source')
        bundles[entry]={'file':'browser/'+stem+'.mjs','sha256':digest(browser/(stem+'.mjs')),'nativeMetafile':meta,'inputHashes':inputs,'command':command}
    runtime_meta=proof/'browser-runtime.json'
    runtime_command=['node',str(Path(spec['runtime'])/'sdk/node_modules/esbuild/bin/esbuild'),str(Path(spec['runtime'])/'sdk/mjs/flatbuffers.js'),'--bundle','--format=esm','--platform=browser','--outfile=browser/runtime.mjs','--metafile='+str(runtime_meta)]
    subprocess.run(runtime_command,cwd=package,check=True)
    runtime_native_meta=json.loads(runtime_meta.read_text());runtime_inputs={}
    runtime_root=(Path(spec['runtime'])/'sdk').resolve(strict=True)
    for name in runtime_native_meta['inputs']:
        path=(package/name).resolve(strict=True)
        if not path.is_relative_to(runtime_root):raise ValueError('browser runtime input escapes selected SDK output')
        runtime_inputs[str(path.relative_to(runtime_root))]=digest(path)
    runtime_bundle={'file':'browser/runtime.mjs','sha256':digest(browser/'runtime.mjs'),'nativeMetafile':runtime_native_meta,'inputHashes':runtime_inputs,'command':runtime_command}
    archives=out/'archives';archives.mkdir();packed=json.loads(subprocess.check_output(['npm','pack','--offline','--ignore-scripts','--json','--pack-destination',str(archives)],cwd=package,text=True));archive=archives/packed[0]['filename']
    with tarfile.open(archive) as tar:
        if json.loads(tar.extractfile('package/package.json').read())!=manifest:raise ValueError('native npm archive metadata differs')
        for name,expected in native_files.items():
            if hashlib.sha256(tar.extractfile('package/'+name).read()).hexdigest()!=expected:raise ValueError('native npm archive changed generated TypeScript')
    graph={'version':1,'primaries':{manifest['name']:'owned'},'nodes':{'owned':{'name':manifest['name'],'version':manifest['version'],'package':manifest,'archive':archive.name,'contentHash':digest(archive),'dependencies':{selected_runtime['name']:{'target':'runtime','type':'dependencies'}}},'runtime':{'name':installed['name'],'version':installed['version'],'package':installed,'contentHash':digest(runtime_archive),'dependencies':{}}}}
    (out/'graph.json').write_text(json.dumps(graph,sort_keys=True,indent=2)+'\n')
    record={'format':'purifier-flatbuffers-typescript-v1','resources':str(bundle),'sdk':str(sdk),'sdkSource':spec['sdkSource'],'compilerVersion':version,'reflectionSchema':str(reflection),'reflectionSchemaSha256':digest(reflection),'schemaHashes':hashes,'nativeSchemas':models,'nativeTypeScriptHashes':native_files,'entryPaths':entry_paths,'runtime':selected_runtime,'runtimeSource':spec['runtime'],'runtimeRepository':spec['runtimeRepository'],'nativeNpmGraph':native_graph,'nativePackage':manifest,'nativePack':packed,'typescriptCommand':cjs_command,'esmCommand':esm_command,'browserBundles':bundles,'browserRuntimeBundle':runtime_bundle,'compiledHashes':{str(p.relative_to(package)):digest(p) for folder in ['lib','esm','browser'] for p in (package/folder).rglob('*') if p.is_file()},'commands':commands}
    (out/'flatbuffers-typescript.json').write_text(json.dumps(record,sort_keys=True,indent=2)+'\n')

if __name__=='__main__':generate(json.loads(Path(sys.argv[1]).read_text()),Path(sys.argv[2]))
