# SPDX-License-Identifier: MIT
{ pkgs, build }:
let
  source2 = pkgs.runCommand "thrift-schema-v2" { } ''
    cp -r ${./fixtures/thrift-cpp} $out
    chmod -R u+w $out
    substituteInPlace $out/schemas/common/value.thrift --replace-fail '1: i32 answer' '2: i32 answer'
  '';
  make =
    src:
    let
      args = {
        inherit src;
        lockFile = ./fixtures/thrift-cpp/cmake-purifier.lock.json;
        pname = "thrift-schema";
        version = "1.0.0";
        resourceRoots."." = "share/schemas";
        resourceSchema = {
          format = "thrift";
          entrypoints = [ "main.thrift" ];
        };
      };
      raw = build args;
      built = build (
        args
        // {
          thriftPackage = {
            name = "thrift_proof";
            version = "1.0.0";
          };
        }
      );
    in
    assert raw.packages.thrift-schema.drvPath == built.packages.thrift-schema.drvPath;
    assert built.packages.thrift-bindings.drvPath == built.projections.thrift-cpp.drvPath;
    built.packages.thrift-bindings;
  packages = [
    (make ./fixtures/thrift-cpp)
    (make source2)
  ];
in
pkgs.runCommand "thrift-cpp-native-consumers"
  {
    nativeBuildInputs = [
      pkgs.cmake
      pkgs.ninja
      pkgs.stdenv.cc
      pkgs.pkg-config
      pkgs.python3
    ];
    buildInputs = [ pkgs.thrift ];
    spec = builtins.toJSON {
      inherit packages;
      dlLibs = pkgs.lib.optionals (!pkgs.stdenv.hostPlatform.isDarwin) [ "-ldl" ];
      generator = ../pkgs/thrift-products/generate.py;
    };
    passAsFile = [ "spec" ];
  }
  ''
    python ${./thrift}/consume.py "$specPath" "$out"
  ''
