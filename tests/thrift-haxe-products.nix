# SPDX-License-Identifier: MIT
{
  pkgs,
  purifier,
  build,
  haxelibPurifierSource,
}:
let
  runtimeBuilder = import ./thrift-haxe/runtime.nix { inherit pkgs purifier haxelibPurifierSource; };
  secondSource = pkgs.runCommand "thrift-haxe-native-field-two" { } ''
    cp -R ${./fixtures/thrift-cpp} "$out"
    chmod -R u+w "$out"
    substituteInPlace "$out/schemas/common/value.thrift" --replace-fail '1: i32 answer' '2: i32 answer'
  '';
  qualifiedSource = pkgs.runCommand "thrift-haxe-native-qualified" { } ''
    cp -R ${./fixtures/thrift-cpp} "$out"
    chmod -R u+w "$out"
    sed -i '1i namespace haxe schema.main' "$out/schemas/main.thrift"
    sed -i '1i namespace haxe schema.common' "$out/schemas/common/value.thrift"
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
      result = build (
        args
        // {
          thriftHaxePackage.manifest = ./thrift-haxe/haxelib.json;
          thriftHaxeRuntimeBuilder = runtimeBuilder;
        }
      );
    in
    assert raw.packages.thrift-schema.drvPath == result.packages.thrift-schema.drvPath;
    result.packages.thrift-haxe-bindings;
  first = make ./fixtures/thrift-cpp;
  second = make secondSource;
  qualified = make qualifiedSource;
  consume =
    product: wire: namespaced:
    let
      caller = pkgs.runCommand "ordinary-native-haxelib-consumer-source" { } ''
        mkdir "$out"
        cp ${./thrift-haxe/Main.hx} "$out/Main.hx"
        ${pkgs.lib.optionalString namespaced ''
          sed -i '1i import schema.main.Envelope; import schema.common.Value; import schema.main.AnswerService_service; import schema.main.AnswerServiceImpl; import schema.main.AnswerServiceProcessor;' "$out/Main.hx"
        ''}
      '';
    in
    pkgs.runCommand "ordinary-native-haxelib-consumer"
      {
        nativeBuildInputs = [
          product.tools.haxe
          product.tools.nativeHaxelib
          product.tools.neko
        ];
      }
      ''
        export HOME="$TMPDIR/home" HAXELIB_PATH=${product.projections.haxelib.repository}/
        export HAXELIB_PURIFIER_REPOSITORY=${product.projections.haxelib.repository} HAXELIB_PURIFIER_FROZEN=1
        export PATH=${product.tools.nativeHaxelib}/bin:$PATH
        mkdir -p "$HOME" "$out"
        haxe -v -cp ${caller} -lib example-thrift-types -main Main --neko "$out/consumer.n" --xml "$out/typed.xml" > "$out/compiler.stdout" 2> "$out/compiler.stderr"
        neko "$out/consumer.n" ${pkgs.lib.escapeShellArg wire} > "$out/result.json"
      '';
  a = consume first "0c00010800010000002a0000" false;
  b = consume second "0c00010800020000002a0000" false;
  c = consume qualified "0c00010800010000002a0000" true;
  resourceCase =
    command:
    (build {
      src = pkgs.runCommand "invalid-native-haxe-schema" { } ''
        cp -R ${./fixtures/thrift-cpp} "$out"
        chmod -R u+w "$out"
        ${command}
      '';
      lockFile = ./fixtures/thrift-cpp/cmake-purifier.lock.json;
      pname = "thrift-schema";
      version = "1.0.0";
      resourceRoots."." = "share/schemas";
      resourceSchema = {
        format = "thrift";
        entrypoints = [ "main.thrift" ];
      };
    }).projections.resources;
  sdkShadow = resourceCase ''printf '%s\n' 'namespace haxe org.apache.thrift.protocol' 'struct TBinaryProtocol {1:i32 answer}' > "$out/schemas/main.thrift"'';
  stdShadow = resourceCase ''printf '%s\n' 'namespace haxe haxe.io' 'struct BytesBuffer {1:i32 answer}' > "$out/schemas/main.thrift"'';
  collision = resourceCase ''
    printf '%s\n' 'include "common/value.thrift"' 'struct collision {1:value.Collision value}' > "$out/schemas/main.thrift"
    printf '%s\n' 'struct Collision {1:i32 answer}' > "$out/schemas/common/value.thrift"
  '';
  invalidSdk =
    kind:
    pkgs.runCommand "invalid-original-haxe-sdk-${kind}"
      {
        nativeBuildInputs = [ pkgs.python3 ];
      }
      ''
        python3 ${./thrift-haxe/invalid-sdk.py} ${first.runtime.producer} "$out" ${kind}
      '';
  runtimeCase =
    kind: diagnostic:
    let
      bad = invalidSdk kind;
    in
    {
      inherit diagnostic;
      request = (builtins.fromJSON (builtins.unsafeDiscardStringContext first.runtimeProof.spec)) // {
        sdkSource = toString first.sdk.src;
        source = toString first.runtime.source;
        producerIdentity = purifier.inputIdentity bad;
        producerOutputs = [ (toString bad) ];
        installedRoot = "${bad}/sdk-source";
        repository = "${bad}/repository";
      };
    };
  wrongManifest =
    pkgs.runCommand "invalid-caller-haxelib-sdk-requirement"
      {
        nativeBuildInputs = [ pkgs.python3 ];
      }
      ''
        python3 - ${./thrift-haxe/haxelib.json} "$out" <<'PY'
        import json,sys
        from pathlib import Path
        value=json.loads(Path(sys.argv[1]).read_text())
        value['dependencies']['thrift']='0.0.0'
        Path(sys.argv[2]).write_text(json.dumps(value))
        PY
      '';
in
pkgs.runCommand "thrift-haxe-native-package-consumers"
  {
    nativeBuildInputs = [ pkgs.python3 ];
    controls = builtins.toJSON {
      generator = ../pkgs/thrift-haxe-products/generate.py;
      installer = ../pkgs/thrift-haxe-products/install.py;
      runtimeVerifier = ../pkgs/thrift-haxe-products/runtime-proof.py;
      runtimeCases = [
        (runtimeCase "development" "original SDK requires its exact native versioned installation")
        (runtimeCase "bytes" "native Haxe SDK source files changed")
        (runtimeCase "graph" "native SDK dependency is missing or incompatible")
      ];
      generation = {
        sdk = toString first.sdk;
        runtimeProof = "${first.runtimeProof}/runtime.json";
        manifest = ./thrift-haxe/haxelib.json;
        inspect = "${first.tools.nativeHaxelib}/bin/haxelib-purifier-inspect";
      };
      installation = {
        runtimeProof = "${first.runtimeProof}/runtime.json";
        repository = toString first.runtime.repository;
        haxelib = "${first.tools.nativeHaxelib}/bin/haxelib";
        inspect = "${first.tools.nativeHaxelib}/bin/haxelib-purifier-inspect";
        haxe = "${first.tools.haxe}/bin/haxe";
        haxeRoot = toString first.tools.haxe;
      };
      cases = [
        {
          resources = toString sdkShadow;
          phase = "generate";
          diagnostic = "generated Haxe module shadows selected runtime";
        }
        {
          resources = toString stdShadow;
          phase = "install";
          diagnostic = "generated Haxe module shadows selected compiler SDK";
        }
        {
          resources = toString collision;
          phase = "generate";
          diagnostic = "native generated Haxe output collision";
        }
        {
          resources = toString first.schemaResources;
          manifest = toString wrongManifest;
          phase = "generate";
          expectHaxeOutput = false;
          diagnostic = "caller Haxelib manifest must retain the exact original SDK dependency";
        }
      ];
    };
    passAsFile = [ "controls" ];
    passthru = { inherit first second qualified; };
  }
  ''
    mkdir "$out"
    cp ${a}/result.json "$out/first.json"
    cp ${b}/result.json "$out/second.json"
    cp ${c}/result.json "$out/qualified.json"
    python3 ${./thrift-haxe/byte-joins.py} ${first.source} ${first.source.proof} ${first} ${first.proof} ${first.runtimeProof} ${a} > "$out/first-byte-joins.json"
    python3 ${./thrift-haxe/byte-joins.py} ${second.source} ${second.source.proof} ${second} ${second.proof} ${second.runtimeProof} ${b} > "$out/second-byte-joins.json"
    python3 ${./thrift-haxe/byte-joins.py} ${qualified.source} ${qualified.source.proof} ${qualified} ${qualified.proof} ${qualified.runtimeProof} ${c} > "$out/qualified-byte-joins.json"
    python3 ${./thrift-haxe/controls.py} "$controlsPath" "$out/rejections.json"
  ''
