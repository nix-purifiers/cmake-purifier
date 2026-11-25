# SPDX-License-Identifier: MIT
import json
from pathlib import Path
import subprocess
import sys

spec = json.loads(Path(sys.argv[1]).read_text())
results = []
for index, case in enumerate(spec['cases']):
    root = Path.cwd() / str(index)
    root.mkdir()
    request = dict(spec['generation'], resources=case['resources'])
    if 'manifest' in case:
        request['manifest'] = case['manifest']
    request_file = root / 'request.json'
    request_file.write_text(json.dumps(request))
    generated = subprocess.run([sys.executable, spec['generator'], str(request_file),
                                str(root / 'source'), str(root / 'source-proof')], capture_output=True, text=True)
    run = generated
    if case['phase'] == 'install':
        assert not generated.returncode, generated.stdout + generated.stderr
        install = dict(spec['installation'], sourceProof=str(root / 'source-proof'))
        request_file.write_text(json.dumps(install))
        run = subprocess.run([sys.executable, spec['installer'], str(request_file),
                              str(root / 'source'), str(root / 'installed'), str(root / 'install-proof')],
                             capture_output=True, text=True)
    assert run.returncode and case['diagnostic'] in run.stdout + run.stderr, f"case {index} {case['diagnostic']} exit {run.returncode}: " + run.stdout + run.stderr
    if case.get('expectHaxeOutput', True):
        assert list((root / 'source-proof/programs').rglob('*.hx')), 'no actual native Haxe output'
    record = {'diagnostic': case['diagnostic'], 'exitCode': run.returncode}
    if case['phase'] == 'install':
        shadow = json.loads((root / 'install-proof/sdk-shadow.json').read_text())
        assert shadow['actualParsedOrigins'], 'no actual native class resolution for shadow control'
        record['nativeResolution'] = shadow
    results.append(record)
for index, case in enumerate(spec['runtimeCases']):
    root = Path.cwd() / ('runtime-' + str(index))
    root.mkdir()
    request_file = root / 'request.json'
    request_file.write_text(json.dumps(case['request']))
    run = subprocess.run([sys.executable, spec['runtimeVerifier'], str(request_file), str(root / 'proof.json')],
                         capture_output=True, text=True)
    assert run.returncode and case['diagnostic'] in run.stderr, run.stdout + run.stderr
    results.append({'diagnostic': case['diagnostic'], 'exitCode': run.returncode})
Path(sys.argv[2]).write_text(json.dumps(results, indent=2) + '\n')
