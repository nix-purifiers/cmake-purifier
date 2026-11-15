# SPDX-License-Identifier: MIT
"""Publish complete native documentation per captured Thrift entrypoint."""
import hashlib,json,re,subprocess,sys
from pathlib import Path,PurePosixPath

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def generate(spec,out):
    bundle=Path(spec['resources']);root=(bundle/'files').resolve(strict=True)
    catalog=json.loads((bundle/'catalog.json').read_text())
    if catalog['format']!='purifier-resources-v1' or catalog['schema']['format']!='thrift':raise ValueError('expected captured Thrift resources')
    hashes={};programs={}
    for name,record in catalog['files'].items():
        logical=PurePosixPath(name);path=(root/name).resolve(strict=True)
        if logical.is_absolute() or '..' in logical.parts or not path.is_relative_to(root):raise ValueError('resource escapes captured tree')
        hashes[name]=sha(path)
        if hashes[name]!=record['sha256']:raise ValueError('captured resource hash mismatch: '+name)
        if logical.suffix=='.thrift':
            if logical.stem in programs:raise ValueError('ambiguous native documentation program: '+logical.stem)
            programs[logical.stem]=name
    formats=spec['formats']
    if not formats or len(set(formats))!=len(formats) or not set(formats)<={'html','markdown','gv','mmd'}:raise ValueError('unsupported native documentation formats')
    compiler=str(Path(spec['sdk'])/'bin/thrift');version=subprocess.check_output([compiler,'--version'],text=True).strip()
    out.mkdir(parents=True);records=[]
    for entry in catalog['schema']['entrypoints']:
        path=(root/entry).resolve(strict=True)
        if not path.is_relative_to(root) or entry not in hashes:raise ValueError('uncaptured documentation entrypoint')
        for target in ['json',*formats]:
            folder=out/target/path.stem;folder.mkdir(parents=True)
            command=[compiler,'-v','-r','-I',str(root),'--gen',target,'-out',str(folder),str(path)]
            result=subprocess.run(command,cwd=root,capture_output=True,text=True)
            (out/(path.stem+'-'+target+'-compiler.log')).write_text(result.stdout+result.stderr)
            if result.returncode:raise ValueError('native documentation compiler failed: '+result.stdout+result.stderr)
            phases={key:set() for key in ['Scanning','Parsing','Program']}
            for line in result.stdout.splitlines():
                match=re.fullmatch(r'(Scanning|Parsing) (.+) for (?:includes|types)',line)
                if match:phase,source=match.groups()
                elif line.startswith('Program: '):phase,source='Program',line[len('Program: '):]
                else:continue
                source=Path(source).resolve(strict=True)
                if not source.is_relative_to(root):raise ValueError('native documentation input escapes captured tree')
                logical=source.relative_to(root).as_posix()
                if logical not in hashes or programs.get(source.stem)!=logical:raise ValueError('native documentation input not captured')
                phases[phase].add(logical)
            if not phases['Program'] or any(v!=phases['Program'] for v in phases.values()):raise ValueError('incomplete native documentation input evidence')
            files={str(p.relative_to(folder)):sha(p) for p in folder.rglob('*') if p.is_file()}
            if not files:raise ValueError('native documentation generator produced no files')
            records.append({'entrypoint':entry,'target':target,'command':command,'nativeInputs':{k:sorted(v) for k,v in phases.items()},'files':files})
    # Native JSON models independently establish include closure for each root.
    for entry in catalog['schema']['entrypoints']:
        folder=out/'json'/Path(entry).stem;models={p.stem:json.loads(p.read_text()) for p in folder.glob('*.json')}
        if not models:raise ValueError('native documentation model missing')
        for name,model in models.items():
            if name not in programs or any(imported not in models for imported in model['includes']):raise ValueError('native documentation model closure incomplete')
        expected={programs[name] for name in models}
        for record in records:
            if record['entrypoint']==entry and set(record['nativeInputs']['Program'])!=expected:raise ValueError('native documentation/model input graph differs')
    receipt={'format':'purifier-thrift-documentation-v1','compilerVersion':version,'sdk':spec['sdk'],'resources':str(bundle),'capturedHashes':hashes,'products':records}
    (out/'thrift-documentation.json').write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')

if __name__=='__main__':generate(json.loads(Path(sys.argv[1]).read_text()),Path(sys.argv[2]))
