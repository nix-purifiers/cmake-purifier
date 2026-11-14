# SPDX-License-Identifier: MIT
{ pkgs, build }:
let
  source2 = pkgs.runCommand "flatbuffers-schema-v2" { } ''
    cp -r ${./fixtures/flatbuffers-schema} $out
    chmod -R u+w $out
    substituteInPlace $out/schemas/common/value.fbs --replace-fail 'answer:int' 'answer:long'
  '';
  make =
    src:
    let
      args = {
        inherit src;
        lockFile = ./fixtures/flatbuffers-schema/cmake-purifier.lock.json;
        pname = "flatbuffers-schema";
        version = "1.0.0";
        resourceRoots."." = "share/schemas";
        resourceSchema = {
          format = "flatbuffers";
          entrypoints = [ "main.fbs" ];
        };
      };
      raw = build args;
      built = build (
        args
        // {
          flatbuffersPackage = {
            name = "schema_proof";
            version = "1.0.0";
          };
        }
      );
    in
    assert raw.packages.flatbuffers-schema.drvPath == built.packages.flatbuffers-schema.drvPath;
    assert built.projections.flatbuffers-cpp.drvPath == built.packages.flatbuffers-bindings.drvPath;
    built.packages.flatbuffers-bindings;
  packages = [
    (make ./fixtures/flatbuffers-schema)
    (make source2)
  ];
in
pkgs.runCommand "flatbuffers-cpp-native-consumers"
  {
    nativeBuildInputs = [
      pkgs.cmake
      pkgs.ninja
      pkgs.stdenv.cc
      pkgs.pkg-config
      pkgs.python3
    ];
    buildInputs = [ pkgs.flatbuffers ];
    spec = builtins.toJSON {
      inherit packages;
      generator = ../pkgs/flatbuffers-products/generate.py;
    };
    passAsFile = [ "spec" ];
  }
  ''
    python ${./flatbuffers}/consume.py "$specPath" "$out"
  ''
