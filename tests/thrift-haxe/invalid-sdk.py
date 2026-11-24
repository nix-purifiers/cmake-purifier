# SPDX-License-Identifier: MIT
"""Deliberately damage a genuine producer for verifier rejection controls."""
import json
from pathlib import Path
import shutil
import sys

original, out = map(Path, sys.argv[1:3])
shutil.copytree(original, out, symlinks=True)
for path in [out, *out.rglob('*')]:
    if not path.is_symlink():
        path.chmod(path.stat().st_mode | 0o200)
relative = (original / 'sdk-source').resolve().relative_to(original.resolve())
(out / 'sdk-source').unlink()
(out / 'sdk-source').symlink_to(out / relative)
root = out / relative
if sys.argv[3] == 'bytes':
    path = next((root / 'src').rglob('*.hx'))
    path.write_bytes(path.read_bytes() + b'\n// invalid SDK control\n')
elif sys.argv[3] == 'development':
    name = json.loads((root / 'haxelib.json').read_text())['name']
    (out / 'repository' / name.replace('.', ',') / '.dev').write_text(str(root))
else:
    name = sorted(json.loads((root / 'haxelib.json').read_text())['dependencies'])[0]
    folder = out / 'repository' / name.replace('.', ',')
    if folder.is_symlink():
        folder.unlink()
    else:
        shutil.rmtree(folder)
