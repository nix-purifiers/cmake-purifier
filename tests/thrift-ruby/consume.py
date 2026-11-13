# SPDX-License-Identifier: MIT
import hashlib,json,os,shlex,shutil,subprocess,sys
from pathlib import Path
spec=json.loads(Path(sys.argv[1]).read_text());out=Path(sys.argv[2]);out.mkdir();results=[]
for index,case in enumerate(spec['versions']):
    model=json.loads((Path(case['proof'])/'thrift-ruby.json').read_text())
    for name,expected in model['capturedHashes'].items():
        assert hashlib.sha256((Path(model['resources'])/'files'/name).read_bytes()).hexdigest()==expected
    installed=Path(f'installed-{index}').resolve();installed.mkdir()
    env={**os.environ,'GEM_HOME':str(installed),'GEM_PATH':str(installed)}
    repository=Path(case['repository'])/'gems'
    archives=list(repository.glob('thrift-ruby-proof-*.gem'));assert len(archives)==1
    subprocess.run(['ruby','-S','gem','install','--local','--prerelease','--no-document','--install-dir',str(installed),str(archives[0])],cwd=repository,env=env,check=True)
    actual=json.loads(subprocess.check_output(['ruby',spec['rubyConsumer']],env=env,text=True))
    assert actual['files']==model['generatedHashes'], {'installed':actual['files'],'native':model['generatedHashes']}
    assert '.nix.' in actual['version'] and '.nix.' in actual['runtimeVersion']
    assert model['nativeModels']['value']['structs'][0]['fields'][0]['key']==index+1
    flags=subprocess.check_output(['pkg-config','--cflags','--libs',case['cpp']+'/lib/pkgconfig/thrift_proof.pc'],text=True)
    binary=Path(f'cpp-{index}')
    subprocess.run(['c++',spec['cppConsumer'],'-o',str(binary),*spec['dlLibs'],*shlex.split(flags)],check=True)
    cpp=subprocess.check_output(['./'+str(binary)],text=True).splitlines()
    assert cpp[0]=='42:'+actual['wire'] and cpp[1]=='43'
    assert Path(cpp[2]).resolve().parent==Path(case['cpp'])/'lib'
    assert Path(cpp[3]).resolve().parent==Path(model['sdk'])/'lib'
    results.append({'case':case,'actual':actual,'cpp':cpp,'model':model})
assert results[0]['actual']['wire']!=results[1]['actual']['wire']
assert results[0]['actual']['version']!=results[1]['actual']['version']
assert results[0]['actual']['runtimeVersion']==results[1]['actual']['runtimeVersion']
# Test real offline installation failure with the SDK archive removed.
missing=Path('missing-runtime').resolve();missing.mkdir()
for archive in (Path(spec['versions'][0]['repository'])/'gems').glob('thrift-ruby-proof-*.gem'):
    shutil.copyfile(archive,missing/archive.name)
env={**os.environ,'GEM_HOME':str(Path('missing-installed').resolve()),'GEM_PATH':str(Path('missing-installed').resolve())}
run=subprocess.run(['ruby','-S','gem','install','--local','--prerelease','--no-document',str(next(missing.glob('*.gem')))],cwd=missing,env=env,capture_output=True,text=True)
assert run.returncode and 'thrift' in run.stderr and 'Could not find a valid gem' in run.stderr
(out/'missing-runtime.stderr').write_text(run.stderr)
from importlib.util import spec_from_file_location,module_from_spec
loader=spec_from_file_location('ruby_generator',spec['generator']);generator=module_from_spec(loader);loader.loader.exec_module(generator)
model=results[0]['model'];controls=[]
def bundle(name):
    root=Path(name).resolve();shutil.copytree(model['resources'],root)
    for path in root.rglob('*'):
        if not path.is_symlink():path.chmod(0o755 if path.is_dir() else 0o644)
    return root

def admit(root,path,text):
    file=root/'files'/path;file.parent.mkdir(parents=True,exist_ok=True);file.write_text(text)
    catalog=json.loads((root/'catalog.json').read_text());catalog['files'][path]={'sha256':hashlib.sha256(file.read_bytes()).hexdigest()};(root/'catalog.json').write_text(json.dumps(catalog))

def attempt(name,root):
    work=Path(name).resolve();work.mkdir();proof=work/'proof';proof.mkdir();previous=Path.cwd()
    try:
        os.chdir(work)
        generator.generate({'resources':str(root),'sdk':model['sdk'],'sdkSource':spec['sdkSource'],
            'ruby':spec['ruby'],'runtimeProof':model['runtimeProof'],'name':'thrift-ruby-proof','version':'1.0.0',
            'bindingsTool':spec['bindingsTool'],'packageTool':spec['packageTool']},work/'schema.gem',proof)
    finally:os.chdir(previous)

def reject(name,root,text):
    try:attempt('attempt-'+name,root)
    except ValueError as error:message=str(error)
    except subprocess.CalledProcessError as error:
        # Ruby native parser diagnostics are retained in the build log.
        message=str(error)+str(error.stdout or '')+str(error.stderr or '')
    else:raise AssertionError('accepted negative control '+name)
    assert text in message,(name,message)
    controls.append(name)

changed=bundle('changed-source');path=changed/'files/common/value.thrift';path.write_text(path.read_text()+'// uncaptured change\n')
reject('changed-source',changed,'does not match captured resource hash')
missing_schema=bundle('missing-import');(missing_schema/'files/common/value.thrift').unlink()
reject('missing-import',missing_schema,'common/value.thrift')
external=bundle('outside-import');foreign=Path('foreign/value.thrift').resolve();foreign.parent.mkdir();foreign.write_text((external/'files/common/value.thrift').read_text())
admit(external,'main.thrift',(external/'files/main.thrift').read_text().replace('common/value.thrift',str(foreign)))
reject('outside-import',external,'native compiler input escapes')
collision=bundle('class-collision');admit(collision,'main.thrift',(collision/'files/main.thrift').read_text()+'\nstruct Value {1:i32 other}\n')
reject('class-collision',collision,'native generated class collision')
intrinsic=bundle('intrinsic-collision');admit(intrinsic,'main.thrift',(intrinsic/'files/main.thrift').read_text()+'\nstruct String {1:i32 other}\n')
reject('intrinsic-collision',intrinsic,'generated class collides with native Ruby/SDK class')
unused=bundle('unused-schema');admit(unused,'unused/value.thrift','struct Unused {1:i32 other}\n')
attempt('unused-schema-accepted',unused)
qualified=spec['qualified'];destination=Path('qualified-installed').resolve();destination.mkdir()
env={**os.environ,'GEM_HOME':str(destination),'GEM_PATH':str(destination)}
repository=Path(qualified['repository'])/'gems'
subprocess.run(['ruby','-S','gem','install','--local','--prerelease','--no-document','--install-dir',str(destination),str(next(repository.glob('thrift-ruby-proof-*.gem')))],cwd=repository,env=env,check=True)
qualified_actual=json.loads(subprocess.check_output(['ruby',spec['qualifiedConsumer']],env=env,text=True))
flags=subprocess.check_output(['pkg-config','--cflags','--libs',qualified['cpp']+'/lib/pkgconfig/thrift_proof.pc'],text=True)
subprocess.run(['c++',spec['qualifiedCpp'],'-o','qualified-cpp',*spec['dlLibs'],*shlex.split(flags)],check=True)
qualified_cpp=subprocess.check_output(['./qualified-cpp'],text=True).strip()
assert qualified_cpp==qualified_actual['wire']
(out/'qualified.json').write_text(json.dumps({'case':qualified,'actual':qualified_actual,'cppWire':qualified_cpp},indent=2)+'\n')
(out/'verification.json').write_text(json.dumps({'consumers':results,'missingRuntimeRejected':True,'controls':controls,'unusedDuplicateProgramAccepted':True},indent=2)+'\n')
