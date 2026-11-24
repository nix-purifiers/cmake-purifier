# SPDX-License-Identifier: MIT
"""Build the genuine SDK ZIP and install it with the selected native client."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

spec = json.loads(Path(sys.argv[1]).read_text())
out = Path(sys.argv[2])
out.mkdir()
repository = out / 'repository'
shutil.copytree(spec['repository'], repository, symlinks=True)
repository.chmod(repository.stat().st_mode | 0o200)
archives = Path('archives').resolve()
archives.mkdir()
subprocess.run([sys.executable, spec['releaseTool'], spec['lock'], spec['source'],
                str(archives), spec['inspect']], check=True)
files = list(archives.glob('*.zip'))
assert len(files) == 1
native = json.loads(subprocess.check_output([spec['inspect'], 'zip', str(files[0])], text=True))
env = dict(os.environ, HAXELIB_PATH=str(repository) + '/', HAXELIB_PURIFIER_REPOSITORY=str(repository),
           HAXELIB_PURIFIER_FROZEN='1')
subprocess.run([spec['haxelib'], 'install', str(files[0]), '--always'], env=env, check=True)
installed = repository / native['name'].replace('.', ',') / native['version'].replace('.', ',')
assert installed.is_dir()
(out / 'sdk-source').symlink_to(installed)
shutil.copyfile(files[0], out / 'sdk.zip')
