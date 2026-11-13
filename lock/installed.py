# SPDX-License-Identifier: MIT
"""Read installed outputs under the requested prefix or an owned build bundle."""
import json
import os
from pathlib import Path


def _within(path, root):
    return os.path.commonpath((str(path), str(root))) == str(root)


def _absolute(path):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError(f'install path is not an absolute path without traversal: {path}')
    return path


def _owned_root(path, owner):
    path = _absolute(path)
    if not _within(path, owner) or not _within(path.resolve(), owner.resolve()):
        raise ValueError(f'install prefix is outside its owned directory {owner}: {path}')
    if not path.is_dir():
        raise ValueError(f'install prefix is missing or is not a directory: {path}')
    return path


def _member(path, root):
    path = _absolute(path)
    if not _within(path, root) or not _within(path.resolve(), root.resolve()):
        raise ValueError(f'installed path escapes the captured prefix {root}: {path}')
    if not path.exists() or not (path.is_file() or path.is_symlink()):
        raise ValueError(f'installed file is missing, dangling, or not a file: {path}')
    return os.path.relpath(path, root)


def read_outputs(build_dir, prefix):
    build = _absolute(build_dir)
    requested = _absolute(prefix)
    manifest = build / 'install_manifest.txt'
    if not manifest.exists():
        return None
    paths = [_absolute(line) for line in manifest.read_text().splitlines() if line]
    # Preserve the established no-install-rules result, including Hello Algo.
    if not paths and not requested.exists():
        return None
    if all(_within(path, requested) for path in paths):
        root = _owned_root(requested, build.parent)
    else:
        candidates = [line.split('=', 1)[1] for line in (build / 'CMakeCache.txt').read_text().splitlines()
                      if line.startswith('CMAKE_INSTALL_PREFIX:') and '=' in line]
        if len(candidates) != 1:
            raise ValueError('install wrote outside the requested prefix without a unique CMAKE_INSTALL_PREFIX')
        _owned_root(build, build.parent)
        root = _owned_root(candidates[0], build)
    installed = sorted(_member(path, root) for path in paths)
    installed_set = set(installed)
    targets = {}
    reply = build / '.cmake/api/v1/reply'
    indexes = sorted(reply.glob('index-*.json'))
    if not indexes:
        raise ValueError(f'CMake wrote no File API reply in {reply}')
    index = json.loads(indexes[-1].read_text())
    codemodel_file = next(obj['jsonFile'] for obj in index['objects'] if obj['kind'] == 'codemodel')
    codemodel = json.loads((reply / codemodel_file).read_text())
    for ref in codemodel['configurations'][0]['targets']:
        target = json.loads((reply / ref['jsonFile']).read_text())
        if 'install' not in target:
            continue
        names = {os.path.basename(artifact['path']) for artifact in target.get('artifacts', [])}
        # File API destinations may repeat for distinct install rules. Keep
        # their multiplicity to preserve the existing lockfile representation.
        files = []
        for destination in target['install']['destinations']:
            directory = Path(destination['path'])
            if '..' in directory.parts:
                raise ValueError(f'File API install destination contains traversal: {directory}')
            absolute = directory if directory.is_absolute() else root / directory
            if not _within(absolute, root) or not _within(absolute.resolve(), root.resolve()):
                # Optional/EXCLUDE_FROM_ALL rules can describe destinations
                # that were not installed. Only the already-validated
                # manifest members are outputs; never serialize these hints.
                continue
            for name in names:
                file = os.path.normpath(os.path.join(os.path.relpath(absolute, root), name))
                if file in installed_set:
                    files.append(file)
        if files:
            targets[target['name']] = {'type': target['type'], 'files': sorted(files)}
    return {'files': installed, 'targets': targets}
