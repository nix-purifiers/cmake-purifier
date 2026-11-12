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
      built = build {
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
    in
    pkgs.callPackage ../pkgs/flatbuffers-products { } {
      resources = built.projections.resources;
      flatbuffersPackage = {
        name = "schema_proof";
        version = "1.0.0";
      };
    };
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
