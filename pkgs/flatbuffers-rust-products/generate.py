# SPDX-License-Identifier: MIT
"""Package native FlatBuffers Rust modules with a native SDK Cargo provider."""
import hashlib,json,re,shutil,subprocess,sys,tomllib
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
    runtime = json.loads(Path(spec['runtimeCatalog']).read_text())
    runtime_manifest=tomllib.loads((Path(spec['runtime'])/'Cargo.toml').read_text())['package']
    if runtime_manifest['name']!='flatbuffers' or runtime_manifest['version']!=match[1]:raise ValueError('native Rust runtime differs from selected compiler')
    runtime_packages=[p for p in runtime['packages'] if p['name']==runtime_manifest['name']]
    if len(runtime_packages)!=1:raise ValueError('runtime has no unique native Cargo publication')
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
    # The SDK type-per-file mode keeps shared namespaces in one module.
    # Retain each native root file; only crate module wiring is adapter-owned.
    native_roots={}
    for index,entry in enumerate(catalog['schema']['entrypoints']):
        native=programs/('rust-'+str(index));native.mkdir()
        run([compiler,'--rust','--rust-module-root-file','--gen-all','-I',str(root),'-o',str(native),str(root/entry)])
        native_roots[entry]=(native/'mod.rs').read_text()
        for path in sorted(native.rglob('*.rs')):
            if path==native/'mod.rs':continue
            target=generated/path.relative_to(native)
            if target.exists():
                if target.read_bytes()!=path.read_bytes():raise ValueError('native generated Rust outputs collide: '+str(path.relative_to(native)))
            else:
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    crate=out/'crate'
    subprocess.run(['cargo','init','--lib','--name',spec['name'],'--edition',runtime_manifest['edition'],'--vcs','none',str(crate)],check=True)
    (crate/'.cargo').mkdir();config=crate/'.cargo/config.toml';config.write_text('[source.crates-io]\nreplace-with="sdk"\n[source.sdk]\nlocal-registry='+json.dumps(spec['runtimeRepository'])+'\n')
    subprocess.run(['cargo','add','--offline',runtime_packages[0]['name']+'@='+runtime_packages[0]['version']],cwd=crate,check=True)
    sources=sorted(generated.rglob('*.rs'))
    if not sources:raise ValueError('native compiler generated no Rust modules')
    tree={}
    for path in sources:
        relative=path.relative_to(generated);node=tree
        for part in relative.parts[:-1]:
            if not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',part):raise ValueError('native Rust namespace has no valid identifier')
            node=node.setdefault(part,{})
        if not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',path.stem):raise ValueError('native Rust module has no valid identifier')
        if path.stem in node:raise ValueError('native Rust namespace/module name collision')
        node[path.stem]=None
        target=crate/'src'/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    def modules(node,indent=''):
        lines=[]
        for name,children in sorted(node.items()):
            if children is None:lines += [indent+'mod r#'+name+';',indent+'pub use self::r#'+name+'::*;']
            else:lines += [indent+'pub mod r#'+name+' {',indent+'  use super::*;',*modules(children,indent+'  '),indent+'}']
        return lines
    (crate/'src/lib.rs').write_text('\n'.join(modules(tree))+'\n')
    subprocess.run(['cargo','generate-lockfile','--offline'],cwd=crate,check=True)
    metadata=json.loads(subprocess.check_output(['cargo','metadata','--offline','--locked','--format-version=1'],cwd=crate,text=True))
    config.unlink();config.parent.rmdir()
    record={'format':'purifier-flatbuffers-rust-v1','resources':str(bundle),'sdk':str(sdk),'compilerVersion':version,'reflectionSchema':str(reflection),'reflectionSchemaSha256':digest(reflection),'schemaHashes':hashes,'nativeSchemas':models,'generatedHashes':{str(p.relative_to(generated)):digest(p) for p in sources},'crateSourceHashes':{str(p.relative_to(crate)):digest(p) for p in (crate/'src').rglob('*.rs')},'runtime':runtime_packages[0],'runtimeManifest':str(Path(spec['runtime'])/'Cargo.toml'),'runtimeSource':spec['runtime'],'commands':commands,'nativeRootModules':native_roots,'moduleTree':tree,'metadata':metadata}
    (out/'flatbuffers-rust.json').write_text(json.dumps(record,sort_keys=True,indent=2)+'\n')


if __name__=='__main__':generate(json.loads(Path(sys.argv[1]).read_text()),Path(sys.argv[2]))
