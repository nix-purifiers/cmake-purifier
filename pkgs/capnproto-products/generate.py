# SPDX-License-Identifier: MIT
"""Generate an owned C++ package using the native Cap'n Proto schema graph."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cmake_quote(value):
    level = '='
    while ']' + level + ']' in value:
        level += '='
    return '[' + level + '[' + value + ']' + level + ']'


def generate(spec, output):
    bundle = Path(spec['resources'])
    catalog = json.loads((bundle / 'catalog.json').read_text())
    if catalog['format'] != 'purifier-resources-v1' or catalog['schema']['format'] != 'capnproto':
        raise ValueError('expected an explicitly selected CapnProto schema bundle')
    root = (bundle / 'files').resolve(strict=True)
    sdk = Path(spec['sdk'])
    capnp = str(sdk / 'bin/capnp')
    command = [capnp, 'compile', '--no-standard-import', '--src-prefix=' + str(root),
               '-I' + str(root), '-I' + str(sdk / 'include')]
    request_command = command + ['-o-'] + [str(root / p) for p in catalog['schema']['entrypoints']]
    request = subprocess.check_output(request_command)
    native = json.loads(subprocess.check_output([spec['inspector']], input=request))
    owned, sdk_sources = {}, {}
    for node in native['files']:
        name = node['name']
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or str(path) != name:
            raise ValueError('native schema path is outside the projected include tree: ' + name)
        source = root / name
        runtime = sdk / 'include' / name
        if source.is_file() and (name not in catalog['files'] or digest(source) != catalog['files'][name]['sha256']):
            raise ValueError('native schema does not match captured resources: ' + name)
        if runtime.is_file():
            if source.exists() and digest(source) != digest(runtime):
                raise ValueError('captured schema shadows a different SDK schema: ' + name)
            sdk_sources[name] = digest(runtime)
        elif source.is_file():
            if not source.resolve(strict=True).is_relative_to(root):
                raise ValueError('schema escapes resource tree: ' + name)
            if name not in catalog['files'] or digest(source) != catalog['files'][name]['sha256']:
                raise ValueError('native schema does not match captured resources: ' + name)
            owned[name] = digest(source)
        else:
            raise ValueError('native schema is absent from captured resources and SDK: ' + name)
    if not owned:
        raise ValueError('no owned CapnProto schemas')
    output.mkdir(parents=True)
    generated = output / 'generated'
    generated.mkdir()
    generation = command + ['-o' + str(sdk / 'bin/capnpc-c++') + ':' + str(generated)] + [str(root / p) for p in sorted(owned)]
    subprocess.run(generation, check=True)
    source_files = []
    for name in sorted(owned):
        for suffix in ['.h', '.c++']:
            if not (generated / (name + suffix)).is_file():
                raise ValueError('native C++ generator omitted ' + name + suffix)
        source_files.append('generated/' + name + '.c++')
    model = {'format':'purifier-capnproto-cpp-v1', 'resources':str(bundle), 'sdk':str(sdk),
             'nativeRequest':native, 'schemaHashes':owned, 'sdkSchemaHashes':sdk_sources,
             'generatedHashes':{str(p.relative_to(output)):digest(p) for p in sorted(generated.rglob('*')) if p.is_file()},
             'commands':[request_command,[spec['inspector']],generation]}
    (output / 'capnproto-products.json').write_text(json.dumps(model,sort_keys=True,indent=2)+'\n')
    (output / 'request.bin').write_bytes(request)
    name, version = spec['name'], spec['version']
    config = ('include_guard(GLOBAL)\ninclude(CMakeFindDependencyMacro)\n'
              f'find_dependency(CapnProto {native["version"]} EXACT CONFIG REQUIRED PATHS "{sdk}/lib/cmake/CapnProto" NO_DEFAULT_PATH)\n'
              f'include("${{CMAKE_CURRENT_LIST_DIR}}/{name}Targets.cmake")\n')
    (output / (name + 'Config.cmake')).write_text(config)
    (output / (name + '.pc.in')).write_text(
        f'prefix=@CMAKE_INSTALL_PREFIX@\nName: {name}\nDescription: Generated CapnProto C++ schemas\n'
        f'Version: {version}\nRequires: capnp\nLibs: -L${{prefix}}/lib -l{name}\nCflags: -I${{prefix}}/include @SDK_CXX_FLAGS@\n')
    cmake = f'''cmake_minimum_required(VERSION 3.20)
project({name} VERSION {version} LANGUAGES CXX)
find_package(CapnProto {native['version']} EXACT CONFIG REQUIRED PATHS "{sdk}/lib/cmake/CapnProto" NO_DEFAULT_PATH)
include(CMakePackageConfigHelpers)
add_library(bindings SHARED {' '.join(cmake_quote(p) for p in source_files)})
set_target_properties(bindings PROPERTIES OUTPUT_NAME {name})
target_include_directories(bindings PUBLIC $<BUILD_INTERFACE:${{CMAKE_CURRENT_SOURCE_DIR}}/generated> $<INSTALL_INTERFACE:include>)
target_link_libraries(bindings PUBLIC CapnProto::capnp)
install(TARGETS bindings EXPORT {name}Targets LIBRARY DESTINATION lib ARCHIVE DESTINATION lib RUNTIME DESTINATION bin)
install(EXPORT {name}Targets NAMESPACE {name}:: DESTINATION lib/cmake/{name})
install(DIRECTORY generated/ DESTINATION include FILES_MATCHING PATTERN "*.h")
write_basic_package_version_file({name}ConfigVersion.cmake VERSION {version} COMPATIBILITY SameMajorVersion)
install(FILES {name}Config.cmake "${{CMAKE_CURRENT_BINARY_DIR}}/{name}ConfigVersion.cmake" DESTINATION lib/cmake/{name})
configure_file({name}.pc.in {name}.pc @ONLY)
install(FILES "${{CMAKE_CURRENT_BINARY_DIR}}/{name}.pc" DESTINATION lib/pkgconfig)
install(FILES capnproto-products.json request.bin DESTINATION share/{name})
install(DIRECTORY generated/ DESTINATION share/{name}/generated)
'''
    sdk_features = r"""
get_target_property(_sdk_features CapnProto::kj INTERFACE_COMPILE_FEATURES)
set(_sdk_standard 0)
foreach(_feature IN LISTS _sdk_features)
  if(_feature MATCHES "^cxx_std_([0-9]+)$")
    if(CMAKE_MATCH_1 GREATER _sdk_standard)
      set(_sdk_standard "${CMAKE_MATCH_1}")
    endif()
  endif()
endforeach()
set(SDK_CXX_FLAGS "")
if(_sdk_standard GREATER 0)
  string(JOIN " " SDK_CXX_FLAGS ${CMAKE_CXX${_sdk_standard}_STANDARD_COMPILE_OPTION})
endif()
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/sdk-compile-features.txt" "${_sdk_features}\n${SDK_CXX_FLAGS}\n")
"""
    cmake = cmake.replace('configure_file(', sdk_features + '\nconfigure_file(', 1)
    cmake += f'install(FILES "${{CMAKE_CURRENT_BINARY_DIR}}/sdk-compile-features.txt" DESTINATION share/{name})\n'
    (output / 'CMakeLists.txt').write_text(cmake)


def finalize(output):
    models = list((output / 'share').glob('*/capnproto-products.json'))
    if len(models) != 1:
        raise ValueError('ambiguous generated schema model')
    model = json.loads(models[0].read_text())
    model['libraryHashes'] = {str(p.relative_to(output)):digest(p) for p in sorted((output/'lib').iterdir()) if p.is_file() and not p.is_symlink()}
    if not model['libraryHashes']:
        raise ValueError('no installed generated library')
    models[0].write_text(json.dumps(model,sort_keys=True,indent=2)+'\n')


if __name__ == '__main__':
    if sys.argv[1] == '--finalize':
        finalize(Path(sys.argv[2]))
    else:
        generate(json.loads(Path(sys.argv[1]).read_text()), Path(sys.argv[2]))
