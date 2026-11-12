# SPDX-License-Identifier: MIT
{
  lib,
  runCommand,
  python3,
  flatbuffers,
  jdk,
  maven,
  purifier,
}:
{
  resources,
  flatbuffersJavaPackage,
  flatbuffersJavaRuntimeBuilder,
}:
let
  options = flatbuffersJavaPackage;
  coordinate =
    value: builtins.isString value && builtins.match "[A-Za-z0-9_][A-Za-z0-9_.+-]*" value != null;
  valid =
    builtins.isAttrs options
    &&
      builtins.attrNames options == [
        "artifactId"
        "groupId"
        "version"
      ]
    && builtins.all coordinate [
      options.groupId
      options.artifactId
      options.version
    ];
  nativeRuntime = import ./runtime.nix { inherit python3 flatbuffers; } {
    runtimeBuilder = flatbuffersJavaRuntimeBuilder;
  };
  runtime = runCommand "flatbuffers-java-runtime-publication" { nativeBuildInputs = [ python3 ]; } ''
    python ${./runtime-output.py} ${flatbuffers} ${flatbuffers.src} ${nativeRuntime} "$out"
  '';
  runtimePackage = runtime // {
    projections = purifier.jvmProjections {
      producer = runtime;
      repository = "${runtime}/repository";
      inherit runCommand python3;
    };
  };
  bindings =
    runCommand "flatbuffers-generated-java-bindings"
      {
        nativeBuildInputs = [
          python3
          jdk
          maven
          flatbuffers
        ];
        spec = builtins.toJSON {
          resources = toString resources;
          sdk = toString flatbuffers;
          sdkSource = toString flatbuffers.src;
          runtime = toString runtime;
          maven = toString maven;
          publisherSource = "${./.}/Publish.java";
          jdk = toString jdk;
          inherit (options) groupId artifactId version;
        };
        passAsFile = [ "spec" ];
        passthru = {
          schemaResources = resources;
          sdkRuntime = runtimePackage;
        };
      }
      ''
        export HOME="$TMPDIR/home"
        mkdir -p "$HOME"
        python ${./generate.py} "$specPath" "$out"
      '';
in
assert valid || throw "cmake-purifier: flatbuffersJavaPackage requires explicit Maven coordinates";
assert
  builtins.isFunction flatbuffersJavaRuntimeBuilder
  || throw "cmake-purifier: FlatBuffers Java requires an explicit native SDK runtime builder";
bindings
// {
  projections = purifier.jvmProjections {
    producer = bindings;
    repository = "${bindings}/repository";
    dependencies = [ runtimePackage ];
    inherit runCommand python3;
  };
}
