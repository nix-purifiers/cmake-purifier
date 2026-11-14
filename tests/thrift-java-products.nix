{
  pkgs,
  build,
  projector,
}:
let
  wrapper = import ./thrift-java-wrapper.nix { inherit pkgs; };
  source1 = pkgs.runCommand "thrift-java-namespaces" { } ''
    cp -r ${./fixtures/thrift-cpp} $out
    chmod -R u+w $out
    echo 'namespace java proof.a
    namespace cpp a
    struct Value {1: i32 answer}' > "$out/schemas/a.thrift"
    echo 'namespace java proof.b
    namespace cpp b
    struct Value {1: i32 answer}' > "$out/schemas/b.thrift"
    substituteInPlace $out/schemas/main.thrift --replace-fail 'include "common/value.thrift"' 'include "common/value.thrift"
    include "a.thrift"
    include "b.thrift"'
    substituteInPlace $out/schemas/main.thrift --replace-fail 'namespace py main_value' 'namespace py main_value
    namespace java proof.main'
    substituteInPlace $out/schemas/common/value.thrift --replace-fail 'namespace py common_value' 'namespace py common_value
    namespace java proof.common'
  '';
  source2 = pkgs.runCommand "thrift-java-second-field" { } ''
    cp -r ${source1} $out
    chmod -R u+w $out
    substituteInPlace $out/schemas/common/value.thrift --replace-fail '1: i32 answer' '2: i32 answer'
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
      built = build (
        args
        // {
          thriftPackage = {
            name = "thrift_proof";
            version = "1.0.0";
          };
          thriftJavaPackage = {
            groupId = "org.example.schemas";
            artifactId = "answer";
            version = "1.0.0";
          };
          thriftJavaRuntimeLock = ./thrift-java-runtime.gradle-purifier.lock.json;
          thriftJavaRuntimeWrapper = wrapper;
          thriftJavaRuntimeBuilder = projector;

        }
      );
      package = built.packages.thrift-java-bindings;
    in
    assert raw.packages.thrift-schema.drvPath == built.packages.thrift-schema.drvPath;
    {
      package = toString package;
      runtimeCatalog = package.sdkRuntime.projections.maven.catalog;
      repository = toString built.projections.maven;
      catalog = built.projections.maven.catalog;
      ivy = toString built.projections.ivy;
      cpp = toString built.packages.thrift-bindings;
    };
  reject =
    !(builtins.tryEval
      (build {
        src = ./fixtures/thrift-cpp;
        thriftJavaPackage = {
          groupId = "org.example";
          artifactId = "answer";
          version = "1.0.0";
        };
      }).packages.thrift-schema.drvPath
    ).success;
  missingProjector =
    !(builtins.tryEval
      (build {
        src = ./fixtures/thrift-cpp;
        resourceRoots."." = "share/schemas";
        resourceSchema = {
          format = "thrift";
          entrypoints = [ "main.thrift" ];
        };
        thriftJavaPackage = {
          groupId = "org.example";
          artifactId = "answer";
          version = "1.0.0";
        };
      }).packages.thrift-java-bindings.drvPath
    ).success;
in
assert reject;
assert missingProjector;
pkgs.runCommand "thrift-java-native-consumers"
  (
    {
      nativeBuildInputs = [
        pkgs.gradle
        pkgs.jdk
        pkgs.python3
        pkgs.stdenv.cc
        pkgs.pkg-config
      ];
      buildInputs = [ pkgs.thrift ];
      spec = builtins.toJSON {
        versions = [
          (make source1)
          (make source2)
        ];
        consumer = "${./thrift-java}/Consumer.java";
        generator = ../pkgs/thrift-java-products/generate.py;
        runtimeCatalog = (make source1).runtimeCatalog;
        cppConsumer = ./thrift/consumer.cpp;
        dlLibs = pkgs.lib.optionals (!pkgs.stdenv.buildPlatform.isDarwin) [ "-ldl" ];
      };
      passAsFile = [ "spec" ];
    }
    // pkgs.lib.optionalAttrs pkgs.stdenv.buildPlatform.isDarwin {
      __darwinAllowLocalNetworking = true;
      # Java's dual-stack sockets keep Gradle from connecting to its daemon
      # inside the Darwin sandbox.
      env.JAVA_TOOL_OPTIONS = "-Djava.net.preferIPv4Stack=true";
    }
  )
  ''
    python ${./thrift-java/consume.py} "$specPath" "$out"
  ''
