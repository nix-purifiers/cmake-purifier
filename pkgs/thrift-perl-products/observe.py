# SPDX-License-Identifier: MIT
"""Observe original installed native producers with the released Carton adapter."""
import json
from pathlib import Path
import sys

sys.path.insert(0, sys.argv[4])
from perl_library import canonical, digest, observe

request = json.loads(Path(sys.argv[1]).read_text())
request['dependencies'] = []
for supplier in request.pop('dependencyCatalogs'):
    raw = Path(supplier['path']).read_bytes()
    catalog = json.loads(raw)
    if catalog['producerIdentity'] != supplier['identity']:
        raise ValueError('Carton SDK catalog belongs to a different original producer')
    request['dependencies'].append({
        'input': supplier['identity'], 'catalogSha256': digest(raw),
        'semanticIdentity': catalog['semanticIdentity'],
    })
request.update(producerPath=sys.argv[2],
               producerOutputPaths=[sys.argv[2], sys.argv[3]],
               nativeMetadataPaths=[sys.argv[3] + '/native-MYMETA.json'])
request['allowedRoots'] += [sys.argv[2], sys.argv[3]]
Path(sys.argv[3] + '/observation.json').write_bytes(canonical(observe(request)) + b'\n')
