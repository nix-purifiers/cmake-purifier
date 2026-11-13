{ pkgs, build }:
let
  source1 = pkgs.runCommand "flatbuffers-java-qualified-types" { } ''
    cp -r ${./fixtures/flatbuffers-schema} $out
    chmod -R u+w $out
    echo 'namespace a; table Value { answer:int; }' > "$out/schemas/a.fbs"
    echo 'namespace b; table Value { answer:int; }' > "$out/schemas/b.fbs"
    substituteInPlace "$out/schemas/main.fbs" --replace-fail 'namespace proof;' 'include "a.fbs"; include "b.fbs"; namespace proof;'
  '';
  source2 = pkgs.runCommand "flatbuffers-java-long" { } ''
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
          entrypoints = [ "main.fbs" ];
        };
      };
      raw = build args;
      built = build (
        args
        // {
          flatbuffersPackage = {
            name = "schema_proof";
            version = "1.0.0";
          };
          flatbuffersJavaPackage = {
            groupId = "org.example.schemas";
            artifactId = "answer";
            version = "1.0.0";
          };
          flatbuffersJavaRuntimeBuilder =
            args:
            pkgs.maven.buildMavenPackage (
              args
              // {
                mvnHash = "sha256-ozeLSzB7hICLqqACKJCgLCCgEgD58G26EvdX8BZc/vE=";
              }
            );
        }
      );
      package = built.packages.flatbuffers-java-bindings;
    in
    assert raw.packages.schema-bundle.drvPath == built.packages.schema-bundle.drvPath;
    {
      inherit bits;
      package = toString package;
      runtime = toString package.sdkRuntime;
      maven = toString package.projections.maven;
      catalog = package.projections.maven.catalog;
      cpp = toString built.packages.flatbuffers-bindings;
    };
  reject =
    options:
    !(builtins.tryEval
      (build {
        src = ./fixtures/flatbuffers-schema;
        flatbuffersJavaPackage = options;
      }).packages.schema-bundle.drvPath
    ).success;
  missingBuilder =
    !(builtins.tryEval
      (build {
        src = ./fixtures/flatbuffers-schema;
        resourceRoots."." = "share/schemas";
        resourceSchema = {
          format = "flatbuffers";
          entrypoints = [ "main.fbs" ];
        };
        flatbuffersJavaPackage = {
          groupId = "org.example";
          artifactId = "answer";
          version = "1.0.0";
        };
      }).packages.flatbuffers-java-bindings.drvPath
    ).success;
in
assert reject {
  groupId = "org.example";
  artifactId = "answer";
  version = "1.0.0";
};
assert missingBuilder;
pkgs.runCommand "flatbuffers-java-native-consumers"
  ({
    nativeBuildInputs = [
      pkgs.python3
      pkgs.jdk
      pkgs.gradle
      pkgs.stdenv.cc
      pkgs.pkg-config
    ];
    buildInputs = [ pkgs.flatbuffers ];
    spec = builtins.toJSON {
      versions = [
        (make source1 32)
        (make source2 64)
      ];
      consumer = "${./flatbuffers-java}/Consumer.java";
      generator = ../pkgs/flatbuffers-java-products/generate.py;
      publisherSource = "${../pkgs/flatbuffers-java-products}/Publish.java";
      cppConsumer = ./flatbuffers-python/consumer.cpp;
    };
    passAsFile = [ "spec" ];
  } // pkgs.lib.optionalAttrs pkgs.stdenv.buildPlatform.isDarwin {
    __darwinAllowLocalNetworking = true;
  })
  ''
    export HOME="$TMPDIR/home" GRADLE_USER_HOME="$TMPDIR/gradle-home"
    mkdir -p "$HOME"
    python ${./flatbuffers-java/consume.py} "$specPath" "$out"
  ''
