# SPDX-License-Identifier: MIT
{
  lib,
  runCommand,
  python3,
  stdenv,
  thrift,
  purifier,
}:
{ resources, thriftPythonPackage }:
let
  options = thriftPythonPackage;
  valid =
    builtins.isAttrs options
    &&
      builtins.attrNames options == [
        "name"
        "version"
      ]
    && builtins.isString options.name
    && options.name != ""
    && builtins.isString options.version
    && options.version != "";
  backend = python3.withPackages (p: [
    p.build
    p.setuptools
    p.wheel
    p.packaging
  ]);
  runtimeWheel = import ./runtime.nix {
    inherit
      runCommand
      python3
      stdenv
      thrift
      ;
  };
  runtime = runtimeWheel // {
    projections = purifier.pythonProjections {
      repository = runtimeWheel;
      producer = runtimeWheel;
      inherit runCommand python3;
    };
  };
  wheel =
    runCommand "thrift-generated-python-wheel"
      {
        outputs = [
          "out"
          "proof"
        ];
        nativeBuildInputs = [
          backend
          thrift
        ];
        spec = builtins.toJSON {
          resources = toString resources;
          sdk = toString thrift;
          runtimeProof = "${runtimeWheel.proof}/runtime.json";
          inherit (options) name version;
        };
        passAsFile = [ "spec" ];
        passthru = {
          schemaResources = resources;
          sdk = thrift;
          sdkRuntime = runtime;
        };
      }
      ''
        export HOME="$TMPDIR/home" SOURCE_DATE_EPOCH=315532800 PYTHONHASHSEED=0
        mkdir -p "$HOME" "$out" "$proof"
        python ${./generate.py} "$specPath" "$out" "$proof"
      '';
in
assert
  valid
  || throw "cmake-purifier: thriftPythonPackage requires an explicit Python distribution name and version";
wheel
// {
  projections = purifier.pythonProjections {
    repository = wheel;
    producer = wheel;
    dependencies = [ runtime ];
    inherit runCommand python3;
  };
}
