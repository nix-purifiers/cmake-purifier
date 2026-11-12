# SPDX-License-Identifier: MIT
{
  lib,
  runCommand,
  writeText,
  python3,
  go,
  thrift,
  purifier,
}:
{
  resources,
  thriftGoPackage,
  thriftGoProjector,
}:
let
  valid =
    builtins.isAttrs thriftGoPackage
    && builtins.attrNames thriftGoPackage == [ "modulePath" ]
    && builtins.isString thriftGoPackage.modulePath
    && builtins.match "[A-Za-z0-9][A-Za-z0-9./_+-]*" thriftGoPackage.modulePath != null;
  runtimeIdentity = runCommand "thrift-go-runtime-identity" {
    source = thrift.src;
    projector = thriftGoProjector;
  } "touch $out";
  runtimeRequest = writeText "thrift-go-runtime-projection.json" (
    builtins.toJSON {
      identity = (purifier.inputIdentity runtimeIdentity).hash;
      modules = [ (toString thrift.src) ];
      repositories = [ ];
    }
  );
  runtime = runCommand "thrift-go-runtime-module-proxy" {
    nativeBuildInputs = [ thriftGoProjector ];
    passthru.catalog = "${runtime}/.catalog";
  } ''go-purifier project-modules ${runtimeRequest} "$out"'';
  generated =
    runCommand "thrift-generated-go-module"
      {
        nativeBuildInputs = [
          python3
          go
          thrift
        ];
        spec = builtins.toJSON {
          resources = toString resources;
          sdk = toString thrift;
          sdkSource = toString thrift.src;
          runtimeCatalog = runtime.catalog;
          inherit (thriftGoPackage) modulePath;
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
  identity = runCommand "thrift-go-module-identity" {
    inherit generated runtime;
    projector = thriftGoProjector;
  } "touch $out";
  request = writeText "thrift-go-module-projection.json" (
    builtins.toJSON {
      identity = (purifier.inputIdentity identity).hash;
      modules = [ "${generated}/module" ];
      repositories = [ (toString runtime) ];
    }
  );
  repository = runCommand "thrift-go-module-repository" {
    nativeBuildInputs = [ thriftGoProjector ];
    passthru.catalog = "${repository}/.catalog";
  } ''go-purifier project-modules ${request} "$out"'';
in
assert valid || throw "cmake-purifier: thriftGoPackage requires an explicit Go modulePath";
assert
  lib.isDerivation thriftGoProjector
  || throw "cmake-purifier: Thrift Go requires an explicit native Go purifier CLI";
generated // { projections.go = repository; }
