# SPDX-License-Identifier: MIT
"""Record the actual native CMake parent, independently of environment labels."""
import json
import os
from pathlib import Path
import sys
command, root, version, output = sys.argv[1:]
actual = str(Path('/proc', str(os.getppid()), 'exe').resolve(strict=True))
assert actual == str(Path(command).resolve()), (actual, command)
Path(output).write_text(json.dumps(dict(executable=actual, moduleRoot=root, version=version), sort_keys=True) + '\n')
