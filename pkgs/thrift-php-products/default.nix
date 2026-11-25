# SPDX-License-Identifier: MIT
{
  lib,
  runCommand,
  python3,
  php,
  thrift,
  purifier,
  composerPurifierSource,
  git,
  unzip,
}:
{
  resources,
  thriftPhpPackage,
  thriftPhpRuntimeBuilder,
  applicationPhp ? php,
}:
let
  options = thriftPhpPackage;
  valid =
    builtins.isAttrs options
    &&
      builtins.attrNames options == [
        "name"
        "version"
      ]
    && builtins.isString options.name
    && builtins.match "[a-z0-9_.-]+/[a-z0-9_.-]+" options.name != null
    && builtins.isString options.version
    && options.version != "";
  composer = php.packages.composer;
  runtime = thriftPhpRuntimeBuilder {
    inherit thrift composer;
    php = applicationPhp;
  };
  selected = purifier.projectInputs {
    dependencies = [ runtime.producer ];
    formats = [ "composer" ];
  };
  runtimeProof =
    runCommand "thrift-native-php-runtime-proof"
      {
        nativeBuildInputs = [
          python3
          applicationPhp
        ];
        spec = builtins.toJSON {
          sdk = toString thrift;
          sdkSource = toString thrift.src;
          producer = toString runtime.producer;
          source = toString runtime.source;
          installedRoot = toString runtime.installedRoot;
          php = "${applicationPhp}/bin/php";
          composer = toString composer;
          requirementsTool = ./runtime-requirements.php;
        };
        passAsFile = [ "spec" ];
      }
      ''
        mkdir "$out"
        ${python3}/bin/python3 ${./runtime-proof.py} "$specPath" "$out/runtime.json"
      '';
  source =
    runCommand "thrift-generated-php-source"
      {
        nativeBuildInputs = [
          python3
          applicationPhp
        ];
        outputs = [
          "out"
          "proof"
        ];
        spec = builtins.toJSON {
          resources = toString resources;
          sdk = toString thrift;
          php = "${applicationPhp}/bin/php";
          composerAutoload = "${composer}/share/php/composer/vendor/autoload.php";
          runtime = toString runtime.installedRoot;
          runtimeProof = "${runtimeProof}/runtime.json";
          classesTool = ./classes.php;
          inherit (options) name version;
        };
        passAsFile = [ "spec" ];
      }
      ''
        ${python3}/bin/python3 ${./generate.py} "$specPath" "$out" "$proof"
      '';
  dependencies = map (input: {
    repository = toString input.repository;
    catalog = input.repository.catalog;
  }) selected;
  request = {
    sourceIdentity = (purifier.inputIdentity source).hash;
    php = "${applicationPhp}/bin/php";
    nativePhp = "${applicationPhp}/bin/php";
    nativeComposerSource = toString composer.src;
    nativeComposerVersion = composer.version;
    autoload = "${composer}/share/php/composer/vendor/autoload.php";
    tools = "${composerPurifierSource}/tools";
    nativeVersionInput = options.version;
    runtimeIdentity = {
      php = toString applicationPhp;
      composer = toString composer;
      capturePhp = toString applicationPhp;
      captureComposer = toString composer;
    };
    inherit dependencies;
    originPaths = { };
    pathRepositories = { };
  };
  installed =
    runCommand "thrift-generated-php-library"
      {
        outputs = [
          "out"
          "proof"
        ];
        nativeBuildInputs = [
          applicationPhp
          composer
          python3
          git
          unzip
        ];
        requestJSON = builtins.toJSON request;
        passAsFile = [ "requestJSON" ];
      }
      ''
        export HOME="$TMPDIR/home" COMPOSER_HOME="$TMPDIR/composer-home"
        export COMPOSER_CACHE_DIR="$TMPDIR/cache" COMPOSER_DISABLE_NETWORK=1 COMPOSER_POLICY=0 COMPOSER_ROOT_VERSION=${lib.escapeShellArg options.version}
        mkdir -p "$HOME" "$COMPOSER_HOME" "$COMPOSER_CACHE_DIR" "$out" "$proof"
        ${python3}/bin/python3 ${./install.py} "$requestJSONPath" ${source} "$out" "$proof"
      '';
  projection =
    import (composerPurifierSource + "/pkgs/build-composer-project/composer-projections.nix")
      {
        inherit
          lib
          purifier
          runCommand
          python3
          composer
          installed
          ;
        src = source;
        php = applicationPhp;
        capturePhp = applicationPhp;
        captureComposer = composer;
        composerLock = "${installed.proof}/native-composer.lock";
        origins = { };
        dependencies = [ runtime.producer ];
        platformRequirements = lib.concatMap (input: input.repository.platformRequirements or [ ]) selected;
        rootContext = "${installed.proof}/root-context.json";
      };
in
assert lib.assertMsg valid
  "thriftPhpPackage requires an explicit Composer package name and version";
assert lib.assertMsg (builtins.isFunction thriftPhpRuntimeBuilder)
  "thriftPhpRuntimeBuilder must build the complete original SDK Composer root";
assert lib.assertMsg (lib.isDerivation runtime.producer)
  "Thrift PHP runtime must retain its original Nix producer";
installed
// {
  projections.composer = projection;
  inherit source runtime runtimeProof;
  php = applicationPhp;
  sdk = thrift;
  schemaResources = resources;
}
