# SPDX-License-Identifier: MIT
"""Package native Thrift C++ generation from a complete captured include tree."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(spec, output):
    output=output.resolve()
    bundle=Path(spec['resources']);root=(bundle/'files').resolve(strict=True)
    catalog=json.loads((bundle/'catalog.json').read_text())
    if catalog['format']!='purifier-resources-v1' or catalog['schema']['format']!='thrift':
        raise ValueError('expected an explicitly selected Thrift schema bundle')
    names={}
    for name in catalog['files']:
        path=PurePosixPath(name)
        if path.suffix=='.thrift':
            if path.stem in names:
                raise ValueError('ambiguous native C++ program output name: '+path.stem)
            names[path.stem]=name
    sdk=Path(spec['sdk']);compiler=str(sdk/'bin/thrift')
    version=subprocess.check_output([compiler,'--version'],text=True).strip()
    native_version=re.fullmatch(r'Thrift version (\d+\.\d+\.\d+)',version)
    if native_version is None:raise ValueError('cannot read native Thrift SDK version: '+version)
    output.mkdir(parents=True);generated=output/'generated';ast=output/'ast';generated.mkdir();ast.mkdir()
    commands=[];native_inputs={}
    for entry in catalog['schema']['entrypoints']:
        path=(root/entry).resolve(strict=True)
        if not path.is_relative_to(root):raise ValueError('entrypoint escapes captured schema tree')
        for target,folder in [('json',ast),('cpp:no_skeleton',generated)]:
            command=[compiler,'-v','-r','-I',str(root),'--gen',target,'-out',str(folder),str(path)]
            result=subprocess.run(command,cwd=root,check=True,text=True,capture_output=True)
            commands.append(command)
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
            if not evidence['Program'] or any(paths!=evidence['Program'] for paths in evidence.values()):
                raise ValueError('incomplete native compiler input evidence')
            native_inputs[f'{entry}:{target}']={phase:sorted(paths) for phase,paths in evidence.items()}
            (folder/(Path(entry).stem+'-compiler.log')).write_text(result.stdout+result.stderr)
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
    cpp=sorted(generated.glob('*.cpp'))
    if not cpp:raise ValueError('native C++ generator produced no implementation sources')
    model={'format':'purifier-thrift-cpp-v1','resources':str(bundle),'sdk':str(sdk),
           'compilerVersion':version,'nativeInputs':native_inputs,'nativeModels':models,'programSources':{name:names[name] for name in models},
           'capturedHashes':hashes,'generatedHashes':{str(p.relative_to(output)):digest(p) for p in sorted(generated.iterdir()) if p.is_file()},'commands':commands}
    (output/'thrift-products.json').write_text(json.dumps(model,sort_keys=True,indent=2)+'\n')
    name,version=spec['name'],spec['version'];sdk_version=native_version[1]
    (output/(name+'Config.cmake')).write_text('include_guard(GLOBAL)\ninclude(CMakeFindDependencyMacro)\n'+f'find_dependency(Thrift {sdk_version} EXACT CONFIG REQUIRED PATHS "{sdk}/lib/cmake/thrift" NO_DEFAULT_PATH)\n'+f'include("${{CMAKE_CURRENT_LIST_DIR}}/{name}Targets.cmake")\n')
    (output/(name+'.pc.in')).write_text(f'prefix=@CMAKE_INSTALL_PREFIX@\nName: {name}\nDescription: Generated Thrift C++ schemas\nVersion: {version}\nRequires: thrift = {sdk_version}\nLibs: -L${{prefix}}/lib -l{name}\nCflags: -I${{prefix}}/include @SDK_CXX_FLAGS@\n')
    cmake=f'''cmake_minimum_required(VERSION 3.20)
project({name} VERSION {version} LANGUAGES CXX)
find_package(Thrift {sdk_version} EXACT CONFIG REQUIRED PATHS "{sdk}/lib/cmake/thrift" NO_DEFAULT_PATH)
include(CMakePackageConfigHelpers)
file(GLOB _generated_sources "${{CMAKE_CURRENT_SOURCE_DIR}}/generated/*.cpp")
'''
    cmake+='''# Probe real generated implementations with the native compiler/SDK.
# CMake supplies the supported standard feature order and compiler flags.
set(_sdk_standard "")
foreach(_feature IN LISTS CMAKE_CXX_COMPILE_FEATURES)
  if(_feature MATCHES "^cxx_std_([0-9]+)$")
    set(_candidate "${CMAKE_MATCH_1}")
    set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)
    try_compile(_works "${CMAKE_CURRENT_BINARY_DIR}/probe-${_candidate}"
      SOURCES ${_generated_sources} LINK_LIBRARIES thrift::thrift
      CXX_STANDARD ${_candidate} CXX_STANDARD_REQUIRED YES CXX_EXTENSIONS NO
      OUTPUT_VARIABLE _probe_output)
    file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/probe-${_candidate}.txt" "${_probe_output}")
    if(_works)
      set(_sdk_standard "${_candidate}")
      break()
    endif()
  endif()
endforeach()
if(NOT _sdk_standard)
  message(FATAL_ERROR "No native compiler standard can build the generated Thrift SDK sources")
endif()
string(JOIN " " SDK_CXX_FLAGS ${CMAKE_CXX${_sdk_standard}_STANDARD_COMPILE_OPTION})
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/sdk-standard.txt" "${_sdk_standard}\\n${SDK_CXX_FLAGS}\\n")
add_library(bindings SHARED ${_generated_sources})
target_include_directories(bindings PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/generated> $<INSTALL_INTERFACE:include>)
target_link_libraries(bindings PUBLIC thrift::thrift)
target_compile_features(bindings PUBLIC cxx_std_${_sdk_standard})
'''
    cmake+=f'''set_target_properties(bindings PROPERTIES OUTPUT_NAME {name})
install(TARGETS bindings EXPORT {name}Targets LIBRARY DESTINATION lib ARCHIVE DESTINATION lib RUNTIME DESTINATION bin)
install(EXPORT {name}Targets NAMESPACE {name}:: DESTINATION lib/cmake/{name})
install(DIRECTORY generated/ DESTINATION include FILES_MATCHING PATTERN "*.h")
write_basic_package_version_file({name}ConfigVersion.cmake VERSION {version} COMPATIBILITY SameMajorVersion)
install(FILES {name}Config.cmake "${{CMAKE_CURRENT_BINARY_DIR}}/{name}ConfigVersion.cmake" DESTINATION lib/cmake/{name})
configure_file({name}.pc.in {name}.pc @ONLY)
install(FILES "${{CMAKE_CURRENT_BINARY_DIR}}/{name}.pc" DESTINATION lib/pkgconfig)
install(FILES thrift-products.json "${{CMAKE_CURRENT_BINARY_DIR}}/sdk-standard.txt" DESTINATION share/{name})
install(DIRECTORY generated ast DESTINATION share/{name})
'''
    (output/'CMakeLists.txt').write_text(cmake)


def finalize(output):
    models=list((output/'share').glob('*/thrift-products.json'))
    if len(models)!=1:raise ValueError('ambiguous generated schema model')
    model=json.loads(models[0].read_text());model['libraryHashes']={str(p.relative_to(output)):digest(p) for p in sorted((output/'lib').iterdir()) if p.is_file() and not p.is_symlink()}
    if not model['libraryHashes']:raise ValueError('no installed generated library')
    models[0].write_text(json.dumps(model,sort_keys=True,indent=2)+'\n')


if __name__=='__main__':
    if sys.argv[1]=='--finalize':finalize(Path(sys.argv[2]))
    else:generate(json.loads(Path(sys.argv[1]).read_text()),Path(sys.argv[2]))
