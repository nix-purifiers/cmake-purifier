# SPDX-License-Identifier: MIT
import os,json,hashlib,subprocess,sys,shlex,shutil
from pathlib import Path
spec=json.loads(Path(sys.argv[1]).read_text());out=Path(sys.argv[2]);out.mkdir();results=[]
shutil.copyfile(spec['javaConsumer'],'GlibConsumer.java');subprocess.run(['javac','GlibConsumer.java'],check=True);classes=str(Path.cwd())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for index,case in enumerate(spec['versions']):
    root=Path('consumer-'+str(index)).resolve();root.mkdir();package=Path(case['generated']);model=json.loads((package/'share/thrift_c_proof/thrift-c-glib.json').read_text())
    for name,digest in model['generatedHashes'].items():
        assert sha(package/'share/thrift_c_proof'/name)==digest
        if name.endswith('.h'):assert (package/'include'/Path(name).name).read_bytes()==(package/'share/thrift_c_proof'/name).read_bytes()
    assert sha(package/'include'/model['adapterHeader']['name'])==model['adapterHeader']['sha256']==sha(Path(model['adapterHeader']['source']))
    for name,digest in model['libraryHashes'].items():assert sha(package/name)==digest
    library=next(package/name for name in model['libraryHashes'])
    def flags(prefix,module):
        env=dict(os.environ,PKG_CONFIG_PATH=prefix+'/lib/pkgconfig:'+os.environ.get('PKG_CONFIG_PATH',''))
        return shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs',module],env=env,text=True))
    c=root/'c-consumer';subprocess.run(['cc',spec['cConsumer'],'-o',str(c),*spec['dlLibs'],*flags(case['generated'],'thrift_c_proof')],check=True)
    c_result=subprocess.check_output([c],text=True).splitlines();assert c_result[1]=='43' and c_result[4]=='7 8' and c_result[5:]==['raw-native-invalid-method','inherited-rpc42'];assert Path(c_result[2]).resolve()==library.resolve();assert Path(c_result[3]).resolve().is_relative_to(Path(case['runtime']).resolve())
    cpp=root/'cpp-consumer';subprocess.run(['c++',spec['cppConsumer'],'-o',str(cpp),*spec['dlLibs'],*flags(case['cpp'],'thrift_proof')],check=True);cpp_result=subprocess.check_output([cpp],text=True).splitlines();assert c_result[0]==cpp_result[0] and cpp_result[1]=='43';wire=cpp_result[0].split(':',1)[1]
    ffi={}
    for kind in ['ctypes','cffi']:
        run=subprocess.run(['python',spec[kind+'Consumer'],str(library),wire],capture_output=True,text=True);assert run.returncode==0,(run.stdout,run.stderr);value=json.loads(run.stdout);assert value['answer']==42 and value['wire']==wire;ffi[kind]=value
    run=subprocess.run(['java','--enable-native-access=ALL-UNNAMED','-cp',classes,'GlibConsumer',str(library),wire],capture_output=True,text=True);assert run.returncode==0,(run.stdout,run.stderr);ffi['java']=json.loads(run.stdout);assert ffi['java']['answer']==42 and ffi['java']['wire']==wire
    project=root/'cmake';project.mkdir();(project/'CMakeLists.txt').write_text('cmake_minimum_required(VERSION 3.20)\nproject(consumer C)\nfind_package(thrift_c_proof 1.0.0 EXACT CONFIG REQUIRED)\nadd_executable(consumer '+json.dumps(spec['cConsumer'])+')\ntarget_link_libraries(consumer PRIVATE thrift_c_proof::bindings '+ ' '.join(spec['dlLibs'])+')\n')
    env=dict(os.environ,PKG_CONFIG_PATH=case['runtime']+'/lib/pkgconfig:'+os.environ.get('PKG_CONFIG_PATH',''));subprocess.run(['cmake','-S',str(project),'-B',str(project/'build'),'-G','Ninja','-DCMAKE_PREFIX_PATH='+case['generated']],env=env,check=True);subprocess.run(['cmake','--build',str(project/'build')],env=env,check=True);assert subprocess.check_output([project/'build/consumer'],text=True).splitlines()==c_result
    results.append({'case':case,'model':model,'c':c_result,'cpp':cpp_result,'ffi':ffi})
assert results[0]['c'][0]!=results[1]['c'][0]
controls=[]
for kind,expected in [('hash','schema does not match captured resource hash'),('missing','Could not find include file'),('outside','native compiler input escapes captured schema tree'),('basename','ambiguous native program output name'),('service','native C/GLib generated outputs collide'),('runtimePrefix','native C/GLib runtime differs from selected SDK'),('runtimeVersion','native C/GLib runtime differs from selected SDK'),('runtimeHeader','installed C/GLib header differs from selected SDK'),('runtimeConfig','native C/GLib runtime configuration version mismatch')]:
    root=Path('reject-'+kind).resolve();root.mkdir();bundle=root/'bundle';shutil.copytree(Path(results[0]['model']['resources']),bundle)
    for path in [bundle,*bundle.rglob('*')]:path.chmod(path.stat().st_mode | 0o200)
    catalog=json.loads((bundle/'catalog.json').read_text());main=bundle/'files/main.thrift';runtime=Path(results[0]['case']['runtime'])
    if kind=='hash':main.write_text(main.read_text()+'\n// changed\n')
    elif kind=='missing':
        main.write_text(main.read_text().replace('common/value.thrift','absent.thrift'));catalog['files']['main.thrift']['sha256']=sha(main)
    elif kind=='outside':
        external=root/'outside.thrift';external.write_text('struct Outside { 1: i32 value }\n');main.write_text('include '+json.dumps(str(external))+'\nstruct External { 1: outside.Outside value }\n');catalog['files']['main.thrift']['sha256']=sha(main)
    elif kind in ['basename','service']:
        extra=bundle/('files/duplicate/value.thrift' if kind=='basename' else 'files/duplicate.thrift');extra.parent.mkdir(parents=True,exist_ok=True);extra.write_text('struct Unused { 1: i32 value }\n' if kind=='basename' else 'service BaseService { i32 ping(1: i32 delta) }\n');catalog['files'][str(extra.relative_to(bundle/'files'))]={'sha256':sha(extra)}
        if kind=='service':main.write_text('include "duplicate.thrift"\n'+main.read_text());catalog['files']['main.thrift']['sha256']=sha(main)
    else:
        copied=root/'runtime';shutil.copytree(runtime,copied)
        for path in [copied,*copied.rglob('*')]:path.chmod(path.stat().st_mode | 0o200)
        pc=copied/'lib/pkgconfig/thrift_c_glib.pc';original_runtime=runtime;pc.write_text(pc.read_text().replace(str(runtime),str(copied)));runtime=copied
        if kind=='runtimePrefix':pc.write_text(pc.read_text().replace(str(copied),str(original_runtime)))
        elif kind=='runtimeVersion':pc.write_text(pc.read_text().replace('Version: '+results[0]['model']['runtimeVersion'],'Version: 99.0.0'))
        elif kind=='runtimeHeader':
            header=copied/'include/thrift/c_glib/thrift.h';header.write_text(header.read_text()+'\n/* changed */\n')
        else:
            header=copied/'include/thrift/config.h';header.write_text(header.read_text().replace('#define PACKAGE_VERSION "'+results[0]['model']['runtimeVersion']+'"','#define PACKAGE_VERSION "99.0.0"'))
    (bundle/'catalog.json').write_text(json.dumps(catalog));config=root/'spec.json';model=results[0]['model'];config.write_text(json.dumps({'resources':str(bundle),'sdk':model['sdk'],'sdkSource':model['sdkSource'],'runtime':str(runtime),'name':'reject_proof','version':'1.0.0','processorAdapter':model['adapterHeader']['source']}));env=dict(os.environ,PKG_CONFIG_PATH=str(runtime/'lib/pkgconfig')+':'+os.environ.get('PKG_CONFIG_PATH',''));run=subprocess.run(['python',spec['generator'],str(config),str(root/'output')],env=env,capture_output=True,text=True)
    assert run.returncode!=0 and expected in run.stdout+run.stderr,(kind,run.stdout,run.stderr);controls.append({'control':kind,'exitCode':run.returncode,'diagnostic':expected})
(out/'verification.json').write_text(json.dumps({'consumers':results,'controls':controls},sort_keys=True,indent=2)+'\n')
