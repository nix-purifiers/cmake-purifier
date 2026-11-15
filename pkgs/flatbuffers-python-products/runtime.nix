# SPDX-License-Identifier: MIT
{
  runCommand,
  python3,
  flatbuffers,
}:
let
  backend = python3.withPackages (p: [
    p.build
    p.setuptools
    p.wheel
    p.packaging
  ]);
in
runCommand "flatbuffers-native-python-runtime"
  {
    outputs = [
      "out"
      "proof"
    ];
    nativeBuildInputs = [
      backend
    ];
  }
  ''
    export HOME="$TMPDIR/home" SOURCE_DATE_EPOCH=315532800 PYTHONHASHSEED=0
    mkdir -p "$HOME" "$out" "$proof"
    cp -r ${flatbuffers.src}/python source
    chmod -R u+w source
    python -m build --no-isolation --wheel --outdir "$out" source
    python ${./runtime-proof.py} ${flatbuffers} ${flatbuffers.src}/python "$out" "$proof"
  ''
