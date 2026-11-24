# SPDX-License-Identifier: MIT
{
  lib,
  runCommand,
  python3,
  thrift,
}:
{ resources, thriftDartPackage }:
let
  options = thriftDartPackage;
  valid =
    builtins.isAttrs options
    && builtins.attrNames options == [ "roots" ]
    && builtins.isList options.roots
    && options.roots != [ ]
    && builtins.length options.roots == builtins.length (lib.unique options.roots)
    && builtins.all (
      root: builtins.isString root && builtins.match "[A-Za-z_][A-Za-z0-9_]*" root != null
    ) options.roots;
  python = python3.withPackages (ps: [ ps.pyyaml ]);
  source =
    runCommand "thrift-generated-dart-packages"
      {
        outputs = [
          "out"
          "proof"
        ];
        nativeBuildInputs = [ python ];
        spec = builtins.toJSON {
          resources = toString resources;
          sdk = toString thrift;
          sdkSource = toString thrift.src;
          inherit (options) roots;
        };
        passAsFile = [ "spec" ];
        passthru = {
          sdk = thrift;
          sdkSource = thrift.src;
          schemaResources = resources;
        };
      }
      ''
        python3 ${./generate.py} "$specPath" "$out" "$proof"
      '';
  projection = source // {
    pathSources =
      map (root: {
        src = source;
        inherit root;
      }) options.roots
      ++ [
        {
          src = thrift.src;
          root = "lib/dart";
        }
      ];
    originalProducer = source;
  };
in
assert lib.assertMsg valid "thriftDartPackage requires explicit unique native Pub package roots";
source // { projections.pub = projection; }
