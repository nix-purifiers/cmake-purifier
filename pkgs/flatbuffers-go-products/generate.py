# SPDX-License-Identifier: MIT
"""Package native FlatBuffers Go modules with a native SDK Go provider."""
import hashlib,json,re,shutil,subprocess,sys
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
    runtime_catalog=json.loads(Path(spec['runtimeCatalog']).read_text())
    sdk_mod=json.loads(subprocess.check_output(['go','mod','edit','-json',str(Path(spec['runtimeSource'])/'go.mod')],text=True))
    if sdk_mod['Module']['Path']!=spec['runtimeModulePath']:raise ValueError('SDK runtime module differs from explicit identity')
    runtime_packages=[m for m in runtime_catalog['modules'] if m['path']==spec['runtimeModulePath']]
    if len(runtime_packages)!=1:raise ValueError('SDK runtime has no unique native Go publication')
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
    for index,entry in enumerate(catalog['schema']['entrypoints']):
        native=programs/('go-'+str(index));native.mkdir()
        run([compiler,'--go','--gen-all','--go-module-name',spec['modulePath'],'--go-import',spec['runtimeModulePath'],'-I',str(root),'-o',str(native),str(root/entry)])
        for path in sorted(native.rglob('*.go')):
            target=generated/path.relative_to(native)
            if target.exists():
                if target.read_bytes()!=path.read_bytes():raise ValueError('native generated Go outputs collide: '+str(path.relative_to(native)))
            else:
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    module=out/'module';shutil.copytree(generated,module)
    subprocess.run(['go','mod','init',spec['modulePath']],cwd=module,check=True)
    subprocess.run(['go','mod','edit','-go='+sdk_mod['Go'],'-require='+runtime_packages[0]['path']+'@'+runtime_packages[0]['version']],cwd=module,check=True)
    sources={str(p.relative_to(module)):digest(p) for p in sorted(module.rglob('*.go'))}
    if not sources:raise ValueError('native compiler generated no Go modules')
    record={'format':'purifier-flatbuffers-go-v1','resources':str(bundle),'sdk':str(sdk),'sdkSource':spec['sdkSource'],'compilerVersion':version,'reflectionSchema':str(reflection),'reflectionSchemaSha256':digest(reflection),'schemaHashes':hashes,'nativeSchemas':models,'generatedHashes':sources,'runtimeModule':runtime_packages[0],'runtimeSource':spec['runtimeSource'],'runtimeGoVersion':sdk_mod['Go'],'modulePath':spec['modulePath'],'commands':commands}
    (out/'flatbuffers-go.json').write_text(json.dumps(record,sort_keys=True,indent=2)+'\n')

if __name__=='__main__':generate(json.loads(Path(sys.argv[1]).read_text()),Path(sys.argv[2]))
