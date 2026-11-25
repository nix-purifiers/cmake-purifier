# SPDX-License-Identifier: MIT
# Captured original Thrift SDK Composer metadata; the build checks it against
# the selected SDK and installs the entire native locked graph offline.
{
  pkgs,
  purifier,
  composerPurifierSource,
}:
let
  cacheProject =
    (pkgs.callPackage (composerPurifierSource + "/pkgs/build-composer-project/default.nix") {
      inherit purifier;
    })
      {
        src = ./sdk;
        dev = true;
      };
  # PHP 8.5 provides XML in the interpreter itself. Loading the shared XML
  # extension too emits startup warnings into native metadata output.
  php = cacheProject.php.withExtensions (
    { enabled, ... }:
    builtins.filter (extension: extension.extensionName != "xml") enabled
  );
  composer = pkgs.php.packages.composer;
  lock = ./sdk/composer.lock;
  manifest = builtins.fromJSON (builtins.readFile ./sdk/composer.json);
  locked = builtins.fromJSON (builtins.readFile lock);
  platformRequirements = pkgs.lib.unique (
    builtins.filter
      (name: name == "php" || pkgs.lib.hasPrefix "ext-" name || pkgs.lib.hasPrefix "composer-" name)
      (
        builtins.attrNames (manifest.require or { })
        ++ builtins.attrNames (manifest.require-dev or { })
        ++ pkgs.lib.concatMap (package: builtins.attrNames (package.require or { })) (
          locked.packages ++ locked.packages-dev
        )
      )
  );
  origins = pkgs.lib.listToAttrs (
    map (
      package:
      pkgs.lib.nameValuePair package.name
        (purifier.inputIdentity (
          cacheProject.cache.fetch cacheProject.cache.entries.byName.${package.name}
        )).hash
    ) (locked.packages ++ locked.packages-dev)
  );
  build =
    {
      thrift,
      php,
      composer,
    }:
    let
      source = thrift.src;
      request = {
        src = source;
        composerLock = lock;
        sourceIdentity = (purifier.inputIdentity source).hash;
        php = "${php}/bin/php";
        nativePhp = "${php}/bin/php";
        nativeComposerSource = toString composer.src;
        nativeComposerVersion = composer.version;
        autoload = "${composer}/share/php/composer/vendor/autoload.php";
        nativeVersionInput = thrift.version;
        runtimeIdentity = {
          php = toString php;
          composer = toString composer;
          capturePhp = toString php;
          captureComposer = toString composer;
        };
        dependencies = [ ];
        originPaths = { };
        pathRepositories = { };
      };
      installed =
        pkgs.runCommand "thrift-native-php-sdk-ci"
          {
            outputs = [
              "out"
              "proof"
            ];
            nativeBuildInputs = [
              php
              composer
              pkgs.python3
              pkgs.unzip
              pkgs.git
            ];
            requestJSON = builtins.toJSON request;
            passAsFile = [ "requestJSON" ];
          }
          ''
            export HOME="$TMPDIR/home" COMPOSER_HOME="$TMPDIR/composer-home"
            export COMPOSER_CACHE_DIR=${cacheProject.cache} COMPOSER_CACHE_READ_ONLY=1 COMPOSER_DISABLE_NETWORK=1 COMPOSER_POLICY=0 COMPOSER_HTACCESS_PROTECT=0
            export COMPOSER_ROOT_VERSION=${pkgs.lib.escapeShellArg thrift.version}
            mkdir -p "$HOME" "$COMPOSER_HOME" "$out" "$proof"
            cmp ${./sdk/composer.json} ${source}/composer.json
            cp -R ${source}/. "$out/"
            chmod -R u+w "$out"
            cp ${lock} "$out/composer.lock"
            cd "$out"
            python3 - "$proof/native-install-env.json" <<'PY'
            import json,os,sys
            from pathlib import Path
            Path(sys.argv[1]).write_text(json.dumps({'format':'composer-purifier-native-install-env-v1','values':{k:os.environ.get(k) for k in ['COMPOSER_ROOT_VERSION','COMPOSER_HOME','COMPOSER_CACHE_DIR','HOME','COMPOSER']}},sort_keys=True))
            PY
            nativeEnvHash="$(python3 -c 'import hashlib,sys;from pathlib import Path;print(hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest())' "$proof/native-install-env.json")"
            composer install --prefer-dist --no-interaction --no-progress
            python3 ${composerPurifierSource}/tools/composer_root.py "$requestJSONPath" "$proof/root-context.json" "$out" "$proof/native-install-env.json" "$nativeEnvHash"
            cmp composer.json ${source}/composer.json
            cmp composer.lock ${lock}
          '';
      projection =
        import (composerPurifierSource + "/pkgs/build-composer-project/composer-projections.nix")
          {
            inherit (pkgs) lib runCommand python3;
            inherit
              purifier
              php
              composer
              installed
              origins
              platformRequirements
              ;
            src = source;
            capturePhp = php;
            captureComposer = composer;
            composerLock = lock;
            dependencies = [ ];
            rootContext = "${installed.proof}/root-context.json";
          };
    in
    {
      producer = installed.overrideAttrs (old: {
        passthru = (old.passthru or { }) // {
          projections.composer = projection;
        };
      });
      inherit source;
      installedRoot = toString installed;
    };
in
{
  inherit php composer build;
}
