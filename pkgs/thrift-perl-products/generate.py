# SPDX-License-Identifier: MIT
"""Preserve native Thrift Perl generation and reject per-program output collisions."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(spec, destination, proof):
    output=proof.resolve()
    bundle=Path(spec['resources']);root=(bundle/'files').resolve(strict=True)
    catalog=json.loads((bundle/'catalog.json').read_text())
    if catalog['format']!='purifier-resources-v1' or catalog['schema']['format']!='thrift':
        raise ValueError('expected an explicitly selected Thrift schema bundle')
    names={}
    for name in catalog['files']:
        path=PurePosixPath(name)
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
        result=subprocess.run(command,cwd=root,text=True,capture_output=True);commands.append(command)
        (folder/(Path(entry).stem+'-compiler.log')).write_text(result.stdout+result.stderr)
        if result.returncode:
            raise ValueError('native Thrift compilation failed: '+result.stdout+result.stderr)
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

    runtime=json.loads(Path(spec['runtimeProof']).read_text())
    if runtime['compilerVersion'] != version:
        raise ValueError('native Perl runtime differs from selected Thrift compiler')
    if spec['name'] == runtime['nativeMetadata']['name']:
        raise ValueError('generated package must not impersonate the native SDK distribution')
    # Generate every native program separately. This exposes output collisions
    # before the recursive generator could silently overwrite a shared namespace.
    isolated=output/'programs';isolated.mkdir()
    ownership=[]
    for name in sorted(models):
        folder=isolated/name;folder.mkdir()
        compile(names[name],'perl',folder,False)
        for path in sorted(folder.rglob('*')):
            if not path.is_file() or path.name.endswith('-compiler.log'):continue
            if path.suffix != ".pm" or path.is_symlink():raise ValueError("unexpected native Perl output")
            relative=path.relative_to(folder).as_posix()
            if relative in runtime['modules']:
                raise ValueError('native generated Perl module shadows selected runtime: '+relative)
            ownership.append({"program":name,"file":str(path.resolve())})
            target=generated/path.relative_to(folder)
            if target.exists():
                raise ValueError('native generated Perl output collision: '+str(path.relative_to(folder)))
            else:
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    destination.mkdir(parents=True)
    shutil.copytree(generated,destination/'lib')
    metadata={'name':spec['name'],'version':spec['version'],
              'runtimeVersion':runtime['nativeVersion']}
    (destination/'package.json').write_text(json.dumps(metadata,sort_keys=True)+'\n')
    shutil.copyfile(spec['makefileTool'],destination/'Makefile.PL')
    expected={str(p.relative_to(generated)):digest(p) for p in generated.rglob('*.pm')}
    record={'format':'purifier-thrift-perl-producer-v1','resources':str(bundle),'sdk':str(sdk),
        'compilerVersion':version,'runtimeProof':spec['runtimeProof'],'nativeInputs':native_inputs,
        'nativeModels':models,'programSources':{name:names[name] for name in models},
        'capturedHashes':hashes,'generatedHashes':expected,'commands':commands,
        'runtime':runtime,'package':metadata,'ownership':ownership}
    (output/'thrift-perl.json').write_text(json.dumps(record,sort_keys=True,indent=2)+'\n')


if __name__=='__main__':
    generate(json.loads(Path(sys.argv[1]).read_text()),Path(sys.argv[2]),Path(sys.argv[3]))
