# SPDX-License-Identifier: MIT
"""Corrupt a real SDK producer for causal rejection tests only."""
from pathlib import Path
import re
import shutil
import sys

original, out = map(Path, sys.argv[1:3])
shutil.copytree(original, out, symlinks=True)
for path in [out, *out.rglob('*')]:
    if path.is_symlink():
        resolved = path.resolve(strict=True)
        if resolved.is_relative_to(original):
            path.unlink()
            path.symlink_to(out / resolved.relative_to(original))
    else:
        path.chmod(path.stat().st_mode | 0o200)
if sys.argv[3] == 'bytes':
    path = out / 'runtime-source/Thrift.lua'
    path.write_bytes(path.read_bytes() + b'\n-- invalid SDK source control\n')
else:
    declaration = out / 'lib/libluasocket.la'
    name = re.search(r"^dlname='([^']+)'$", declaration.read_text(), re.M).group(1)
    (out / 'lib' / name).unlink()
