{
  pkgs,
  build,
  projector,
}:
let
  source1 = pkgs.runCommand "thrift-go-namespaces" { } ''
    cp -r ${./fixtures/thrift-cpp} $out
    chmod -R u+w $out
    substituteInPlace $out/schemas/main.thrift --replace-fail 'namespace py main_value' 'namespace py main_value
    namespace go main_value'
    substituteInPlace $out/schemas/common/value.thrift --replace-fail 'namespace py common_value' 'namespace py common_value
    namespace go common_value'
  '';
  source2 = pkgs.runCommand "thrift-go-second-field" { } ''
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
          thriftGoPackage.modulePath = "example.org/schemas";
          thriftGoProjector = projector;
          thriftPackage = {
            name = "thrift_proof";
            version = "1.0.0";
          };
        }
      );
      package = built.packages.thrift-go-bindings;
    in
    assert raw.packages.thrift-schema.drvPath == built.packages.thrift-schema.drvPath;
    {
      package = toString package;
      runtimeCatalog = package.sdkRuntime.catalog;
      repository = toString built.projections.go;
      cpp = toString built.packages.thrift-bindings;
    };
  reject =
    !(builtins.tryEval
      (build {
        src = ./fixtures/thrift-cpp;
        thriftGoPackage.modulePath = "example.org/schemas";
        thriftGoProjector = projector;
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
        thriftGoPackage.modulePath = "example.org/schemas";
      }).packages.thrift-go-bindings.drvPath
    ).success;
in
assert reject;
assert missingProjector;
pkgs.runCommand "thrift-go-native-consumers"
  {
    nativeBuildInputs = [
      pkgs.go
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
      consumer = ./thrift-go/consumer.go;
      generator = ../pkgs/thrift-go-products/generate.py;
      runtimeCatalog = (make source1).runtimeCatalog;
      cppConsumer = ./thrift/consumer.cpp;
      dlLibs = pkgs.lib.optionals (!pkgs.stdenv.hostPlatform.isDarwin) [ "-ldl" ];
    };
    passAsFile = [ "spec" ];
  }
  ''
    python ${./thrift-go/consume.py} "$specPath" "$out"
  ''
