# SPDX-License-Identifier: MIT
{
  runCommand,
  python3,
  stdenv,
  thrift,
}:
let
  backend = python3.withPackages (p: [
    p.build
    p.setuptools
    p.wheel
    p.packaging
  ]);
in
runCommand "thrift-native-python-runtime"
  {
    outputs = [
      "out"
      "proof"
    ];
    nativeBuildInputs = [
      backend
      stdenv.cc
    ];
  }
  ''
    export HOME="$TMPDIR/home" SOURCE_DATE_EPOCH=315532800 PYTHONHASHSEED=0
    mkdir -p "$HOME" "$out" "$proof"
    cp -r ${thrift.src}/lib/py source
    chmod -R u+w source
    python -m build --no-isolation --wheel --outdir "$out" source
    python ${./runtime-proof.py} ${thrift} ${thrift.src}/lib/py "$out" "$proof"
  ''
