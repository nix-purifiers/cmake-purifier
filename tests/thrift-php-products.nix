# SPDX-License-Identifier: MIT
{
  pkgs,
  purifier,
  build,
  composerPurifierSource,
}:
let
  sdk = import ./thrift-php/runtime.nix { inherit pkgs purifier composerPurifierSource; };
  source2 = pkgs.runCommand "thrift-php-native-idl-v2" { } ''
    cp -R ${./fixtures/thrift-cpp} "$out"
    chmod -R u+w "$out"
    substituteInPlace "$out/schemas/common/value.thrift" --replace-fail '1: i32 answer' '2: i32 answer'
  '';
  qualified = pkgs.runCommand "thrift-php-native-qualified-idl" { } ''
    cp -R ${./fixtures/thrift-cpp} "$out"
    chmod -R u+w "$out"
    sed -i '1i namespace php Proof.Main' "$out/schemas/main.thrift"
    sed -i '1i namespace php Proof.Common' "$out/schemas/common/value.thrift"
  '';
  make =
    src: version:
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
      result = build (
        args
        // {
          thriftPhpPackage = {
            name = "example/native-thrift-php";
            inherit version;
          };
          thriftPhpRuntime = sdk.php;
          thriftPhpRuntimeBuilder = sdk.build;
        }
      );
    in
    assert raw.packages.thrift-schema.drvPath == result.packages.thrift-schema.drvPath;
    result.packages.thrift-php-bindings;
  first = make ./fixtures/thrift-cpp "1.0.0";
  second = make source2 "2.0.0";
  namespaced = make qualified "1.0.0";
  consume =
    product: script: wire:
    pkgs.runCommand "thrift-php-native-composer-consumer"
      {
        nativeBuildInputs = [
          sdk.php
          sdk.composer
          pkgs.python3
          pkgs.unzip
        ];
      }
      ''
        export HOME="$TMPDIR/home" COMPOSER_HOME="$TMPDIR/composer-home" COMPOSER_CACHE_DIR="$TMPDIR/cache"
        export COMPOSER_DISABLE_NETWORK=1 COMPOSER_POLICY=0 COMPOSER_ROOT_VERSION=1.0.0
        mkdir -p "$HOME" "$COMPOSER_HOME" "$COMPOSER_CACHE_DIR" "$out/project" "$out/proof"
        python3 - ${product.projections.composer.catalog} ${product.projections.composer} "$out/project/composer.json" <<'PY'
        import json,sys
        from pathlib import Path
        catalog=json.loads(Path(sys.argv[1]).read_text());root=catalog['roots'][0]
        assert root['name']=='example/native-thrift-php'
        Path(sys.argv[3]).write_text(json.dumps({'name':'example/ordinary-consumer','version':'1.0.0','require':{root['name']:'='+root['version']},'repositories':{'native':{'type':'artifact','url':sys.argv[2]},'packagist.org':False},'config':{'allow-plugins':{'php-http/discovery':True}}},indent=2)+'\n')
        PY
        cd "$out/project"
        composer update --no-interaction --no-progress --no-audit
        python3 ${./thrift-php/byte-joins.py} ${product.source} ${product.source.proof} ${product.runtime.source} ${product.runtimeProof}/runtime.json ${product.projections.composer} ${product.projections.composer.catalog} "$out/project" > "$out/proof/byte-joins.json"
        ${sdk.php}/bin/php ${script} "$out/project" ${pkgs.lib.escapeShellArg wire} > "$out/proof/consumer.json"
      '';
  a = consume first ./thrift-php/consume.php "0c00010800010000002a0000";
  b = consume second ./thrift-php/consume.php "0c00010800020000002a0000";
  c = consume namespaced ./thrift-php/consume-qualified.php "0c00010800010000002a0000";
  rejected =
    pkgs.runCommand "thrift-php-native-runtime-rejections"
      {
        nativeBuildInputs = [ pkgs.python3 ];
        request = builtins.toJSON {
          runtime = {
            sdk = toString first.sdk;
            sdkSource = toString first.sdk.src;
            producer = toString first.runtime.producer;
            source = toString first.runtime.source;
            installedRoot = toString first.runtime.installedRoot;
            php = "${sdk.php}/bin/php";
            composer = toString sdk.composer;
            requirementsTool = ../pkgs/thrift-php-products/runtime-requirements.php;
          };
          proof = "${first.runtimeProof}/runtime.json";
          verifier = ../pkgs/thrift-php-products/runtime-proof.py;
          classes = ../pkgs/thrift-php-products/classes.php;
          autoload = "${sdk.composer}/share/php/composer/vendor/autoload.php";
        };
        passAsFile = [ "request" ];
      }
      ''
        python3 ${./thrift-php/reject-invalid-runtime.py} "$requestPath" "$out"
      '';
in
pkgs.runCommand "thrift-php-native-product-consumers" { } ''
  mkdir -p "$out"
  cp ${a}/proof/consumer.json "$out/first.json"
  cp ${b}/proof/consumer.json "$out/second.json"
  cp ${c}/proof/consumer.json "$out/qualified.json"
  cp ${a}/proof/byte-joins.json "$out/first-byte-joins.json"
  cp ${b}/proof/byte-joins.json "$out/second-byte-joins.json"
  cp ${c}/proof/byte-joins.json "$out/qualified-byte-joins.json"
  cp ${rejected} "$out/rejections.json"
''
