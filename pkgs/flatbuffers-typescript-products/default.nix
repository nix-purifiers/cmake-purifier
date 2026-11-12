# SPDX-License-Identifier: MIT
{
  lib,
  stdenvNoCC,
  runCommand,
  python3,
  nodejs,
  pnpm_10,
  pnpmConfigHook,
  flatbuffers,
  purifier,
}:
{
  resources,
  flatbuffersTypeScriptPackage,
  flatbuffersTypeScriptVendorBuilder,
  flatbuffersTypeScriptWebjar ? null,
}:
let
  options = flatbuffersTypeScriptPackage;
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
  runtime = stdenvNoCC.mkDerivation {
    pname = "flatbuffers-native-typescript-runtime";
    version = lib.getVersion flatbuffers;
    src = flatbuffers.src;
    pnpmDeps = flatbuffersTypeScriptVendorBuilder {
      pname = "flatbuffers-native-typescript-runtime";
      version = lib.getVersion flatbuffers;
      src = flatbuffers.src;
      pnpm = pnpm_10;
      fetcherVersion = 5;
    };
    nativeBuildInputs = [
      nodejs
      pnpm_10
      pnpmConfigHook
      python3
    ];
    buildPhase = ''
      runHook preBuild
      pnpm run compile
      runHook postBuild
    '';
    installPhase = ''
      runHook preInstall
      mkdir -p "$out/archives" "$out/sdk"
      npm pack --ignore-scripts --json --pack-destination "$out/archives" > "$out/npm-pack.json"
      cp -r package.json pnpm-lock.yaml tsconfig.json tsconfig.mjs.json ts js mjs node_modules "$out/sdk/"
      python ${./runtime.py} "$out"
      node --version > "$out/node-version.txt"
      node node_modules/typescript/bin/tsc --version > "$out/typescript-version.txt"
      runHook postInstall
    '';
  };
  runtimeRepository =
    (purifier.npmProjections {
      producer = runtime;
      graph = "${runtime}/graph.json";
      archives = "${runtime}/archives";
      inherit runCommand python3;
    }).npm;
  provider = runtime // {
    projections.npm = runtimeRepository;
  };
  generated =
    runCommand "flatbuffers-generated-typescript-package"
      {
        nativeBuildInputs = [
          python3
          nodejs
          flatbuffers
        ];
        spec = builtins.toJSON {
          resources = toString resources;
          sdk = toString flatbuffers;
          sdkSource = toString flatbuffers.src;
          runtime = toString runtime;
          runtimeRepository = toString runtimeRepository;
          runtimeCatalog = runtimeRepository.catalog;
          package = options;
        };
        passAsFile = [ "spec" ];
        passthru = {
          sdkRuntime = provider;
          schemaResources = resources;
        };
      }
      ''
        export HOME="$TMPDIR/home" npm_config_cache="$TMPDIR/npm-cache"
        mkdir -p "$HOME"
        python ${./generate.py} "$specPath" "$out"
      '';
  repository =
    (purifier.npmProjections {
      producer = generated;
      graph = "${generated}/graph.json";
      archives = "${generated}/archives";
      dependencies = [ provider ];
      inherit runCommand python3;
    }).npm;
  web = purifier.resourceProjections {
    producer = generated;
    roots."." = "package/browser";
    inherit runCommand python3;
  };
  webjar = lib.optionalAttrs (flatbuffersTypeScriptWebjar != null) (
    purifier.webjarProjections (
      flatbuffersTypeScriptWebjar
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
  || throw "cmake-purifier: flatbuffersTypeScriptPackage requires name, version and explicit entrypoints";
assert
  builtins.isFunction flatbuffersTypeScriptVendorBuilder
  || throw "cmake-purifier: FlatBuffers TypeScript requires a captured native SDK dependency builder";
generated // { projections = web // webjar // { npm = repository; }; }
