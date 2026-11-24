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
    (root / 'request.json').write_text(json.dumps(request))
    run = subprocess.run([sys.executable, spec['generator'], str(root / 'request.json'), str(root / 'source'), str(root / 'source-proof')], capture_output=True, text=True)
    if case['phase'] == 'install':
        assert not run.returncode, run.stdout + run.stderr
        request = dict(spec['installation'], sourceProof=str(root / 'source-proof'))
        (root / 'request.json').write_text(json.dumps(request))
        run = subprocess.run([sys.executable, spec['installer'], str(root / 'request.json'), str(root / 'source'), str(root / 'installed'), str(root / 'install-proof')], capture_output=True, text=True)
    assert run.returncode and case['diagnostic'] in run.stderr, case['diagnostic'] + ': ' + run.stdout + run.stderr
    results.append({'diagnostic': case['diagnostic'], 'exitCode': run.returncode})
for index, case in enumerate(spec['runtimeCases']):
    root = Path.cwd() / ('runtime-' + str(index))
    root.mkdir()
    request = dict(spec['installation'], **case['override'])
    (root / 'request.json').write_text(json.dumps(request))
    run = subprocess.run([sys.executable, spec['installer'], str(root / 'request.json'), spec['source'], str(root / 'installed'), str(root / 'install-proof')], capture_output=True, text=True)
    assert run.returncode and case['diagnostic'] in run.stderr, case['diagnostic'] + ': ' + run.stdout + run.stderr
    results.append({'diagnostic': case['diagnostic'], 'exitCode': run.returncode})
Path(sys.argv[2]).write_text(json.dumps(results, indent=2) + '\n')
