# SPDX-License-Identifier: MIT
"""Record the native npm publication produced by the SDK's own build."""
import hashlib,json,shutil,sys,tarfile
from pathlib import Path
out=Path(sys.argv[1])
# Native pnpm creates these root cache-state records with timestamps/temp paths.
# Copy its compiler/tool payload and dependency links; native Nix fixups follow.
#
# installation bookkeeping is not used by node, tsc or esbuild afterwards.
excluded={'.modules.yaml','.pnpm-workspace-state-v1.json'}
for name in sorted(excluded):
 path=Path('node_modules')/name
 if path.exists():print('Raw native pnpm cache state '+name+':\n'+path.read_text(),file=sys.stderr)
shutil.copytree('node_modules',out/'sdk/node_modules',symlinks=True,ignore=lambda directory,names:excluded if Path(directory)==Path('node_modules') else set())
(out/'tool-payload.json').write_text(json.dumps({'excludedRootPnpmCacheState':sorted(excluded),'exportMethod':'native tree copy; standard Nix fixups retained','rawCacheState':'retained verbatim in native Nix build log'},indent=2)+'\n')
packed=json.loads((out/'npm-pack.json').read_text());assert len(packed)==1
archive=out/'archives'/packed[0]['filename']
with tarfile.open(archive) as tar:metadata=json.loads(tar.extractfile('package/package.json').read())
assert metadata==json.loads((out/'sdk/package.json').read_text())
# A new SDK with runtime dependencies needs their actual package graph captured.
if any(metadata.get(field) for field in ['dependencies','optionalDependencies','peerDependencies']):raise ValueError('SDK runtime has uncaptured native npm dependencies')
graph={'version':1,'primaries':{metadata['name']:'runtime'},'nodes':{'runtime':{'name':metadata['name'],'version':metadata['version'],'package':metadata,'archive':archive.name,'contentHash':hashlib.sha256(archive.read_bytes()).hexdigest(),'dependencies':{}}}}
(out/'graph.json').write_text(json.dumps(graph,sort_keys=True,indent=2)+'\n')
