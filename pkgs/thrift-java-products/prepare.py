# SPDX-License-Identifier: MIT
"""Retain the complete native SDK layout and add its native wrapper companion."""
import hashlib,json,shutil,sys
from pathlib import Path
spec=json.loads(Path(sys.argv[1]).read_text());source=Path(spec['sdkSource']);wrapper=Path(spec['wrapper']);out=Path(sys.argv[2]);shutil.copytree(source,out,symlinks=True)
for path in [out,*out.rglob('*')]:
 if not path.is_symlink():path.chmod(path.stat().st_mode|0o200)
files={}
for logical in ['gradlew','gradlew.bat','gradle/wrapper/gradle-wrapper.jar','gradle/wrapper/gradle-wrapper.properties']:
 path=(wrapper/logical).resolve(strict=True)
 if not path.is_relative_to(wrapper.resolve(strict=True)):raise ValueError('native wrapper companion escapes selected tree')
 target=out/'lib/java'/logical
 if target.exists() and target.read_bytes()!=path.read_bytes():raise ValueError('wrapper companion changes an existing SDK file')
 target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target);files[logical]=hashlib.sha256(path.read_bytes()).hexdigest()
record={'sdkSource':str(source),'wrapper':str(wrapper),'wrapperHashes':files,'sdkJavaSourceHashes':{str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (source/'lib/java').rglob('*') if p.is_file()}}
(out/'purifier-java-sdk-source.json').write_text(json.dumps(record,sort_keys=True,indent=2)+'\n')
