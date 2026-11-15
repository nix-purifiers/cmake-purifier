# SPDX-License-Identifier: MIT
"""Compile native Thrift C/GLib products against the selected SDK runtime."""
import hashlib,json,re,shutil,subprocess,sys
from pathlib import Path,PurePosixPath


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(spec,out):
    output=out.resolve()
    bundle=Path(spec['resources']);root=(bundle/'files').resolve(strict=True)
    catalog=json.loads((bundle/'catalog.json').read_text())
    if catalog['format']!='purifier-resources-v1' or catalog['schema']['format']!='thrift':
        raise ValueError('expected an explicitly selected Thrift schema bundle')
    names={}
    for name in catalog['files']:
        path=PurePosixPath(name)
        if path.suffix=='.thrift':
            if path.stem in names:
                raise ValueError('ambiguous native program output name: '+path.stem)
            names[path.stem]=name
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
        if result.returncode:raise ValueError("native compiler failed: "+result.stdout+result.stderr)
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
            if names.get(actual.stem)!=logical:raise ValueError('ambiguous native program source: '+logical)
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

    isolated=output/'programs';isolated.mkdir();owners={}
    for name in sorted(models):
        folder=isolated/name;folder.mkdir();compile(names[name],'c_glib',folder,False)
        for path in sorted(folder.iterdir()):
            if path.suffix not in ['.c','.h']:continue
            if path.name in owners:raise ValueError('native C/GLib generated outputs collide: '+path.name)
            owners[path.name]=name;shutil.copyfile(path,generated/path.name)
    if not list(generated.glob('*.c')):raise ValueError('native C/GLib generator produced no implementations')
    runtime=Path(spec['runtime']);source=Path(spec['sdkSource'])
    runtime_version=subprocess.check_output(['pkg-config','--modversion','thrift_c_glib'],text=True).strip()
    runtime_prefix=subprocess.check_output(['pkg-config','--variable=prefix','thrift_c_glib'],text=True).strip()
    if runtime_version!=native_version[1] or Path(runtime_prefix).resolve()!=runtime.resolve():raise ValueError('native C/GLib runtime differs from selected SDK')
    header_hashes={}
    for path in (source/'lib/c_glib/src/thrift').rglob('*.h'):
        logical=path.relative_to(source/'lib/c_glib/src');installed=runtime/'include'/logical
        if not installed.is_file() or path.read_bytes()!=installed.read_bytes():raise ValueError('installed C/GLib header differs from selected SDK: '+str(logical))
        header_hashes[str(logical)]=digest(installed)
    if not header_hashes:raise ValueError('selected SDK has no native C/GLib source headers')
    configuration=(runtime/'include/thrift/config.h').read_text()
    configured_version=re.search(r'^#define PACKAGE_VERSION "([^"]+)"',configuration,re.M)
    if configured_version is None or configured_version.group(1)!=native_version[1]:raise ValueError('native C/GLib runtime configuration version mismatch')
    model={'format':'purifier-thrift-c-glib-v1','resources':str(bundle),'sdk':str(sdk),'sdkSource':str(source),'runtime':str(runtime),'runtimeVersion':runtime_version,'runtimeHeaderHashes':header_hashes,'runtimeConfigSha256':digest(runtime/'include/thrift/config.h'),'runtimePkgConfigSha256':digest(runtime/'lib/pkgconfig/thrift_c_glib.pc'),'compilerVersion':version,'nativeInputs':native_inputs,'nativeModels':models,'programSources':{name:names[name] for name in models},'capturedHashes':hashes,'generatedOwners':owners,'generatedHashes':{str(p.relative_to(output)):digest(p) for p in generated.iterdir() if p.is_file()},'commands':commands}
    adapter=output/'purifier_thrift_c_glib_processor.h';shutil.copyfile(spec['processorAdapter'],adapter);model['adapterHeader']={'source':spec['processorAdapter'],'name':adapter.name,'sha256':digest(adapter)}
    (output/'thrift-c-glib.json').write_text(json.dumps(model,sort_keys=True,indent=2)+'\n')
    name,version=spec['name'],spec['version']
    dependencies=f'''include(CMakeFindDependencyMacro)
find_dependency(PkgConfig)
pkg_check_modules(THRIFT_C_GLIB REQUIRED IMPORTED_TARGET "thrift_c_glib = {native_version[1]}")
'''
    (output/(name+'Config.cmake')).write_text('include_guard(GLOBAL)\n'+dependencies+f'include("${{CMAKE_CURRENT_LIST_DIR}}/{name}Targets.cmake")\n')
    (output/(name+'.pc.in')).write_text(f'prefix=@CMAKE_INSTALL_PREFIX@\nName: {name}\nDescription: Native generated Thrift C GLib schemas\nVersion: {version}\nRequires: thrift_c_glib = {native_version[1]}\nLibs: -L${{prefix}}/lib -l{name}\nCflags: -I${{prefix}}/include\n')
    (output/'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project({name} VERSION {version} LANGUAGES C)
{dependencies}
include(CMakePackageConfigHelpers)
file(GLOB _sources "${{CMAKE_CURRENT_SOURCE_DIR}}/generated/*.c")
add_library(bindings SHARED ${{_sources}})
target_include_directories(bindings PUBLIC $<BUILD_INTERFACE:${{CMAKE_CURRENT_SOURCE_DIR}}/generated> $<INSTALL_INTERFACE:include>)
target_link_libraries(bindings PUBLIC PkgConfig::THRIFT_C_GLIB)
set_target_properties(bindings PROPERTIES OUTPUT_NAME {name})
install(TARGETS bindings EXPORT {name}Targets LIBRARY DESTINATION lib ARCHIVE DESTINATION lib RUNTIME DESTINATION bin)
install(EXPORT {name}Targets NAMESPACE {name}:: DESTINATION lib/cmake/{name})
install(DIRECTORY generated/ DESTINATION include FILES_MATCHING PATTERN "*.h")
install(FILES purifier_thrift_c_glib_processor.h DESTINATION include)
write_basic_package_version_file({name}ConfigVersion.cmake VERSION {version} COMPATIBILITY SameMajorVersion)
install(FILES {name}Config.cmake "${{CMAKE_CURRENT_BINARY_DIR}}/{name}ConfigVersion.cmake" DESTINATION lib/cmake/{name})
configure_file({name}.pc.in {name}.pc @ONLY)
install(FILES "${{CMAKE_CURRENT_BINARY_DIR}}/{name}.pc" DESTINATION lib/pkgconfig)
install(FILES thrift-c-glib.json DESTINATION share/{name})
install(DIRECTORY generated ast programs DESTINATION share/{name})
install(FILES "${{CMAKE_CURRENT_BINARY_DIR}}/compile_commands.json" DESTINATION share/{name})
''')

def finalize(output):
    files=list((output/'share').glob('*/thrift-c-glib.json'))
    if len(files)!=1:raise ValueError('ambiguous installed C/GLib product metadata')
    model=json.loads(files[0].read_text());model['libraryHashes']={str(p.relative_to(output)):digest(p) for p in (output/'lib').iterdir() if p.is_file() and not p.is_symlink()}
    if not model['libraryHashes']:raise ValueError('installed generated C/GLib library missing')
    files[0].write_text(json.dumps(model,sort_keys=True,indent=2)+'\n')

if __name__=='__main__':
    if sys.argv[1]=='--finalize':finalize(Path(sys.argv[2]))
    else:generate(json.loads(Path(sys.argv[1]).read_text()),Path(sys.argv[2]))
