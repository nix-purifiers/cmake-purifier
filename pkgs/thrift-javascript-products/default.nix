# SPDX-License-Identifier: MIT
{
  lib,
  runCommand,
  python3,
  nodejs,
  esbuild,
  nix,
  thrift,
  purifier,
}:
{
  resources,
  thriftJavaScriptPackage,
  thriftJavaScriptRuntimeBuilder,
  thriftJavaScriptDependencies ? [ ],
  thriftJavaScriptBrowserBuilder ? null,
  thriftJavaScriptWebjar ? null,
}:
let
  options = thriftJavaScriptPackage;
  valid =
    builtins.isAttrs options
    &&
      builtins.attrNames options == [
        "entrypoints"
        "name"
        "version"
      ]
    && builtins.isString options.name
    && builtins.isString options.version
    && builtins.isAttrs options.entrypoints
    && options.entrypoints != { };
  sdk = thriftJavaScriptRuntimeBuilder {
    src = thrift.src;
    buildScripts = [ ];
    doCheck = false;
  };
  runtimeRepository =
    (purifier.npmProjections {
      producer = sdk.release;
      graph = "${sdk.release.graph}/graph.json";
      archives = "${sdk.release.graph}/archives";
      inherit runCommand python3;
    }).npm;
  runtime = sdk.release // {
    projections.npm = runtimeRepository;
  };
  selected = purifier.projectInputs {
    dependencies = thriftJavaScriptDependencies;
    formats = [ "npm" ];
  };
  browserSdk = thriftJavaScriptBrowserBuilder {
    src = thrift.src;
    projectDir = "lib/js";
    buildScripts = [ ];
    doCheck = false;
  };
  browserTooling = runCommand "thrift-native-browser-tooling" { nativeBuildInputs = [ nodejs ]; } ''
    export HOME="$TMPDIR/home" npm_config_cache="$TMPDIR/npm-cache"
    mkdir -p "$HOME" "$npm_config_cache/_cacache"
    cp -rs --no-preserve=mode ${browserSdk.cache}/. "$npm_config_cache/_cacache"
    cp -r ${browserSdk.release.src} source
    chmod -R u+w source
    cd source/lib/js
    npm ci --offline --ignore-scripts --no-audit --no-fund
    mkdir -p "$out"
    cp -r node_modules "$out/"
    cp package.json package-lock.json "$out/"
  '';
  generated =
    runCommand "thrift-generated-javascript-package"
      {
        nativeBuildInputs = [
          python3
          nodejs
          nix
          thrift
        ];
        spec = builtins.toJSON {
          resources = toString resources;
          sdk = toString thrift;
          sdkSource = toString thrift.src;
          captureTool = purifier.npmCaptureTool;
          runtimeGraph = "${sdk.release.graph}/graph.json";
          runtimeRepository = toString runtimeRepository;
          runtimeCatalog = runtimeRepository.catalog;
          extraInputs = map (input: {
            repository = toString input.repository;
            catalog = input.repository.catalog;
          }) selected;
          package = options;
          browserTooling = if thriftJavaScriptBrowserBuilder == null then null else toString browserTooling;
          browserBundler = "${esbuild}/bin/esbuild";
        };
        passAsFile = [ "spec" ];
        passthru = {
          sdkRuntime = runtime;
          schemaResources = resources;
        };
      }
      ''
        export HOME="$TMPDIR/home" npm_config_cache="$TMPDIR/npm-cache"
        export NPM_PURIFIER_NPM_MODULES=${nodejs}/lib/node_modules/npm/node_modules
        export NPM_PURIFIER_TARGET_NODE=${nodejs}/bin/node
        export NPM_PROJECTION_NIX=${nix}/bin/nix
        mkdir -p "$HOME"
        python ${./generate.py} "$specPath" "$out"
      '';
  repository =
    (purifier.npmProjections {
      producer = generated;
      graph = "${generated}/graph.json";
      archives = "${generated}/archives";
      dependencies = [ runtime ] ++ thriftJavaScriptDependencies;
      inherit runCommand python3;
    }).npm;
  web = lib.optionalAttrs (thriftJavaScriptBrowserBuilder != null) (
    purifier.resourceProjections {
      producer = generated;
      roots."." = "package/browser";
      inherit runCommand python3;
    }
  );
  webjar = lib.optionalAttrs (thriftJavaScriptWebjar != null) (
    purifier.webjarProjections (
      thriftJavaScriptWebjar
      // {
        producer = generated;
        assets = "${generated}/package/browser";
        inherit runCommand python3;
      }
    )
  );

in
assert
  valid
  || throw "cmake-purifier: thriftJavaScriptPackage requires name, version and explicit entrypoints";
assert
  builtins.isFunction thriftJavaScriptRuntimeBuilder
  || throw "cmake-purifier: Thrift JavaScript requires a released native npm SDK builder";
assert
  thriftJavaScriptBrowserBuilder == null
  || builtins.isFunction thriftJavaScriptBrowserBuilder
  || throw "cmake-purifier: Thrift browser output requires a released native npm SDK builder";
assert
  thriftJavaScriptWebjar == null
  || thriftJavaScriptBrowserBuilder != null
  || throw "cmake-purifier: Thrift WebJar requires browser outputs";
generated // { projections = web // webjar // { npm = repository; }; }
