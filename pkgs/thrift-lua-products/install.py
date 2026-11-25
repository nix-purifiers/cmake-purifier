# SPDX-License-Identifier: MIT
"""Stage exact native modules and verify original SDK and loader ownership."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(root):
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('original Lua SDK source must contain regular files')
        if path.is_file():
            result[path.relative_to(root).as_posix()] = sha(path)
    return result


spec = json.loads(Path(sys.argv[1]).read_text())
source, destination, proof = map(Path, sys.argv[2:])
proof.mkdir(parents=True, exist_ok=True)
sdk = Path(spec['runtime']).resolve(strict=True)
original = Path(spec['sdkSource']).resolve(strict=True) / 'lib/lua'
installed = sdk / 'share/lua' / spec['abi']
original_copy = sdk / 'runtime-source'
source_hashes = inventory(original)
if not source_hashes or inventory(original_copy) != source_hashes:
    raise ValueError('original native Lua SDK source changed or is incomplete')
for path in original.glob('*.lua'):
    if not (installed / path.name).is_file() or sha(installed / path.name) != sha(path):
        raise ValueError('installed original Lua SDK module changed')
model = json.loads((Path(spec['sourceProof']) / 'thrift-lua.json').read_text())
makefile = (sdk / 'native-build/Makefile').read_text().replace('\\\n', ' ')
version = re.search(r'^PACKAGE_VERSION\s*=\s*(\S+)', makefile, re.M)
if not version or model['compilerVersion'] != 'Thrift version ' + version.group(1):
    raise ValueError('original Lua SDK build version differs from native compiler')
if not re.search(r'^LUA\s*=\s*' + re.escape(spec['lua'] + '/bin/lua') + r'\s*$', makefile, re.M):
    raise ValueError('native Lua SDK was built for a different original interpreter')
version_run = subprocess.run([spec['lua'] + '/bin/lua', '-v'], check=True, capture_output=True, text=True)
lua_version = (version_run.stdout + version_run.stderr).strip()
if not re.match(r'Lua ' + re.escape(spec['luaVersion']) + r'(?:\s|$)', lua_version):
    raise ValueError('native Lua interpreter differs from selected original SDK')
targets = re.search(r'^lib_LTLIBRARIES\s*=\s*(.+)$', makefile, re.M)
if not targets:
    raise ValueError('original native Lua SDK library declarations are absent')
for field, expected in [('LUA_INCLUDE', '-I' + spec['lua'] + '/include'), ('LUA_LIB', '-L' + spec['lua'] + '/lib -llua')]:
    observed = re.search(r'^' + field + r'\s*=\s*(.+)$', makefile, re.M)
    if not observed or observed.group(1).strip() != expected:
        raise ValueError('native Lua SDK headers or linkage differ from original interpreter')
dependency_files = {path.name: path for path in (sdk / 'native-build/dependencies').glob('*.Plo')}
if not dependency_files:
    raise ValueError('native SDK compiler dependency graph is missing')
libraries = {}
compiled_sources = {}
for target in targets.group(1).split():
    if not re.fullmatch(r'[A-Za-z0-9_]+\.la', target):
        raise ValueError('unsupported original native Lua SDK target')
    declaration = sdk / 'lib' / target
    text = declaration.read_text()
    dlname = re.search(r"^dlname='([^']+)'$", text, re.M)
    if not dlname:
        raise ValueError('native Lua SDK shared library is absent')
    candidate = sdk / 'lib' / dlname.group(1)
    if not candidate.exists():
        raise ValueError('original native Lua SDK shared library is missing')
    library = candidate.resolve(strict=True)
    if not library.is_relative_to(sdk):
        raise ValueError('native Lua SDK library escapes its original producer')
    variable = target[:-3] + '_la_SOURCES'
    declared = re.search(r'^' + re.escape(variable) + r'\s*=\s*(.+)$', makefile, re.M)
    if not declared:
        raise ValueError('original native SDK source declarations are missing')
    for relative in declared.group(1).split():
        if relative not in source_hashes:
            raise ValueError('native SDK source is absent from original inventory')
        matches = [path for path in dependency_files.values() if re.search(r'(?:^|\s)' + re.escape(relative) + r'(?:\s|$)', path.read_text().replace('\\\n', ' '))]
        if len(matches) != 1:
            raise ValueError('native SDK compiler dependency graph lacks a unique original source: ' + relative)
        compiled_sources[relative] = {'sha256': source_hashes[relative], 'dependencyFile': str(matches[0]), 'dependencySha256': sha(matches[0])}
    standard = sdk / 'lib/lua' / spec['abi'] / (target[:-3] + '.so')
    if standard.resolve(strict=True) != library:
        raise ValueError('native Lua SDK module layout changed its original library')
    libraries[target[:-3]] = {'path': str(library), 'sha256': sha(library), 'declarationSha256': sha(declaration)}
destination.mkdir(parents=True, exist_ok=True)
modules = []
installed_files = {}
for relative, digest in model['generatedHashes'].items():
    path = source / relative
    if sha(path) != digest:
        raise ValueError('native generated Lua source changed')
    module = relative[:-4].replace('/', '.')
    if any(not part or part in {'.', '..'} for part in module.split('.')):
        raise ValueError('native Lua module has an unsafe identity')
    # Keep the native module name; install it in Lua's standard search layout.
    installed_relative = module.replace('.', '/') + '.lua'
    target = destination / installed_relative
    if target.exists():
        raise ValueError('native Lua module installation paths collide')
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, target)
    modules.append(module)
    installed_files[relative] = installed_relative
order, active, visiting = [], set(), set()
def visit(name):
    if name in visiting:
        raise ValueError('native Lua schema include graph is cyclic')
    if name in active:
        return
    visiting.add(name)
    for dependency in model['nativeModels'][name]['includes']:
        visit(dependency)
    visiting.remove(name)
    active.add(name)
    order.append(name)
for name in sorted(model['nativeModels']):
    visit(name)
ordered_modules = []
for name in order:
    records = [row for row in model['ownership'] if row['program'] == name]
    for row in sorted(records, key=lambda row: (not row['path'].endswith('_ttypes.lua'), row['path'])):
        ordered_modules.append(row['path'][:-4].replace('/', '.'))
if set(ordered_modules) != set(modules):
    raise ValueError('native Lua module ownership is incomplete')
module_file = proof / 'native-modules.txt' 
sdk_modules = [path.stem for path in sorted(installed.glob('*.lua'))]
if set(modules) & set(sdk_modules + list(libraries)):
    raise ValueError('generated Lua module shadows original SDK module')
module_file.write_text(''.join('sdk\t' + name + '\n' for name in sdk_modules) + ''.join('generated\t' + name + '\n' for name in ordered_modules))
env = dict(os.environ, LUA_PATH=str(destination) + '/?.lua;' + str(installed) + '/?.lua', LUA_CPATH=str(sdk / 'lib/lua' / spec['abi']) + '/?.so')
trace = proof / 'native-load.tsv'
run = subprocess.run([spec['lua'] + '/bin/lua', spec['loader'], str(module_file), str(trace)], env=env, capture_output=True, text=True)
(proof / 'native-load.stdout').write_text(run.stdout)
(proof / 'native-load.stderr').write_text(run.stderr)
if run.returncode:
    raise ValueError('native Lua load rejected: ' + run.stderr)
roots = [(destination.resolve(), 'generated'), (installed.resolve(), 'original SDK Lua'), ((sdk / 'lib').resolve(), 'original SDK native')]
loaded = []
for line in trace.read_text().splitlines():
    name, filename = line.split('\t')
    path = Path(filename).resolve(strict=True)
    owners = [(root, owner) for root, owner in roots if path.is_relative_to(root)]
    if len(owners) != 1:
        raise ValueError('native Lua module lacks a unique original producer: ' + str(path))
    loaded.append({'module': name, 'path': str(path), 'owner': owners[0][1], 'sha256': sha(path)})
if set(row['module'] for row in loaded) != set(modules + sdk_modules + list(libraries)):
    raise ValueError('native Lua did not load the complete original SDK and generated module graph')
record = {'kind': 'native-thrift-lua-package', 'compilerVersion': model['compilerVersion'], 'luaVersion': lua_version,
          'runtime': str(sdk), 'originalSDKSource': str(original), 'originalSDKFiles': source_hashes,
          'nativeLibraries': libraries, 'compiledSources': compiled_sources, 'modules': modules, 'installedFiles': installed_files, 'generatedHashes': model['generatedHashes'], 'loaded': loaded}
(proof / 'native-lua.json').write_text(json.dumps(record, indent=2) + '\n')
