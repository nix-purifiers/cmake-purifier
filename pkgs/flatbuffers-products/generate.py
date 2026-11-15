# SPDX-License-Identifier: MIT
"""Use native flatc dependencies and code generation on an installed schema bundle."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
import sys


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(spec, output):
    bundle = Path(spec['resources'])
    catalog = json.loads((bundle / 'catalog.json').read_text())
    if catalog['format'] != 'purifier-resources-v1' or catalog['schema']['format'] != 'flatbuffers':
        raise ValueError('expected an explicitly selected FlatBuffers schema bundle')
    root = (bundle / 'files').resolve(strict=True)
    sdk = Path(spec['sdk'])
    flatc = str(sdk / 'bin/flatc')
    version = subprocess.check_output([flatc, '--version'], text=True).strip()
    sdk_version = re.fullmatch(r'flatc version (\d+\.\d+\.\d+)', version)
    if sdk_version is None:
        raise ValueError('cannot read native flatc SDK version: ' + version)
    commands, dependencies, source_hashes = [], {}, {}
    for entry in catalog['schema']['entrypoints']:
        command = [flatc, '--cpp', '-M', '-I', str(root), str(root / entry)]
        rules = subprocess.check_output(command, text=True)
        commands.append(command)
        dependencies[entry] = rules
        # flatc emits Make prerequisites, including recursively imported schemas.
        for name in shlex.split(rules.split(':', 1)[1].replace('\\\n', '')):
            path = Path(name).resolve(strict=True)
            relative = str(path.relative_to(root))
            if relative not in catalog['files'] or digest(path) != catalog['files'][relative]['sha256']:
                raise ValueError('native schema dependency does not match captured resources: ' + relative)
            source_hashes[relative] = digest(path)
    output.mkdir(parents=True)
    include = output / 'include'
    for relative in sorted(source_hashes):
        target = include / PurePosixPath(relative).parent
        target.mkdir(parents=True, exist_ok=True)
        command = [flatc, '--cpp', '--keep-prefix', '-I', str(root), '-o', str(target), str(root / relative)]
        subprocess.run(command, check=True)
        commands.append(command)
    generated = {str(p.relative_to(output)): digest(p) for p in sorted(include.rglob('*')) if p.is_file()}
    if not generated:
        raise ValueError('flatc produced no C++ headers')
    name = spec['name']
    cmake = output / 'lib/cmake' / name
    cmake.mkdir(parents=True)
    (cmake / (name + 'Config.cmake')).write_text(
        'include_guard(GLOBAL)\ninclude(CMakeFindDependencyMacro)\n'
        f'find_dependency(flatbuffers {sdk_version[1]} EXACT CONFIG REQUIRED PATHS "{sdk}/lib/cmake/flatbuffers" NO_DEFAULT_PATH)\n'
        f'add_library({name}::bindings INTERFACE IMPORTED)\n'
        f'set_target_properties({name}::bindings PROPERTIES\n'
        f' INTERFACE_INCLUDE_DIRECTORIES "{include}"\n'
        ' INTERFACE_COMPILE_FEATURES cxx_std_11\n'
        ' INTERFACE_LINK_LIBRARIES flatbuffers::flatbuffers)\n')
    subprocess.run(['cmake', '-DOUTPUT=' + str(cmake / (name + 'ConfigVersion.cmake')),
                    '-DVERSION=' + spec['version'], '-P', str(Path(__file__).with_name('version.cmake'))], check=True)
    pc = output / 'lib/pkgconfig'
    pc.mkdir(parents=True)
    (pc / (name + '.pc')).write_text(
        f'prefix={output}\nName: {name}\nDescription: Generated FlatBuffers C++ schemas\n'
        f'Version: {spec["version"]}\nRequires: flatbuffers\nCflags: -I${{prefix}}/include\n')
    support = output / 'nix-support'
    support.mkdir()
    (support / 'propagated-build-inputs').write_text(str(sdk) + '\n')
    (support / 'inputs').write_text(str(bundle) + '\n' + str(sdk) + '\n')
    (output / 'flatbuffers-products.json').write_text(json.dumps({
        'format': 'purifier-flatbuffers-cpp-v1', 'sdk': str(sdk), 'compilerVersion': version,
        'resources': str(bundle), 'schemaHashes': source_hashes, 'generatedHashes': generated,
        'nativeDependencies': dependencies, 'commands': commands,
    }, sort_keys=True, indent=2) + '\n')


if __name__ == '__main__':
    generate(json.loads(Path(sys.argv[1]).read_text()), Path(sys.argv[2]))
