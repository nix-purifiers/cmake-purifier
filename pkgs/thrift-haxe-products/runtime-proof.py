# SPDX-License-Identifier: MIT
"""Verify the original selected Haxe SDK package and its native repository."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


spec = json.loads(Path(sys.argv[1]).read_text())
outputs = [Path(path).resolve(strict=True) for path in spec['producerOutputs']]
dependencies = [{**item, 'path': Path(item['path']).resolve(strict=True)} for item in spec['dependencyOutputs']]


def owned(path, producer_only=False):
    path = Path(path).resolve(strict=True)
    roots = outputs if producer_only else outputs + [item['path'] for item in dependencies]
    if not any(path.is_relative_to(root) for root in roots):
        raise ValueError('native Haxe SDK path is outside its original producer outputs: ' + str(path))
    return path


source = Path(spec['sdkSource']).resolve(strict=True) / 'lib/haxe'
installed = owned(spec['installedRoot'], producer_only=True)
repository = owned(spec['repository'], producer_only=True)
if Path(spec['source']).resolve(strict=True) != source.parent.parent:
    raise ValueError('runtime callback changed the original selected SDK source')


def inventory(root):
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_file():
            if not path.resolve(strict=True).is_relative_to(root):
                raise ValueError('native package source escapes its original root')
            result[path.relative_to(root).as_posix()] = sha(path)
    return result


original = inventory(source)
if not original or inventory(installed) != original:
    raise ValueError('native Haxe SDK source files changed, disappeared, or gained foreign files')


def inspect(root):
    raw = subprocess.check_output([spec['inspect'], 'json', str(root / 'haxelib.json')], text=True)
    native = json.loads(raw)
    document = json.loads((root / 'haxelib.json').read_text())
    relative = Path(native['classPath'] or '.')
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('native Haxelib class path escapes its package')
    classes = owned(root / relative)
    return native, document, classes


sdk, manifest, sdk_classes = inspect(installed)
compiler = subprocess.check_output([spec['thrift'], '--version'], text=True).strip()
match = re.fullmatch(r'Thrift version (\d+\.\d+\.\d+)', compiler)
if not match or sdk['version'] != match.group(1):
    raise ValueError('original Haxe runtime belongs to a different native Thrift SDK')
versions = {
    'haxe': subprocess.check_output([spec['haxe'], '--version'], text=True).strip(),
    'haxelib': subprocess.check_output([spec['haxelib'], 'version'], text=True).strip(),
    'neko': subprocess.check_output([spec['neko'], '-version'], text=True).strip(),
}
if versions != spec['toolVersions']:
    raise ValueError('native runtime tools do not match the original selected Nix inputs')
nodes = {}
markers = {}
for folder in sorted(repository.iterdir()):
    if not folder.is_dir():
        raise ValueError('unexpected file in native SDK repository: ' + str(folder))
    if (folder / '.dev').is_file():
        marker = folder / '.dev'
        root = owned(marker.read_text().strip())
        if root != installed:
            raise ValueError('foreign development directory in original SDK repository')
    elif (folder / '.current').is_file():
        marker = folder / '.current'
        version_dir = marker.read_text().strip()
        if not version_dir or '/' in version_dir or '\\' in version_dir or version_dir in {'.', '..'}:
            raise ValueError('native SDK repository version pointer escapes its package')
        # Native Haxelib stores dotted versions in comma-separated folders.
        root = owned(folder / version_dir.replace('.', ','))
    else:
        raise ValueError('native SDK repository has no selected package version')
    native, document, classes = inspect(root)
    name = native['name']
    if name in nodes:
        raise ValueError('duplicate native SDK package name')
    nodes[name] = {'metadata': native, 'root': str(root), 'classRoot': str(classes),
                   'dependencies': document.get('dependencies', {}), 'files': inventory(root),
                   'folder': folder.name, 'marker': marker.name}
    markers[marker.relative_to(repository).as_posix()] = marker.read_text()
if sdk['name'] not in nodes or Path(nodes[sdk['name']]['root']) != installed:
    raise ValueError('native repository does not resolve the original SDK package')
active = set()


def visit(name):
    if name in active:
        return
    if name not in nodes:
        raise ValueError('native SDK dependency is missing: ' + name)
    active.add(name)
    for dependency, version in nodes[name]['dependencies'].items():
        if dependency not in nodes or (version and version != nodes[dependency]['metadata']['version']):
            raise ValueError('native SDK dependency is missing or incompatible: ' + dependency)
        visit(dependency)


visit(sdk['name'])
if active != set(nodes):
    raise ValueError('native SDK repository differs from its complete active dependency graph')
environment = dict(os.environ, HAXELIB_PATH=str(repository) + '/', HAXELIB_PURIFIER_REPOSITORY=str(repository))
paths = subprocess.check_output([spec['haxelib'], 'path', sdk['name']], env=environment, text=True)
resolved = {str(owned(line.strip())) for line in paths.splitlines() if line.strip() and not line.startswith('-')}
if resolved != {node['classRoot'] for node in nodes.values()}:
    raise ValueError('native Haxelib resolution differs from the original SDK graph')
Path(sys.argv[2]).write_text(json.dumps({
    'compilerVersion': compiler, 'sdk': sdk, 'toolVersions': versions,
    'sourceFiles': original, 'nodes': nodes, 'markers': markers,
    'nativePath': paths, 'producerIdentity': spec['producerIdentity'],
    'toolIdentities': spec['toolIdentities'],
    'dependencyOutputs': spec['dependencyOutputs'],
}, indent=2, sort_keys=True) + '\n')
