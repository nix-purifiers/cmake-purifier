# SPDX-License-Identifier: MIT
"""Record the native npm publication produced by the SDK's own build."""
import hashlib,json,sys,tarfile
from pathlib import Path
out=Path(sys.argv[1]);packed=json.loads((out/'npm-pack.json').read_text());assert len(packed)==1
archive=out/'archives'/packed[0]['filename']
with tarfile.open(archive) as tar:metadata=json.loads(tar.extractfile('package/package.json').read())
assert metadata==json.loads((out/'sdk/package.json').read_text())
# A new SDK with runtime dependencies needs their actual package graph captured.
if any(metadata.get(field) for field in ['dependencies','optionalDependencies','peerDependencies']):raise ValueError('SDK runtime has uncaptured native npm dependencies')
graph={'version':1,'primaries':{metadata['name']:'runtime'},'nodes':{'runtime':{'name':metadata['name'],'version':metadata['version'],'package':metadata,'archive':archive.name,'contentHash':hashlib.sha256(archive.read_bytes()).hexdigest(),'dependencies':{}}}}
(out/'graph.json').write_text(json.dumps(graph,sort_keys=True,indent=2)+'\n')
