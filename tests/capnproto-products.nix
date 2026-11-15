# SPDX-License-Identifier: MIT
{ pkgs, build }:
let
  source2 = pkgs.runCommand "capnproto-schema-v2" { } ''
    cp -r ${./fixtures/capnproto-schema} $out
    chmod -R u+w $out
    substituteInPlace $out/schemas/common/value.capnp --replace-fail 'Int32;' 'Int32 = 1;'
  '';
  make =
    src:
    let
      args = {
        inherit src;
        lockFile = ./fixtures/capnproto-schema/cmake-purifier.lock.json;
        pname = "capnproto-schema";
        version = "1.0.0";
        resourceRoots."." = "share/schemas";
        resourceSchema = {
          format = "capnproto";
          entrypoints = [ "main.capnp" ];
        };
      };
      raw = build args;
      built = build (
        args
        // {
          capnprotoPackage = {
            name = "capnp_proof";
            version = "1.0.0";
          };
        }
      );
    in
    assert raw.packages.capnproto-schema.drvPath == built.packages.capnproto-schema.drvPath;
    assert built.projections.capnproto-cpp.drvPath == built.packages.capnproto-bindings.drvPath;
    built.packages.capnproto-bindings;
  packages = [
    (make ./fixtures/capnproto-schema)
    (make source2)
  ];
in
pkgs.runCommand "capnproto-cpp-native-consumers"
  {
    nativeBuildInputs = [
      pkgs.cmake
      pkgs.ninja
      pkgs.stdenv.cc
      pkgs.pkg-config
      pkgs.python3
    ];
    buildInputs = [ pkgs.capnproto ];
    spec = builtins.toJSON {
      inherit packages;
      dlLibs = pkgs.lib.optionals (!pkgs.stdenv.hostPlatform.isDarwin) [ "-ldl" ];
      generator = ../pkgs/capnproto-products/generate.py;
      inspector = "${(builtins.head packages).nativeInspector}/bin/inspect";
    };
    passAsFile = [ "spec" ];
  }
  ''
    python ${./capnproto}/consume.py "$specPath" "$out"
  ''
