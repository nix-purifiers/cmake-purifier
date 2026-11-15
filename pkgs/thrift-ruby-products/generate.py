# SPDX-License-Identifier: MIT
"""Package native Thrift Ruby generation with the matching native SDK gem."""
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

    # Generate every native program separately. This exposes output collisions
    # before the recursive generator could silently overwrite a shared namespace.
    isolated=output/'programs';isolated.mkdir()
    ownership=[]
    for name in sorted(models):
        folder=isolated/name;folder.mkdir()
        compile(names[name],'rb:namespaced',folder,False)
        for path in sorted(folder.rglob('*')):
            if not path.is_file() or path.name.endswith('-compiler.log'):continue
            if path.suffix != ".rb" or path.is_symlink():raise ValueError("unexpected native Ruby output")
            ownership.append({"program":name,"file":str(path.resolve())})
            target=generated/path.relative_to(folder)
            if target.exists():
                raise ValueError('native generated Ruby output collision: '+str(path.relative_to(folder)))
            else:
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    runtime=json.loads(Path(spec['runtimeProof']).read_text())
    if runtime['compilerVersion']!=version or runtime['version']!=native_version[1]:
        raise ValueError('runtime gem does not match native Thrift compiler')
    work=Path('ruby-source').resolve();work.mkdir();shutil.copytree(generated,work/'lib')
    ownership_path=output/'native-program-files.json';ownership_path.write_text(json.dumps(ownership))
    ruby=str(Path(spec['ruby'])/'bin/ruby')
    binding_run=subprocess.run([ruby,'-I',str(Path(spec['sdkSource'])/'lib/rb/lib'),'-r','thrift',
        spec['bindingsTool'],str(ownership_path),str(output/'native-bindings.json')],capture_output=True,text=True)
    (output/'ruby-bindings.stdout').write_text(binding_run.stdout)
    (output/'ruby-bindings.stderr').write_text(binding_run.stderr)
    if binding_run.returncode:raise ValueError('native Ruby binding validation failed: '+binding_run.stderr)
    metadata=output/'package.json';metadata.write_text(json.dumps({'name':spec['name'],'version':spec['version'],
        'runtime':{'name':runtime['name'],'version':runtime['version']}}))
    subprocess.run([ruby,spec['packageTool'],str(metadata),str(work),str(destination.resolve()),str(output/'package-proof.json')],check=True)
    gem_proof=json.loads((output/'package-proof.json').read_text())
    expected={str(p.relative_to(generated)):digest(p) for p in generated.rglob('*.rb')}
    if gem_proof['generatedHashes']!=expected:raise ValueError('native gem changed generated Ruby source bytes')
    record={'format':'purifier-thrift-ruby-v1','resources':str(bundle),'sdk':str(sdk),
        'compilerVersion':version,'runtimeProof':spec['runtimeProof'],'nativeInputs':native_inputs,
        'nativeModels':models,'programSources':{name:names[name] for name in models},
        'capturedHashes':hashes,'generatedHashes':expected,'commands':commands,
        'bindings':json.loads((output/'native-bindings.json').read_text()),'runtime':runtime,'gem':gem_proof}
    (output/'thrift-ruby.json').write_text(json.dumps(record,sort_keys=True,indent=2)+'\n')


if __name__=='__main__':
    generate(json.loads(Path(sys.argv[1]).read_text()),Path(sys.argv[2]),Path(sys.argv[3]))
