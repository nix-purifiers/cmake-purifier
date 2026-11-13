# SPDX-License-Identifier: MIT
{ pkgs, build }:
let
  source2 = pkgs.runCommand "thrift-erlang-schema-v2" { } ''
    cp -r ${./fixtures/thrift-cpp} "$out"
    chmod -R u+w "$out"
    substituteInPlace "$out/schemas/common/value.thrift" --replace-fail '1: i32 answer' '2: i32 answer'
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
          thriftErlangPackage = {
            name = "schema";
            version = "1.0.0";
          };
        }
      );
    in
    assert raw.packages.thrift-schema.drvPath == built.packages.thrift-schema.drvPath;
    built.packages.thrift-erlang-bindings;
  packages = [
    (make ./fixtures/thrift-cpp)
    (make source2)
  ];
in
pkgs.runCommand "thrift-erlang-native-consumers"
  {
    nativeBuildInputs = [
      pkgs.beamPackages.erlang
      pkgs.python3
    ];
    controls = builtins.toJSON {
      resources = toString (builtins.head packages).schemaResources;
      sdk = toString (builtins.head packages).sdk;
      package = toString (builtins.head packages);
      proof = toString (builtins.head packages).proof;
      generator = ../pkgs/thrift-erlang-products/generate.py;
    };
    passAsFile = [ "controls" ];
    ERL_FLAGS = "+S 2:2";
  }
  (
    ''
      mkdir -p "$out"
      cp ${./thrift-erlang/consume.erl} consume.erl
    ''
    + pkgs.lib.concatImapStrings (i: package: ''
      mkdir case${toString i}
      cd case${toString i}
      export ERL_LIBS="${package}/lib:${package.sdkRuntime}/lib"
      export EXPECTED_APP_ROOT=${package}
      export EXPECTED_RUNTIME_ROOT=${package.sdkRuntime}
      export EXPECTED_COMPILER_VERSION="$(${package.sdk}/bin/thrift --version)"
      erlc ../consume.erl
      export EXPECTED_WIRE=${if i == 1 then "0C00010800010000002A0000" else "0C00010800020000002A0000"}
      erl -noshell -pa . -s consume main > "$out/case${toString i}.txt"
      cp wire.bin "$out/case${toString i}.bin"
      cd ..
    '') packages
    + ''python ${./thrift-erlang/controls.py} "$controlsPath" "$out/controls.json"''
  )
