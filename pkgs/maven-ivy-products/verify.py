# SPDX-License-Identifier: MIT
"""Join native Apache Ivy output and copied bytes to the source Maven view."""
import hashlib,json,sys
from pathlib import Path
from xml.etree import ElementTree as ET
source,out,proof,tool=map(Path,sys.argv[1:]);sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
artifacts=[]
for line in (proof/'native-conversion.log').read_text().splitlines():
 if line.startswith('artifact\t'):
  _,original,destination=line.split('\t');assert (source/original).read_bytes()==(out/destination).read_bytes();artifacts.append({'maven':original,'ivy':destination,'sha256':sha(out/destination)})
modules=[]
for path in sorted(out.rglob('ivy.xml')):
 root=ET.parse(path).getroot();info=root.find('info');identity={field:info.attrib[field] for field in ['organisation','module','revision']};pom=source/identity['organisation'].replace('.','/')/identity['module']/identity['revision']/(identity['module']+'-'+identity['revision']+'.pom');assert pom.is_file()
 modules.append({'descriptor':str(path.relative_to(out)),'sha256':sha(path),'sourcePom':str(pom.relative_to(source)),'sourcePomSha256':sha(pom),'nativeIdentity':identity,'nativeConfigurations':[dict(c.attrib) for c in root.findall('configurations/conf')],'nativePublications':[dict(a.attrib) for a in root.findall('publications/artifact')],'nativeDependencies':[dict(d.attrib) for d in root.findall('dependencies/dependency')]})
assert modules and artifacts
(proof/'conversion.json').write_text(json.dumps({'format':'native-maven-ivy-v1','nativeIvyJar':str(tool),'nativeIvyJarSha256':sha(tool),'mavenRepository':str(source),'modules':modules,'copiedArtifacts':artifacts,'policy':'Native Apache Ivy parses Maven parents, scopes and classifiers using only the selected local repository; HTTP and HTTPS are forbidden. Native descriptor publication dates use the fixed 1980 epoch. Artifact bytes and published coordinates stay unchanged.'},sort_keys=True,indent=2)+'\n')
