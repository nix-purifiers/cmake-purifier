# SPDX-License-Identifier: MIT
{
  lib,
  runCommand,
  python3,
  nodejs,
  nix,
  thrift,
  purifier,
}:
{
  resources,
  thriftJavaScriptPackage,
  thriftJavaScriptRuntimeBuilder,
  thriftJavaScriptDependencies ? [ ],
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
in
assert
  valid
  || throw "cmake-purifier: thriftJavaScriptPackage requires name, version and explicit entrypoints";
assert
  builtins.isFunction thriftJavaScriptRuntimeBuilder
  || throw "cmake-purifier: Thrift JavaScript requires a released native npm SDK builder";
generated // { projections.npm = repository; }
