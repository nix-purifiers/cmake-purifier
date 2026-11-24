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
    request = dict(spec['generation'], resources=case['resources'], roots=case['roots'])
    request_file = root / 'request.json'
    request_file.write_text(json.dumps(request))
    result = subprocess.run([sys.executable, spec['generator'], str(request_file),
                             str(root / 'source'), str(root / 'proof')], capture_output=True, text=True)
    assert result.returncode and case['diagnostic'] in result.stdout + result.stderr, result.stdout + result.stderr
    assert list((root / 'proof/programs').rglob('*.dart')), 'no actual native generator output'
    results.append({'diagnostic': case['diagnostic'], 'exitCode': result.returncode})
Path(sys.argv[2]).write_text(json.dumps(results, indent=2) + '\n')
