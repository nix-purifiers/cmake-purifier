# SPDX-License-Identifier: MIT
{
  pkgs,
  build,
  npmBuilder,
  purifier,
}:
let
  sdkSource = builtins.fetchTree {
    type = "tarball";
    url = pkgs.thrift.src.url;
    narHash = pkgs.thrift.src.outputHash;
  };
  runtimeBuilder = args: npmBuilder (args // { src = sdkSource; });
  sdk = runtimeBuilder {
    buildScripts = [ ];
    doCheck = false;
  };
  typeSdk = npmBuilder {
    src = ./fixtures/thrift-javascript-types;
    buildScripts = [ ];
  };
  source1 = pkgs.runCommand "thrift-javascript-qualified-types" { } ''
    cp -r ${./fixtures/thrift-cpp} $out
    chmod -R u+w $out
    echo 'namespace cpp a
    struct Value { 1: i32 answer }' > "$out/schemas/a.thrift"
    echo 'namespace cpp b
    struct Value { 1: i32 answer }' > "$out/schemas/b.thrift"
    substituteInPlace "$out/schemas/main.thrift" --replace-fail 'include "common/value.thrift"' 'include "common/value.thrift"
    include "a.thrift"
    include "b.thrift"'
  '';
  source2 = pkgs.runCommand "thrift-javascript-second-field" { } ''
    cp -r ${source1} $out
    chmod -R u+w $out
    substituteInPlace $out/schemas/common/value.thrift --replace-fail '1: i32 answer' '2: i32 answer'
  '';
  compiler =
    pkgs.runCommand "thrift-sdk-native-typescript"
      {
        nativeBuildInputs = [
          pkgs.nodejs
          pkgs.makeWrapper
        ];
      }
      ''
        export HOME="$TMPDIR/home" npm_config_cache="$TMPDIR/npm-cache"
        mkdir -p "$HOME" "$npm_config_cache/_cacache"
        cp -rs --no-preserve=mode ${sdk.cache}/. "$npm_config_cache/_cacache"
        cp -r ${sdkSource} source
        chmod -R u+w source
        cd source
        npm ci --offline --ignore-scripts --no-audit --no-fund
        mkdir -p "$out/bin"
        cp -r node_modules/typescript "$out/typescript"
        makeWrapper ${pkgs.nodejs}/bin/node "$out/bin/tsc" --add-flags "$out/typescript/bin/tsc"
      '';
  make =
    src: withTypes: aliases:
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
          thriftJavaScriptPackage = {
            name = if aliases then "@proof/thrift-aliases" else "@proof/thrift-schemas";
            version = "1.0.0";
            entrypoints = (
              if aliases then
                {
                  default = "main_types";
                  class = "value_types";
                  __proto__ = "a_types";
                }
              else
                {
                  schema = "main_types";
                  common = "value_types";
                  rpc = "AnswerService";
                  a = "a_types";
                  b = "b_types";
                }
            );
          };
          thriftJavaScriptRuntimeBuilder = runtimeBuilder;
          thriftJavaScriptDependencies = pkgs.lib.optional withTypes typeSdk.release;
        }
      );
      package = built.packages.thrift-javascript-bindings;
      install = purifier.npmInstallRepository {
        dependencies = [ package ];
        inherit (pkgs) runCommand python3;
      };
    in
    assert raw.packages.thrift-schema.drvPath == built.packages.thrift-schema.drvPath;
    {
      generated = toString package;
      repository = toString package.projections.npm;
      catalog = package.projections.npm.catalog;
      install = toString install;
      installCatalog = install.catalog;
      cpp = toString built.packages.thrift-bindings;
    };
  missingResources =
    !(builtins.tryEval
      (build {
        src = ./fixtures/thrift-cpp;
        thriftJavaScriptPackage = {
          name = "schema-proof";
          version = "1.0.0";
          entrypoints.schema = "main_types";
        };
      }).packages.schema_bundle.drvPath
    ).success;
  missingBuilder =
    !(builtins.tryEval
      (build {
        src = ./fixtures/thrift-cpp;
        resourceRoots."." = "share/schemas";
        resourceSchema = {
          format = "thrift";
          entrypoints = [ "main.thrift" ];
        };
        thriftJavaScriptPackage = {
          name = "schema-proof";
          version = "1.0.0";
          entrypoints.schema = "main_types";
        };
      }).packages.thrift-javascript-bindings.drvPath
    ).success;
in
assert missingResources;
assert missingBuilder;
pkgs.runCommand "thrift-javascript-native-consumers"
  {
    nativeBuildInputs = [
      pkgs.python3
      pkgs.nodejs
      pkgs.stdenv.cc
      pkgs.pkg-config
      compiler
    ];
    buildInputs = [ pkgs.thrift ];
    spec = builtins.toJSON {
      versions = [
        (make source1 true false)
        (make source2 true false)
      ];
      noTypes = make source1 false false;
      aliases = make source1 true true;
      consumer = ./thrift-javascript/consumer.cjs;
      typescriptConsumer = ./thrift-javascript/consumer.ts;
      generator = ../pkgs/thrift-javascript-products/generate.py;
      cppConsumer = ./thrift/consumer.cpp;
      originalTypes = ./fixtures/thrift-javascript-types;
      dlLibs = pkgs.lib.optionals (!pkgs.stdenv.hostPlatform.isDarwin) [ "-ldl" ];
    };
    passAsFile = [ "spec" ];
  }
  ''
    export HOME="$TMPDIR/home" npm_config_cache="$TMPDIR/npm-cache"
    mkdir -p "$HOME"
    python ${./thrift-javascript/consume.py} "$specPath" "$out"
  ''
