{
  pkgs,
  build,
}:
let
  source1 = pkgs.runCommand "flatbuffers-typescript-qualified-types" { } ''
    cp -r ${./fixtures/flatbuffers-schema} $out
    chmod -R u+w $out
    echo 'namespace proof; table Packet { answer:int; } root_type Packet; file_identifier "EXT1";' > "$out/schemas/other.fbs"
    echo 'namespace a; table Value { answer:int; }' > "$out/schemas/a.fbs"
    echo 'namespace b; table Value { answer:int; }' > "$out/schemas/b.fbs"
    substituteInPlace "$out/schemas/main.fbs" --replace-fail 'namespace proof;' 'include "a.fbs"; include "b.fbs"; namespace proof;'
  '';
  source2 = pkgs.runCommand "flatbuffers-typescript-long" { } ''
    cp -r ${source1} $out
    chmod -R u+w $out
    substituteInPlace $out/schemas/common/value.fbs --replace-fail 'answer:int' 'answer:long'
  '';
  make =
    src: bits:
    let
      args = {
        inherit src;
        lockFile = ./fixtures/flatbuffers-schema/cmake-purifier.lock.json;
        pname = "schema-bundle";
        version = "1.0.0";
        resourceRoots."." = "share/schemas";
        resourceSchema = {
          format = "flatbuffers";
          entrypoints = [
            "main.fbs"
            "other.fbs"
          ];
        };
      };
      raw = build args;
      bindings = (
        args
        // {
          flatbuffersPackage = {
            name = "schema_proof";
            version = "1.0.0";
          };
          flatbuffersTypeScriptPackage = {
            name = "proof-schemas";
            version = "1.0.0";
            entrypoints = {
              "." = "main.fbs";
              "./extra" = "other.fbs";
            };
          };
          flatbuffersTypeScriptWebjar = {
            artifactId = "proof-schemas";
            version = "1.0.0";
          };
          flatbuffersTypeScriptVendorBuilder =
            args:
            pkgs.fetchPnpmDeps (args // { hash = "sha256-ssFTdn16Kx9zuACw8lH8Vb8h5j50SGF6WJDAxRsNEBc="; });

        }
      );
      built = build bindings;
      combined = build (
        bindings
        // {
          flatbuffersJavaPackage = {
            groupId = "org.example.schemas";
            artifactId = "answer";
            version = "1.0.0";
          };
          flatbuffersJavaRuntimeBuilder =
            args:
            pkgs.maven.buildMavenPackage (
              args // { mvnHash = "sha256-ozeLSzB7hICLqqACKJCgLCCgEgD58G26EvdX8BZc/vE="; }
            );
        }
      );
      package = built.packages.flatbuffers-typescript-bindings;
    in
    assert raw.packages.schema-bundle.drvPath == built.packages.schema-bundle.drvPath;
    {
      inherit bits;
      generated = toString package;
      repository = toString package.projections.npm;
      catalog = package.projections.npm.catalog;
      web = package.projections.web.documentRoot;
      javaResources = package.projections.java-resources.classPath;
      maven = toString built.projections.maven;
      combinedMaven = if bits == 32 then toString combined.projections.maven else null;
      ivy = toString built.projections.ivy;
      runtimeCatalog = package.sdkRuntime.projections.npm.catalog;
      cpp = toString built.packages.flatbuffers-bindings;
    };
in
pkgs.runCommand "flatbuffers-typescript-native-consumers"
  (
    {
      nativeBuildInputs = [
        pkgs.python3
        pkgs.nodejs
        pkgs.jdk
        pkgs.gradle
        pkgs.stdenv.cc
        pkgs.pkg-config
      ]
      ++ pkgs.lib.optional pkgs.stdenv.hostPlatform.isLinux pkgs.chromium;
      buildInputs = [ pkgs.flatbuffers ];
      spec = builtins.toJSON {
        javaConsumer = "${./flatbuffers-typescript}/ResourceConsumer.java";
        chromium = if pkgs.stdenv.hostPlatform.isLinux then "${pkgs.chromium}/bin/chromium" else null;
        versions = [
          (make source1 32)
          (make source2 64)
        ];
        consumer = ./flatbuffers-typescript/consumer.js;
        generator = ../pkgs/flatbuffers-typescript-products/generate.py;
        cppConsumer = ./flatbuffers-python/consumer.cpp;
      };
      passAsFile = [ "spec" ];
    }
    // pkgs.lib.optionalAttrs pkgs.stdenv.buildPlatform.isDarwin {
      __darwinAllowLocalNetworking = true;
    }
  )
  ''
    export HOME="$TMPDIR/home"
    mkdir -p "$HOME"
    python ${./flatbuffers-typescript/consume.py} "$specPath" "$out"
  ''
