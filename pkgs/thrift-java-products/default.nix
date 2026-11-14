# SPDX-License-Identifier: MIT
{
  callPackage,
  lib,
  runCommand,
  stdenv,
  python3,
  jdk,
  gradle,
  thrift,
  purifier,
}:
{
  resources,
  thriftJavaPackage,
  thriftJavaRuntimeLock,
  thriftJavaRuntimeWrapper,
  thriftJavaRuntimeBuilder,
}:
let
  options = thriftJavaPackage;
  valid =
    builtins.isAttrs options
    &&
      builtins.attrNames options == [
        "artifactId"
        "groupId"
        "version"
      ]
    && builtins.all builtins.isString [
      options.groupId
      options.artifactId
      options.version
    ];
  model = builtins.fromJSON (builtins.readFile thriftJavaRuntimeLock);
  rootProject = builtins.filter (project: project.path == ":") model.projects;
  publication =
    if
      builtins.length rootProject == 1 && builtins.length (builtins.head rootProject).publications == 1
    then
      builtins.head (builtins.head rootProject).publications
    else
      throw "cmake-purifier: SDK runtime needs one native root Maven publication";
  prepared = runCommand "thrift-java-sdk-source" {
    nativeBuildInputs = [ python3 ];
    spec = builtins.toJSON {
      sdkSource = toString thrift.src;
      wrapper = toString thriftJavaRuntimeWrapper;
    };
    passAsFile = [ "spec" ];
  } ''python ${./prepare.py} "$specPath" "$out"'';
  project = thriftJavaRuntimeBuilder {
    src = prepared;
    lockFile = thriftJavaRuntimeLock;
  };
  # The SDK's own build refers to ../../LICENSE, NOTICE and test schemas.
  # Keep that native layout rather than flattening lib/java into a new root.
  runtime = project.packages.${model.rootProjectName}.overrideAttrs (
    old:
    {
      sourceRoot = "${prepared.name}/lib/java";
      nativeIvyConverter = ../maven-ivy-products;
    }
    // lib.optionalAttrs stdenv.buildPlatform.isDarwin {
      __darwinAllowLocalNetworking = true;
      # Java's dual-stack sockets keep Gradle from connecting to its daemon
      # inside the Darwin sandbox.
      env = (old.env or { }) // {
        JAVA_TOOL_OPTIONS = "-Djava.net.preferIPv4Stack=true";
      };
    }
  );
  runtimeViews = purifier.jvmProjections {
    producer = runtime;
    repository = runtime.maven;
    runtimeRepository = runtime.runtime;
    formats = [ "maven" ];
    inherit runCommand python3;
  };
  provider = runtime // {
    projections = runtimeViews;
  };
  generated =
    runCommand "thrift-generated-java-package"
      (
        {
          nativeBuildInputs = [
            python3
            jdk
            gradle
            thrift
          ];
          spec = builtins.toJSON {
            resources = toString resources;
            sdk = toString thrift;
            sdkSource = toString thrift.src;
            runtimeNativeRepository = toString runtime.maven;
            runtimeRepository = toString runtimeViews.maven;
            runtimeCatalog = runtimeViews.maven.catalog;
            runtimeSource = toString prepared;
            inherit publication;
            package = options;
          };
          passAsFile = [ "spec" ];
          passthru = {
            sdkRuntime = provider;
            schemaResources = resources;
            sdkSource = prepared;
          };
        }
        // lib.optionalAttrs stdenv.buildPlatform.isDarwin {
          __darwinAllowLocalNetworking = true;
          # Java's dual-stack sockets keep Gradle from connecting to its
          # daemon inside the Darwin sandbox.
          env.JAVA_TOOL_OPTIONS = "-Djava.net.preferIPv4Stack=true";
        }
      )
      ''
        export HOME="$TMPDIR/home" GRADLE_USER_HOME="$TMPDIR/gradle-home" JAVA_HOME=${jdk}
        mkdir -p "$HOME"
        python ${./generate.py} "$specPath" "$out"
      '';
  repository = purifier.jvmProjections {
    producer = generated;
    repository = "${generated}/repository";
    dependencies = [ provider ];
    formats = [
      "maven"
      "ivy"
    ];
    inherit runCommand python3;
  };
  nativeIvy = callPackage ../maven-ivy-products { } { repository = repository.maven; };
in
assert
  valid
  || throw "cmake-purifier: thriftJavaPackage requires explicit groupId, artifactId and version";
assert
  thriftJavaRuntimeLock != null
  && thriftJavaRuntimeWrapper != null
  && builtins.isFunction thriftJavaRuntimeBuilder
  || throw "cmake-purifier: Thrift Java requires the native Gradle project constructor";
generated
// {
  projections = {
    inherit (repository) maven;
    ivy = nativeIvy;
  };
}
