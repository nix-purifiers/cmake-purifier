# SPDX-License-Identifier: MIT
import json
from pathlib import Path
import shutil
import subprocess
import sys

spec=json.loads(Path(sys.argv[1]).read_text())
results=[]
for index,case in enumerate(spec['cases']):
 root=Path.cwd()/str(index);root.mkdir()
 request=dict(spec['generation'],resources=case['resources'])
 (root/'request.json').write_text(json.dumps(request))
 run=subprocess.run([sys.executable,spec['generator'],str(root/'request.json'),str(root/'generated'),str(root/'proof')],capture_output=True,text=True)
 assert run.returncode and case['diagnostic'] in run.stderr,run.stdout+run.stderr
 results.append({'diagnostic':case['diagnostic'],'exitCode':run.returncode})
for index,(kind,diagnostic) in enumerate([
 ('source','native generated OCaml source changed'),
 ('sdk','original OCaml SDK source changed'),
 ('metadata','native caller Oasis metadata changed'),
 ('omitted','native Oasis package omitted or added generated modules'),
]):
 root=Path.cwd()/('observe-'+str(index));root.mkdir()
 shutil.copytree(spec['source'],root/'src')
 shutil.copytree(spec['proof'],root/'proof')
 shutil.copytree(spec['package'],root/'package')
 for path in [root,*root.rglob('*')]:
  if not path.is_symlink():path.chmod(path.stat().st_mode|0o200)
 request=dict(spec['observation'])
 if kind=='source':
  path=next((root/'src').glob('*.ml'));path.write_bytes(path.read_bytes()+b'\n(* invalid native source control *)\n')
 elif kind=='sdk':
  shutil.copytree(request['runtime'],root/'sdk',symlinks=True)
  path=root/'sdk/original-source/src/Thrift.ml';path.chmod(path.stat().st_mode|0o200);path.write_bytes(path.read_bytes()+b'\n(* invalid SDK source control *)\n');request['runtime']=str(root/'sdk')
 elif kind=='metadata':
  path=root/'proof/original_oasis';path.write_bytes(path.read_bytes()+b'\n# invalid original metadata control\n')
 else:
  path=next((root/'package').rglob('main_consts.cmi'));path.unlink()
 (root/'request.json').write_text(json.dumps(request))
 run=subprocess.run([sys.executable,spec['observer'],str(root/'request.json'),str(root/'package'),str(root/'proof'),spec['inspector']],cwd=root,capture_output=True,text=True)
 assert run.returncode and diagnostic in run.stderr,kind+': '+run.stdout+run.stderr
 results.append({'diagnostic':diagnostic,'exitCode':run.returncode})
Path(sys.argv[2]).write_text(json.dumps(results,indent=2)+'\n')
