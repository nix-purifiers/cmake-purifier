{
  pkgs,
  build,
  projector,
}:
let
  source1 = pkgs.runCommand "flatbuffers-go-qualified-types" { } ''
    cp -r ${./fixtures/flatbuffers-schema} $out
    chmod -R u+w $out
    echo 'namespace extra; table Packet { answer:int; } root_type Packet; file_identifier "EXT1";' > "$out/schemas/other.fbs"
    echo 'namespace a; table Value { answer:int; }' > "$out/schemas/a.fbs"
    echo 'namespace b; table Value { answer:int; }' > "$out/schemas/b.fbs"
    substituteInPlace "$out/schemas/main.fbs" --replace-fail 'namespace proof;' 'include "a.fbs"; include "b.fbs"; namespace proof;'
  '';
  source2 = pkgs.runCommand "flatbuffers-go-long" { } ''
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
      built = build (
        args
        // {
          flatbuffersPackage = {
            name = "schema_proof";
            version = "1.0.0";
          };
          flatbuffersGoPackage.modulePath = "example.org/schemas";
          flatbuffersGoRuntimeModulePath = "github.com/google/flatbuffers/go";
          flatbuffersGoProjector = projector;

        }
      );
      package = built.packages.flatbuffers-go-bindings;
    in
    assert raw.packages.schema-bundle.drvPath == built.packages.schema-bundle.drvPath;
    {
      inherit bits;
      generated = toString package;
      repository = toString package.projections.go;
      runtimeCatalog = package.sdkRuntime.catalog;
      cpp = toString built.packages.flatbuffers-bindings;
    };
in
pkgs.runCommand "flatbuffers-go-native-consumers"
  {
    nativeBuildInputs = [
      pkgs.python3
      pkgs.go
      pkgs.stdenv.cc
      pkgs.pkg-config
    ];
    buildInputs = [ pkgs.flatbuffers ];
    spec = builtins.toJSON {
      versions = [
        (make source1 32)
        (make source2 64)
      ];
      consumer = ./flatbuffers-go/consumer.go;
      generator = ../pkgs/flatbuffers-go-products/generate.py;
      cppConsumer = ./flatbuffers-python/consumer.cpp;
    };
    passAsFile = [ "spec" ];
  }
  ''
    export HOME="$TMPDIR/home"
    mkdir -p "$HOME"
    python ${./flatbuffers-go/consume.py} "$specPath" "$out"
  ''
