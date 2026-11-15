# SPDX-License-Identifier: MIT
{
  lib,
  runCommand,
  writeText,
  python3,
  go,
  flatbuffers,
  purifier,
}:
{
  resources,
  flatbuffersGoPackage,
  flatbuffersGoRuntimeModulePath,
  flatbuffersGoProjector,
}:
let
  valid =
    builtins.isAttrs flatbuffersGoPackage
    && builtins.attrNames flatbuffersGoPackage == [ "modulePath" ]
    && builtins.isString flatbuffersGoPackage.modulePath
    && builtins.match "[A-Za-z0-9][A-Za-z0-9./_+-]*" flatbuffersGoPackage.modulePath != null;
  runtimeSource = runCommand "flatbuffers-go-runtime-source" { nativeBuildInputs = [ go ]; } ''
    export HOME="$TMPDIR/home" GOCACHE="$TMPDIR/cache" GOPATH="$TMPDIR/go" GOTOOLCHAIN=local GOWORK=off GOPROXY=off GOSUMDB=off
    cp -r ${flatbuffers.src}/go $out
    chmod -R u+w $out
    cd $out
    go mod init ${lib.escapeShellArg flatbuffersGoRuntimeModulePath}
  '';
  runtimeIdentity = runCommand "flatbuffers-go-runtime-identity" {
    source = runtimeSource;
    projector = flatbuffersGoProjector;
  } "touch $out";
  runtimeRequest = writeText "flatbuffers-go-runtime-projection.json" (
    builtins.toJSON {
      identity = (purifier.inputIdentity runtimeIdentity).hash;
      modules = [ (toString runtimeSource) ];
      repositories = [ ];
    }
  );
  runtime = runCommand "flatbuffers-go-runtime-module-proxy" {
    nativeBuildInputs = [ flatbuffersGoProjector ];
    passthru.catalog = "${runtime}/.catalog";
  } ''go-purifier project-modules ${runtimeRequest} "$out"'';
  generated =
    runCommand "flatbuffers-generated-go-module"
      {
        nativeBuildInputs = [
          python3
          go
          flatbuffers
        ];
        spec = builtins.toJSON {
          resources = toString resources;
          sdk = toString flatbuffers;
          sdkSource = toString flatbuffers.src;
          runtimeCatalog = runtime.catalog;
          runtimeSource = toString runtimeSource;
          runtimeModulePath = flatbuffersGoRuntimeModulePath;
          inherit (flatbuffersGoPackage) modulePath;
        };
        passAsFile = [ "spec" ];
        passthru = {
          schemaResources = resources;
          sdkRuntime = runtime;
        };
      }
      ''
        export HOME="$TMPDIR/home" GOCACHE="$TMPDIR/cache" GOPATH="$TMPDIR/go" GOTOOLCHAIN=local GOWORK=off GOPROXY=off GOSUMDB=off
        mkdir -p "$HOME"
        python ${./generate.py} "$specPath" "$out"
      '';
  identity = runCommand "flatbuffers-go-module-identity" {
    inherit generated runtime;
    projector = flatbuffersGoProjector;
  } "touch $out";
  request = writeText "flatbuffers-go-module-projection.json" (
    builtins.toJSON {
      identity = (purifier.inputIdentity identity).hash;
      modules = [ "${generated}/module" ];
      repositories = [ (toString runtime) ];
    }
  );
  repository = runCommand "flatbuffers-go-module-repository" {
    nativeBuildInputs = [ flatbuffersGoProjector ];
    passthru.catalog = "${repository}/.catalog";
  } ''go-purifier project-modules ${request} "$out"'';
in
assert
  builtins.isString flatbuffersGoRuntimeModulePath
  && builtins.match "[A-Za-z0-9][A-Za-z0-9./_+-]*" flatbuffersGoRuntimeModulePath != null
  || throw "cmake-purifier: FlatBuffers Go requires an explicit SDK runtime module path";
assert valid || throw "cmake-purifier: flatbuffersGoPackage requires an explicit Go modulePath";
assert
  lib.isDerivation flatbuffersGoProjector
  || throw "cmake-purifier: Thrift Go requires an explicit native Go purifier CLI";
generated // { projections.go = repository; }
