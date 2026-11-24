# SPDX-License-Identifier: MIT
{
  pkgs,
  purifier,
  build,
  pubProjectorSource,
}:
let
  pub = pkgs.callPackage (pubProjectorSource + "/pkgs/build-pub-project") { inherit purifier; };
  source2 = pkgs.runCommand "thrift-dart-native-field-two" { } ''
    cp -R ${./fixtures/thrift-cpp} "$out"
    chmod -R u+w "$out"
    substituteInPlace "$out/schemas/common/value.thrift" --replace-fail '1: i32 answer' '2: i32 answer'
  '';
  qualified = pkgs.runCommand "thrift-dart-native-qualified-packages" { } ''
    cp -R ${./fixtures/thrift-cpp} "$out"
    chmod -R u+w "$out"
    sed -i '1i namespace dart proof_main' "$out/schemas/main.thrift"
    sed -i '1i namespace dart proof_value' "$out/schemas/common/value.thrift"
  '';
  make =
    src: roots:
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
      result = build (args // { thriftDartPackage = { inherit roots; }; });
    in
    assert raw.packages.thrift-schema.drvPath == result.packages.thrift-schema.drvPath;
    result.packages.thrift-dart-bindings;
  first = make ./fixtures/thrift-cpp [
    "main"
    "value"
  ];
  second = make source2 [
    "main"
    "value"
  ];
  namespaced = make qualified [
    "proof_main"
    "proof_value"
  ];
  consume =
    product: wire: mainName: valueName:
    let
      consumer = pkgs.runCommand "ordinary-thrift-dart-consumer-source" { } ''
        mkdir -p "$out/bin"
        cp ${./thrift-dart/consume.dart} "$out/bin/consume.dart"
        ${pkgs.lib.optionalString (mainName != "main")
          ''substituteInPlace "$out/bin/consume.dart" --replace-fail 'package:main/main.dart' 'package:${mainName}/${mainName}.dart' ''
        }
        ${pkgs.lib.optionalString (valueName != "value")
          ''substituteInPlace "$out/bin/consume.dart" --replace-fail 'package:value/value.dart' 'package:${valueName}/${valueName}.dart' ''
        }
        cat > "$out/pubspec.yaml" <<'YAML'
        name: ordinary_consumer
        environment:
          sdk: '>=2.12.0 <4.0.0'
        dependencies:
          ${mainName}:
            path: ${product}/${mainName}
        YAML
      '';
    in
    (pub {
      src = consumer;
      pathSources = product.projections.pub.pathSources;
      lockFile = ./thrift-dart/pub-purifier.lock.json;
      pubLock = ./thrift-dart/pubspec.lock;
      testCommand = "dart run bin/consume.dart ${pkgs.lib.escapeShellArg wire}";
    }).tests;
  a = consume first "0c00010800010000002a0000" "main" "value";
  b = consume second "0c00010800020000002a0000" "main" "value";
  c = consume namespaced "0c00010800010000002a0000" "proof_main" "proof_value";
  resourceCase =
    command:
    (build {
      src = pkgs.runCommand "thrift-dart-invalid-package-schema" { } ''
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
  collision = resourceCase ''
    sed -i '1i namespace dart collision' "$out/schemas/main.thrift"
    sed -i '1i namespace dart collision' "$out/schemas/common/value.thrift"
  '';
  shadow = resourceCase ''sed -i '1i namespace dart thrift' "$out/schemas/main.thrift"'';
in
pkgs.runCommand "thrift-dart-native-pub-consumers"
  {
    nativeBuildInputs = [ (pkgs.python3.withPackages (ps: [ ps.pyyaml ])) ];
    controls = builtins.toJSON {
      generator = ../pkgs/thrift-dart-products/generate.py;
      generation = {
        sdk = toString first.sdk;
        sdkSource = toString first.sdkSource;
      };
      cases = [
        {
          resources = toString first.schemaResources;
          roots = [ "main" ];
          diagnostic = "declared Dart package roots differ";
        }
        {
          resources = toString collision;
          roots = [ "collision" ];
          diagnostic = "native generated Dart output collision";
        }
        {
          resources = toString shadow;
          roots = [
            "thrift"
            "value"
          ];
          diagnostic = "generated Dart package shadows the original SDK root";
        }
      ];
    };
    passAsFile = [ "controls" ];
    passthru = { inherit first second namespaced; };
  }
  ''
    mkdir -p "$out"
    cp ${a} "$out/first-materialization.json"
    cp ${b} "$out/second-materialization.json"
    cp ${c} "$out/qualified-materialization.json"
    python3 ${./thrift-dart/byte-joins.py} ${first} ${first.proof} ${a} > "$out/first-byte-joins.json"
    python3 ${./thrift-dart/byte-joins.py} ${second} ${second.proof} ${b} > "$out/second-byte-joins.json"
    python3 ${./thrift-dart/byte-joins.py} ${namespaced} ${namespaced.proof} ${c} > "$out/qualified-byte-joins.json"
    python3 ${./thrift-dart/controls.py} "$controlsPath" "$out/rejections.json"
  ''
