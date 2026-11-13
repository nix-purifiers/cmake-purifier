# SPDX-License-Identifier: MIT
{
  lib,
  runCommand,
  python3,
  beamPackages,
  thrift,
}:
{ resources, thriftErlangPackage }:
let
  options = thriftErlangPackage;
  valid =
    builtins.isAttrs options
    &&
      builtins.attrNames options == [
        "name"
        "version"
      ]
    && builtins.isString options.name
    && builtins.match "[a-z][a-zA-Z0-9_]*" options.name != null
    && options.name != "thrift"
    && builtins.isString options.version
    && options.version != "";
  inherit (beamPackages) erlang;
  runtime =
    runCommand "thrift-native-erlang-runtime"
      {
        outputs = [
          "out"
          "proof"
        ];
        nativeBuildInputs = [
          erlang
          thrift
          python3
        ];
        ERL_FLAGS = "+S 2:2";
        PURIFIER_ERLANG_RUNTIME = toString erlang;
        passthru = {
          sdk = thrift;
          sdkSource = thrift.src;
          inherit erlang;
        };
      }
      ''
        mkdir -p "$out/lib/thrift/ebin" "$out/lib/thrift/include" "$out/lib/thrift/src"
        cp ${thrift.src}/lib/erl/include/*.hrl "$out/lib/thrift/include/"
        cp ${thrift.src}/lib/erl/src/*.erl "$out/lib/thrift/src/"
        for source in "$out/lib/thrift/src/"*.erl; do
          case "$source" in *_test.erl) continue ;; esac
          erlc -pa "$out/lib/thrift/ebin" -I "$out/lib/thrift/include" -o "$out/lib/thrift/ebin" "$source"
        done
        thrift --version > compiler-version.txt
        escript ${./application.escript} ${thrift.src}/lib/erl/src/thrift.app.src thrift compiler-version.txt "$out/lib/thrift/ebin" "$out/lib/thrift/ebin"
        python ${./runtime-proof.py} ${thrift.src} "$out" "$proof" ${thrift} ${erlang}
        cp ${thrift.src}/LICENSE ${thrift.src}/NOTICE "$out/"
      '';
  package =
    runCommand "thrift-generated-erlang-application"
      {
        outputs = [
          "out"
          "proof"
        ];
        nativeBuildInputs = [
          erlang
          thrift
          python3
        ];
        ERL_FLAGS = "+S 2:2";
        PURIFIER_ERLANG_RUNTIME = toString erlang;
        spec = builtins.toJSON {
          resources = toString resources;
          sdk = toString thrift;
        };
        passAsFile = [ "spec" ];
        passthru = {
          schemaResources = resources;
          sdk = thrift;
          sdkRuntime = runtime;
          inherit erlang;
        };
      }
      ''
        mkdir -p generated "$out/lib/${options.name}/ebin" "$out/lib/${options.name}/include" "$out/lib/${options.name}/src" "$proof"
        python ${./generate.py} "$specPath" generated "$proof"
        cp generated/*.erl "$out/lib/${options.name}/src/"
        cp generated/*.hrl "$out/lib/${options.name}/include/"
        erlc -pa ${runtime}/lib/thrift/ebin -I "$out/lib/${options.name}/include" -o "$out/lib/${options.name}/ebin" "$out/lib/${options.name}/src/"*.erl
        escript ${./application.escript} generated ${lib.escapeShellArg options.name} ${lib.escapeShellArg options.version} "$out/lib/${options.name}/ebin" ${runtime}/lib/thrift/ebin
        mkdir -p "$out/nix-support"
        printf '%s\n' ${runtime} > "$out/nix-support/propagated-build-inputs"
      '';
in
assert
  valid || throw "cmake-purifier: thriftErlangPackage requires an OTP application name and version";
package
