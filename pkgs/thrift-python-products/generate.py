# SPDX-License-Identifier: MIT
"""Package native Thrift Python generation with its own SDK runtime wheel."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import zipfile
from packaging.utils import canonicalize_name
from packaging.version import Version


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(spec, destination, proof):
    canonicalize_name(spec['name'], validate=True)
    Version(spec['version'])
    output=proof.resolve()
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
        compile(names[name],'py',folder,False)
        for path in sorted(folder.rglob('*')):
            if not path.is_file() or path.name.endswith('-compiler.log'):continue
            target=generated/path.relative_to(folder)
            if target.exists():
                if target.read_bytes()!=path.read_bytes():raise ValueError('native generated Python outputs collide: '+str(path.relative_to(folder)))
            else:
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    runtime=json.loads(Path(spec['runtimeProof']).read_text())
    if runtime['compilerVersion']!=version or runtime['version']!=native_version[1]:
        raise ValueError('runtime wheel does not match native Thrift compiler')
    if (generated/'thrift').exists():
        raise ValueError('generated schema package collides with native Thrift runtime')
    work=Path('python-source').resolve();work.mkdir()
    shutil.copytree(generated,work/'generated')
    metadata={'name':spec['name'],'version':spec['version'],'dependencies':['thrift == '+runtime['version']]}
    text='[build-system]\nrequires = ["setuptools", "wheel"]\nbuild-backend = "setuptools.build_meta"\n[project]\n'
    for key,value in metadata.items():text+=key+' = '+json.dumps(value)+'\n'
    text+='[tool.setuptools.packages.find]\nwhere = ["generated"]\nnamespaces = false\n'
    (work/'pyproject.toml').write_text(text)
    subprocess.run([sys.executable,'-m','build','--no-isolation','--wheel','--outdir',str(destination.resolve()),str(work)],check=True)
    wheels=list(destination.glob('*.whl'))
    if len(wheels)!=1:raise ValueError('native backend did not produce exactly one generated schema wheel')
    owned={}
    with zipfile.ZipFile(wheels[0]) as wheel:
        for name in wheel.namelist():
            if name.endswith('.py'):
                source=generated/name
                if wheel.read(name)!=source.read_bytes():raise ValueError('wheel changed native generated Python source: '+name)
                owned[name]=digest(source)
    if not owned:raise ValueError('native wheel contains no generated schema modules')
    model={'format':'purifier-thrift-python-v1','resources':str(bundle),'sdk':str(sdk),
           'compilerVersion':version,'runtimeProof':spec['runtimeProof'],'nativeInputs':native_inputs,'nativeModels':models,
           'programSources':{name:names[name] for name in models},'capturedHashes':hashes,
           'generatedHashes':owned,'commands':commands,'runtime':runtime,
           'wheel':wheels[0].name,'wheelSha256':digest(wheels[0])}
    (proof/'thrift-python.json').write_text(json.dumps(model,sort_keys=True,indent=2)+'\n')
    shutil.copy(work/'pyproject.toml',proof/'pyproject.toml')


if __name__=='__main__':
    generate(json.loads(Path(sys.argv[1]).read_text()),Path(sys.argv[2]),Path(sys.argv[3]))
