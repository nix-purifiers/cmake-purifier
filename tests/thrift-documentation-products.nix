# SPDX-License-Identifier: MIT
{ pkgs, build }:
let
  source = pkgs.runCommand "thrift-documentation-two-roots" { } ''
    cp -r ${./fixtures/thrift-cpp} $out
    chmod -R u+w $out
    printf 'include "common/value.thrift"\nstruct Additional { 1: value.Value extra }\n' > $out/schemas/second.thrift
  '';
  source2 = pkgs.runCommand "thrift-documentation-field-two" { } ''
    cp -r ${source} $out
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
          entrypoints = [
            "main.thrift"
            "second.thrift"
          ];
        };
      };
      raw = build args;
      built = build (
        args
        // {
          thriftDocumentation = {
            formats = [
              "html"
              "markdown"
              "gv"
              "mmd"
            ];
            webjar = {
              artifactId = "thrift-docs";
              version = "1.0.0";
            };
          };
        }
      );
      docs = built.packages.thrift-documentation;
    in
    assert raw.packages.thrift-schema.drvPath == built.packages.thrift-schema.drvPath;
    {
      generated = toString docs;
      web = docs.projections.web.documentRoot;
      javaResources = docs.projections.java-resources.classPath;
      maven = toString built.projections.maven;
      ivy = toString built.projections.ivy;
    };
in
pkgs.runCommand "thrift-native-documentation-consumers"
  (
    {
      nativeBuildInputs = [
        pkgs.python3
        pkgs.jdk
        pkgs.gradle
        pkgs.graphviz
        pkgs.thrift
      ];
      spec = builtins.toJSON {
        versions = [
          (make source)
          (make source2)
        ];
        chromium = if pkgs.stdenv.isLinux then "${pkgs.chromium}/bin/chromium" else null;
        javaConsumer = ./flatbuffers-typescript/ResourceConsumer.java;
        generator = ../pkgs/thrift-documentation-products/generate.py;
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
    export HOME="$TMPDIR/home"
    mkdir -p "$HOME"
    python ${./thrift-documentation/consume.py} "$specPath" "$out"
  ''
