# SPDX-License-Identifier: MIT
"""Reject native generated module paths that shadow selected Perl libraries."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

request = json.loads(Path(sys.argv[1]).read_text())
runtime = json.loads(Path(request['runtimeProof']).read_text())
results = []
for index, case in enumerate(request['cases']):
    modules = runtime['modules'][case['module']]
    for native in modules:
        assert hashlib.sha256(Path(native['origin']).read_bytes()).hexdigest() == native['sha256']
    with tempfile.TemporaryDirectory(prefix='native-perl-shadow-') as temporary:
        root = Path(temporary)
        spec = {key: request[key] for key in ['sdk', 'runtimeProof', 'makefileTool']}
        spec.update(resources=case['resources'], name='Example::GeneratedShadow', version='1.0.0')
        spec_path = root / 'spec.json'
        spec_path.write_text(json.dumps(spec))
        command = [sys.executable, request['generator'], str(spec_path), str(root / 'source'), str(root / 'proof')]
        result = subprocess.run(command, capture_output=True, text=True)
        expected = 'native generated Perl module shadows selected runtime: ' + case['module']
        if result.returncode == 0 or expected not in result.stderr:
            raise AssertionError('native shadowing guard failed: ' + result.stderr)
        emitted = list((root / 'proof' / 'programs').rglob(case['module']))
        if len(emitted) != 1:
            raise AssertionError('negative control did not preserve one actual native compiler output')
        results.append({'module': case['module'], 'exitCode': result.returncode,
                        'nativeOrigins': modules, 'nativeGeneratedSha256': hashlib.sha256(emitted[0].read_bytes()).hexdigest(),
                        'expectedDiagnostic': expected})
Path(sys.argv[2]).write_text(json.dumps(results, indent=2) + '\n')
