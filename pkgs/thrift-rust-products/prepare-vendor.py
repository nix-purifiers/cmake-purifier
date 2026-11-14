# SPDX-License-Identifier: MIT
"""Expose native vendor roots without re-vendoring away publication files."""
import shutil, sys, tomllib
from pathlib import Path
source=Path(sys.argv[1]).resolve(strict=True)
out=Path(sys.argv[2])
config=tomllib.loads((source/'.cargo/config.toml').read_text())
roots=[]
for entry in config.get('source',{}).values():
    if 'directory' in entry:
        root=Path(entry['directory'].replace('@vendor@',str(source))).resolve(strict=True)
        if not root.is_relative_to(source):raise ValueError('native vendor directory escapes captured vendor')
        roots.append(root)
if not roots:raise ValueError('native vendor configuration has no source directories')
shutil.copytree(source,out,symlinks=True)
out.chmod(0o755)
for root in roots:
    for package in sorted(root.iterdir()):
        if not (package/'Cargo.toml').is_file():continue
        relative=package.relative_to(source)
        target=out/package.name
        if target==out/relative:continue
        if target.exists() or target.is_symlink():raise ValueError('native vendor directory names collide: '+package.name)
        target.symlink_to(relative,target_is_directory=True)
