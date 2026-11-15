# SPDX-License-Identifier: MIT
"""Package native FlatBuffers Python namespaces and native reflection metadata."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile
from packaging.utils import canonicalize_name
from packaging.version import Version


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(spec, destination, proof):
    canonicalize_name(spec['name'], validate=True)
    Version(spec['version'])
    bundle = Path(spec['resources'])
    catalog = json.loads((bundle/'catalog.json').read_text())
    if catalog['format'] != 'purifier-resources-v1' or catalog['schema']['format'] != 'flatbuffers':
        raise ValueError('expected an explicitly selected FlatBuffers schema bundle')
    root = (bundle/'files').resolve(strict=True)
    sdk = Path(spec['sdk'])
    compiler = str(sdk/'bin/flatc')
    reflection = Path(spec['sdkSource'])/'reflection/reflection.fbs'
    version = subprocess.check_output([compiler, '--version'], text=True).strip()
    match = re.fullmatch(r'flatc version (\d+\.\d+\.\d+)', version)
    if match is None:
        raise ValueError('cannot read native flatc version')
    runtime = json.loads(Path(spec['runtimeProof']).read_text())
    if runtime['compilerVersion'] != version or runtime['version'] != match[1]:
        raise ValueError('native Python runtime differs from selected flatc')
    generated = proof/'generated';generated.mkdir()
    programs = proof/'programs';programs.mkdir()
    commands, models, hashes = [], {}, {}
    def run(command):
        subprocess.run(command, check=True)
        commands.append(command)
    for index, entry in enumerate(catalog['schema']['entrypoints']):
        source = (root/entry).resolve(strict=True)
        if not source.is_relative_to(root):
            raise ValueError('entrypoint escapes captured schema tree')
        folder = programs/str(index);folder.mkdir()
        run([compiler, '--binary', '--schema', '--bfbs-absolute-paths', '-I', str(root), '-o', str(folder), str(source)])
        binary = folder/(source.stem+'.bfbs')
        run([compiler, '--json', '--strict-json', '-o', str(folder), str(reflection), '--', str(binary)])
        model = json.loads((folder/(source.stem+'.json')).read_text())
        files = model.get('fbs_files', [])
        if not files:
            raise ValueError('native reflection omitted input file graph')
        selected = set()
        for record in files:
            path = Path(record['filename'])
            if not path.is_absolute():
                raise ValueError('native reflection did not retain absolute input paths')
            path = path.resolve(strict=True)
            if not path.is_relative_to(root):
                raise ValueError('native schema input escapes captured tree: '+str(path))
            logical = path.relative_to(root).as_posix()
            if logical not in catalog['files'] or digest(path) != catalog['files'][logical]['sha256']:
                raise ValueError('native schema input differs from captured hash: '+logical)
            hashes[logical] = digest(path);selected.add(str(path))
        if str(source) not in selected:
            raise ValueError('native reflection omitted selected entrypoint')
        for record in files:
            if any(str(Path(name).resolve(strict=True)) not in selected for name in record.get('included_filenames', [])):
                raise ValueError('native reflection include graph is incomplete')
        models[entry] = {'schema': model, 'binarySha256': digest(binary)}
    # Default per-schema generation retains native inter-module imports. The
    # Python backend's --gen-all flag suppresses those imports in this SDK.
    for index, logical in enumerate(sorted(hashes)):
        native=programs/('python-'+str(index));native.mkdir()
        run([compiler,'--python','-I',str(root),'-o',str(native),str(root/logical)])
        for path in sorted(native.rglob('*')):
            if not path.is_file():continue
            target=generated/path.relative_to(native)
            if target.exists():
                if target.read_bytes()!=path.read_bytes():raise ValueError('native generated Python outputs collide: '+str(path.relative_to(native)))
            else:
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    if (generated/'flatbuffers').exists() or (generated/'flatbuffers.py').exists():
        raise ValueError('generated namespace collides with native FlatBuffers runtime')
    modules = sorted(path.stem for path in generated.glob('*.py') if path.stem != '__init__')
    work = Path('python-source').resolve();work.mkdir()
    shutil.copytree(generated, work/'generated')
    text = '[build-system]\nrequires = ["setuptools", "wheel"]\nbuild-backend = "setuptools.build_meta"\n[project]\n'
    for key, value in {'name': spec['name'], 'version': spec['version'], 'dependencies': ['flatbuffers == '+runtime['version']]}.items():
        text += key+' = '+json.dumps(value)+'\n'
    text += '[tool.setuptools]\npackage-dir = {"" = "generated"}\npy-modules = '+json.dumps(modules)+'\n'
    text += '[tool.setuptools.packages.find]\nwhere = ["generated"]\nnamespaces = false\n'
    (work/'pyproject.toml').write_text(text)
    run([sys.executable, '-m', 'build', '--no-isolation', '--wheel', '--outdir', str(destination.resolve()), str(work)])
    wheels = list(destination.glob('*.whl'))
    if len(wheels) != 1:
        raise ValueError('native backend did not produce exactly one schema wheel')
    owned = {}
    with zipfile.ZipFile(wheels[0]) as wheel:
        for name in wheel.namelist():
            if name.endswith('.py'):
                source = generated/name
                if wheel.read(name) != source.read_bytes():
                    raise ValueError('wheel changed native generated source: '+name)
                owned[name] = digest(source)
    expected = {str(path.relative_to(generated)) for path in generated.rglob('*.py') if path != generated/'__init__.py'}
    if not owned or set(owned) != expected:
        raise ValueError('native backend omitted generated Python modules')
    shutil.copy(work/'pyproject.toml', proof/'pyproject.toml')
    record = {'format': 'purifier-flatbuffers-python-v1', 'resources': str(bundle), 'sdk': str(sdk),
              'compilerVersion': version, 'reflectionSchema': str(reflection), 'reflectionSchemaSha256': digest(reflection),
              'schemaHashes': hashes, 'nativeSchemas': models, 'generatedHashes': owned, 'runtime': runtime,
              'runtimeProof': spec['runtimeProof'], 'commands': commands, 'wheel': wheels[0].name,
              'wheelSha256': digest(wheels[0])}
    (proof/'flatbuffers-python.json').write_text(json.dumps(record, sort_keys=True, indent=2)+'\n')


if __name__ == '__main__':
    generate(json.loads(Path(sys.argv[1]).read_text()), Path(sys.argv[2]), Path(sys.argv[3]))
