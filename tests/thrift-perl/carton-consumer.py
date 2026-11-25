#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Capture and replay the owning CMake producer with the released Carton CLI."""
import json
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[2]


def run(args, **options):
    result = subprocess.run(list(map(str, args)), capture_output=True, text=True, **options)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout.strip()


source = run(['nix', 'eval', '--impure', '--raw', '--expr',
              '(builtins.getFlake ' + json.dumps(str(repo)) + ').outPath'])
with tempfile.TemporaryDirectory(prefix='cmake-carton-thrift-') as temporary:
    root = Path(temporary)
    supplier = root / 'supplier'
    supplier.mkdir()
    (supplier / 'flake.nix').write_text(
        '{outputs={self}:import (' + json.dumps(source + '/tests/thrift-perl/carton-supplier.nix')
        + ') {cmakeSource=' + json.dumps(source) + ';};}\n')
    cli = Path(run(['nix', 'build', '--impure', '--no-link', '--print-out-paths',
                    'path:' + str(supplier) + '#cli'])) / 'bin/carton-purifier'
    original = b"requires 'SchemaMain::Envelope';\nrequires 'SchemaValue::Value';\nrequires 'SchemaMain::AnswerServiceClient';\n"
    (root / 'cpanfile').write_bytes(original)
    run([cli, '--project', root, 'lock', '--dependency', 'path:./supplier'])
    assert (root / 'cpanfile').read_bytes() == original
    lock = json.loads((root / 'carton-purifier.lock.json').read_text())
    assert lock['schemaVersion'] == 2 and lock['entries'] == [] and lock['distributions'] == []
    run([cli, '--project', root, 'prefetch'])
    script = repo / 'tests/thrift-perl/consume.pl'
    result = json.loads(run([cli, '--project', root, '--native', '--tool=perl', '--', script]))
    assert result['answer'] == 42 and result['rpc'] == 43, result
    shell = json.loads(run([cli, '--project', root, 'shell', '--', 'perl', script]))
    assert shell == result
    release = Path(run([cli, '--project', root, 'release']))
    assert (release / 'source.tar.gz').is_file()
    print(json.dumps({'native': result, 'shell': shell, 'cpanDistributions': 0,
                      'release': str(release)}, indent=2))
