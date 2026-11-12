# SPDX-License-Identifier: MIT
"""Publish a native Maven SDK build without changing its JAR bytes."""
from pathlib import Path
import hashlib,json,re,shutil,subprocess,sys,xml.etree.ElementTree as ET,zipfile
sdk,source,native,out=map(Path,sys.argv[1:]);out.mkdir();proof=out/'proof';proof.mkdir()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
ns={'m':'http://maven.apache.org/POM/4.0.0'}
original=source/'java/pom.xml';pom=native/'pom.xml'
if (native/'sdk-original.pom').read_bytes()!=original.read_bytes():raise ValueError('runtime builder did not retain native SDK POM')
root=ET.parse(pom).getroot();coordinates={key:root.findtext('m:'+key,namespaces=ns) for key in ['groupId','artifactId','version']}
version=subprocess.check_output([str(sdk/'bin/flatc'),'--version'],text=True).strip()
match=re.fullmatch(r'flatc version (\d+\.\d+\.\d+)',version)
if match is None or coordinates['version']!=match[1]:raise ValueError('native Maven runtime does not match selected compiler')
for key,value in coordinates.items():
 if not value or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.+-]*',value):raise ValueError('invalid native Maven SDK coordinate: '+key)
name=coordinates['artifactId']+'-'+coordinates['version'];jar=native/(name+'.jar')
with zipfile.ZipFile(jar) as z:
 classes={n:hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if n.endswith('.class')}
 major=int.from_bytes(z.read('com/google/flatbuffers/Table.class')[6:8],'big')
 embedded='META-INF/maven/'+coordinates['groupId']+'/'+coordinates['artifactId']+'/pom.properties'
 props=z.read(embedded).decode();assert all(key+'='+value in props for key,value in coordinates.items())
 if not classes:raise ValueError('native runtime JAR has no classes')
repository=out/'repository'/coordinates['groupId'].replace('.','/')/coordinates['artifactId']/coordinates['version'];repository.mkdir(parents=True)
artifacts={}
for p in native.glob('*.jar'):
 if not p.name.startswith(name):raise ValueError('unexpected native Maven SDK artifact')
 shutil.copyfile(p,repository/p.name);artifacts[p.name]=sha(p)
shutil.copyfile(pom,repository/(name+'.pom'));shutil.copyfile(original,proof/'sdk-original.pom');shutil.copyfile(pom,proof/'configured.pom')
shutil.copyfile(jar,out/'runtime.jar')
record={'sdk':str(sdk),'sdkSource':str(source),'nativeBuild':str(native),'compilerVersion':version,'coordinates':coordinates,'classMajor':major,'classes':classes,'jarSha256':sha(jar),'nativeArtifacts':artifacts,'originalPomSha256':sha(original),'configuredPomSha256':sha(pom),'sourceHashes':{str(p.relative_to(source)):sha(p) for p in sorted((source/'java/src/main/java').rglob('*.java'))}}
(proof/'model.json').write_text(json.dumps(record,sort_keys=True,indent=2)+'\n')
