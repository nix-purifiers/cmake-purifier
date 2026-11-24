# SPDX-License-Identifier: MIT
"""Observe original source bytes, native findlib metadata and interface CRCs."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

spec=json.loads(Path(sys.argv[1]).read_text())
out,proof=map(Path,sys.argv[2:4])
inspector=sys.argv[4]
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
run=lambda args:subprocess.check_output(args,text=True).strip()
compiler=Path(spec['ocaml'])/'bin'
findlib=Path(spec['findlib'])/'bin/ocamlfind'
stdlib=Path(run([str(compiler/'ocamlc'),'-where'])).resolve(strict=True)
actual=run([str(compiler/'ocamlc'),'-version'])
if actual!=spec['ocamlVersion']:raise ValueError('native OCaml compiler differs from original selected SDK')
original=Path(spec['sdkSource'])/'lib/ocaml'
runtime=Path(spec['runtime'])
def inventory(root):
 result={}
 for path in root.rglob('*'):
  if path.is_symlink():raise ValueError('original OCaml SDK source must use regular files')
  if path.is_file():result[path.relative_to(root).as_posix()]=sha(path)
 return result
sdk_sources=inventory(original)
if not sdk_sources or inventory(runtime/'original-source')!=sdk_sources:raise ValueError('original OCaml SDK source changed')
model=json.loads((Path(spec['sourceProof'])/'thrift-ocaml.json').read_text())
source=Path(spec['source'])
raw={row['path']:Path(row['file']) for row in model['ownership']}
if (proof/'original_oasis').read_bytes()!=Path(spec['oasis']).read_bytes():raise ValueError('native caller Oasis metadata changed')
source_hashes={}
for name,digest in model['generatedHashes'].items():
 if sha(raw[name])!=digest or sha(source/name)!=digest or sha(Path('src')/name)!=digest:
  raise ValueError('native generated OCaml source changed')
 source_hashes[name]=digest
metas=list((out/'lib/ocaml'/actual/'site-lib').rglob('META'))
if len(metas)!=1:raise ValueError('Oasis must install exactly one native findlib package')
name=metas[0].parent.name
os.environ['OCAMLPATH']=str(out/'lib/ocaml'/actual/'site-lib')+':'+str(runtime/'lib/ocaml'/actual/'site-lib')
records=[]
for mode in ['byte','native']:
 text=run([str(findlib),'query','-recursive','-predicates',mode+',mt,mt_posix','-format','%p\t%d\t%v\t%+A',name])
 (proof/(mode+'-findlib.tsv')).write_text(text+'\n')
 rows=[]
 for line in text.splitlines():
  package,directory,version,archives=line.split('\t')
  directory=Path(directory).resolve(strict=True)
  owners=[root for root in [out.resolve(),runtime.resolve(),stdlib] if directory.is_relative_to(root)]
  if len(owners)!=1:raise ValueError('native findlib package has a foreign or ambiguous owner')
  rows.append({'name':package,'directory':str(directory),'version':version,'archives':archives.split()})
 if not any(row['name']=='thrift' and row['version']==model['compilerVersion'].removeprefix('Thrift version ') for row in rows):raise ValueError('native Thrift runtime metadata differs from compiler')
 records.append({'mode':mode,'packages':rows})

def info(path):return run([str(compiler/'ocamlobjinfo'),str(path)])
def cmi(path):
 text=info(path);unit=re.search(r'^Unit name: (.+)$',text,re.M).group(1)
 matches=re.findall(r'^\s*([a-f0-9]{32})\s+'+re.escape(unit)+r'$',text,re.M)
 if len(set(matches))!=1:raise ValueError('native interface CRC is missing or ambiguous')
 return unit,matches[0]
package_dir=metas[0].parent
sdk_dir=runtime/'lib/ocaml'/actual/'site-lib/thrift'
sdk_units={unit:(crc,path) for path in sdk_dir.glob('*.cmi') for unit,crc in [cmi(path)]}
units={unit:(crc,path) for path in package_dir.glob('*.cmi') for unit,crc in [cmi(path)]}
sdk_typed_sources={}
for path in sdk_dir.glob('*.cmt'):
 filename,digest=run([inspector,str(path)]).split('\t')
 original_path=original/filename
 if not original_path.is_file() or hashlib.md5(original_path.read_bytes()).hexdigest()!=digest:raise ValueError('native SDK typed source digest differs from original bytes')
 sdk_typed_sources[filename]={'nativeDigest':digest,'typedFile':str(path),'typedSha256':sha(path)}
expected_sdk={path.stem for path in (original/'src').glob('*.ml')}
if set(sdk_units)!=expected_sdk or {Path(path).stem for path in sdk_typed_sources}!=expected_sdk:raise ValueError('native SDK compiled module graph differs from original source')
for mode in ['byte','native']:
 archives=run([str(findlib),'query','-predicates',mode+',mt,mt_posix','-format','%+A','thrift']).split()
 if len(archives)!=1:raise ValueError('original native Thrift SDK archive is ambiguous')
 text=info(Path(archives[0]));(proof/(mode+'-sdk-archive.txt')).write_text(text+'\n')
 if set(re.findall(r'^(?:Unit name|Name): (.+)$',text,re.M))!=expected_sdk:raise ValueError('original native Thrift SDK archive graph is incomplete')

expected={Path(name).stem[0].upper()+Path(name).stem[1:] for name in source_hashes if name.endswith('.ml')}
typed_sources = {}
for path in sorted(package_dir.glob('*.cmt*')):
 text=run([inspector,str(path)])
 filename,digest=text.split('\t')
 relative=Path(filename).name
 if relative not in source_hashes:raise ValueError('native typed module has a foreign source file')
 if hashlib.md5((source/relative).read_bytes()).hexdigest()!=digest:raise ValueError('native typed source digest differs from original generated bytes')
 typed_sources[relative]={'typedFile':str(path),'typedSha256':sha(path),'nativeDigest':digest}
if set(typed_sources)!=set(source_hashes):raise ValueError('native typed graph omitted a generated source or interface')
if set(units)!=expected:raise ValueError('native Oasis package omitted or added generated modules')
if set(units)&set(sdk_units):raise ValueError('generated OCaml module shadows original Thrift SDK')
for unit in units:
 if list(stdlib.rglob(unit[0].lower()+unit[1:]+'.cmi')):raise ValueError('generated OCaml module shadows original standard library')
imports=[]
for path in sorted(package_dir.glob('*.cmi')):
 text=info(path)
 for crc,unit in re.findall(r'^\s*([a-f0-9]{32})\s+(\S+)\s*$',text,re.M):
  selected=units.get(unit) or sdk_units.get(unit)
  if selected is None:
   filename=unit[0].lower()+unit[1:]+'.cmi'
   candidates=list(stdlib.rglob(filename))
   valid=[p for p in candidates if cmi(p)==(unit,crc)]
   if not valid:raise ValueError('native imported interface lacks an original selected owner: '+unit)
   selected=(crc,valid[0])
  if selected[0]!=crc:raise ValueError('native imported interface CRC differs from its original producer')
  imports.append({'unit':unit,'crc':crc,'path':str(selected[1]),'sha256':sha(selected[1])})
for record in records:
 app=next(row for row in record['packages'] if row['name']==name)
 archives=[Path(path) for path in app['archives']]
 if len(archives)!=1:raise ValueError('native findlib must select exactly one schema archive')
 text=info(archives[0]);(proof/(record['mode']+'-archive.txt')).write_text(text+'\n')
 archived=set(re.findall(r'^(?:Unit name|Name): (.+)$',text,re.M))
 if archived!=expected:raise ValueError('native archive contents differ from the complete generated module graph')
(proof/'native-ocaml.json').write_text(json.dumps({'kind':'native-thrift-ocaml-package','package':name,'compilerVersion':model['compilerVersion'],'ocamlVersion':actual,'originalSDK':str(runtime),'originalSDKFiles':sdk_sources,'sdkTypedSources':sdk_typed_sources,'sourceHashes':source_hashes,'typedSources':typed_sources,'nativeFindlib':records,'units':{key:{'crc':crc,'path':str(path),'sha256':sha(path)} for key,(crc,path) in units.items()},'imports':imports},indent=2)+'\n')
