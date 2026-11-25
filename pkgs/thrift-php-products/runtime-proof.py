# SPDX-License-Identifier: MIT
"""Verify the selected SDK's original PHP tree and native Composer root."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


spec=json.loads(Path(sys.argv[1]).read_text())
sdk=Path(spec['sdkSource']).resolve(strict=True)
source=Path(spec['source']).resolve(strict=True)
producer=Path(spec['producer']).resolve(strict=True)
installed=Path(spec['installedRoot']).resolve(strict=True)
if not installed.is_relative_to(producer):
    raise ValueError('native SDK Composer root is outside its original producer output')
if (source/'composer.json').read_bytes() != (sdk/'composer.json').read_bytes():
    raise ValueError('native SDK Composer source manifest changed')
manifest=json.loads((sdk/'composer.json').read_text())
autoload=manifest.get('autoload',{})
names=[]
for field in ['psr-4','psr-0']:
    for paths in autoload.get(field,{}).values():
        names.extend([paths] if isinstance(paths,str) else paths)
for field in ['classmap','files']:
    paths=autoload.get(field,[])
    names.extend([paths] if isinstance(paths,str) else paths)
roots=[]
for name in sorted(set(names)):
    relative=PurePosixPath(name or '.')
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('original SDK autoload path escapes its source')
    path=(sdk/relative).resolve(strict=True)
    if not path.is_relative_to(sdk):
        raise ValueError('original SDK autoload path aliases outside source')
    roots.append((relative,path))
files={}
for relative,root in roots:
 for path in sorted(root.rglob('*')) if root.is_dir() else [root]:
    if not path.is_file():
        continue
    name=path.relative_to(sdk).as_posix()
    if path.is_symlink() or not (source/name).resolve(strict=True).is_relative_to(source) or not (installed/name).resolve(strict=True).is_relative_to(installed):
        raise ValueError('SDK PHP source escapes its original input')
    value=sha(path)
    if sha(source/name)!=value or sha(installed/name)!=value:
        raise ValueError('SDK PHP source or installed method bytes changed: '+name)
    files[name]=value
if not files:
    raise ValueError('selected native SDK has no PHP runtime source')
code='require $argv[1]; echo json_encode(Composer\\InstalledVersions::getRootPackage(), JSON_THROW_ON_ERROR);'
root=json.loads(subprocess.check_output([spec['php'],'-r',code,str(installed/'vendor/autoload.php')],text=True))
if root['name']!=manifest['name'] or not root.get('pretty_version'):
    raise ValueError('native Composer SDK root metadata does not match original source')
locked=json.loads((installed/'composer.lock').read_text())
active=json.loads((installed/'vendor/composer/installed.json').read_text())
packages=active['packages'] if isinstance(active,dict) else active
expected={p['name'] for p in locked.get('packages',[])+locked.get('packages-dev',[])}
if {p['name'] for p in packages} != expected:
    raise ValueError('native SDK must retain its complete locked Composer dependency graph')
version=subprocess.check_output([str(Path(spec['sdk'])/'bin/thrift'),'--version'],text=True).strip()
root_record=Path(sys.argv[2]).with_name('native-root.json')
root_record.write_text(json.dumps(root)+'\n')
requirements=subprocess.run([spec['php'],spec['requirementsTool'],str(Path(spec['composer'])/'share/php/composer/vendor/autoload.php'),str(sdk/'composer.json'),str(installed/'vendor/composer/installed.json'),str(root_record)],text=True,capture_output=True)
if requirements.returncode:
    raise ValueError('original SDK dependency graph is incomplete: '+requirements.stdout+requirements.stderr)
Path(sys.argv[2]).write_text(json.dumps({'compilerVersion':version,'name':root['name'],'version':root['pretty_version'],'nativeRoot':root,'autoloadRoots':[str(installed/path) for path,_ in roots],'sourceFiles':files,'sourceManifestSha256':sha(sdk/'composer.json'),'dependencyCount':len(expected),'nativeRequirementChecks':json.loads(requirements.stdout)},sort_keys=True,indent=2)+'\n')
