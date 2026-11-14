{
  pkgs,
  build,
  projector,
}:
let
  source1 = pkgs.runCommand "flatbuffers-rust-qualified-types" { } ''
    cp -r ${./fixtures/flatbuffers-schema} $out
    chmod -R u+w $out
    echo 'namespace extra; table Packet { answer:int; } root_type Packet; file_identifier "EXT1";' > "$out/schemas/other.fbs"
    echo 'namespace a; table Value { answer:int; }' > "$out/schemas/a.fbs"
    echo 'namespace b; table Value { answer:int; }' > "$out/schemas/b.fbs"
    substituteInPlace "$out/schemas/main.fbs" --replace-fail 'namespace proof;' 'include "a.fbs"; include "b.fbs"; namespace proof;'
  '';
  source2 = pkgs.runCommand "flatbuffers-rust-long" { } ''
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
          flatbuffersRustPackage.name = "proof_schemas";
          flatbuffersRustRuntimeLock = ./flatbuffers-rust-runtime.Cargo.lock;
          flatbuffersRustVendorBuilder =
            args:
            pkgs.rustPlatform.fetchCargoVendor (
              args // { hash = "sha256-gw5qhmu2shDosxCN0gNWRjHyE70WUgKMML2KFwlq5cI="; }
            );
          flatbuffersRustProjector = projector;
        }
      );
      package = built.packages.flatbuffers-rust-bindings;
    in
    assert raw.packages.schema-bundle.drvPath == built.packages.schema-bundle.drvPath;
    {
      inherit bits;
      generated = toString package;
      repository = toString package.projections.cargo;
      cpp = toString built.packages.flatbuffers-bindings;
    };
in
pkgs.runCommand "flatbuffers-rust-native-consumers"
  {
    nativeBuildInputs = [
      pkgs.python3
      pkgs.cargo
      pkgs.rustc
      pkgs.stdenv.cc
      pkgs.pkg-config
    ];
    buildInputs = [ pkgs.flatbuffers ];
    spec = builtins.toJSON {
      versions = [
        (make source1 32)
        (make source2 64)
      ];
      consumer = ./flatbuffers-rust/consumer.rs;
      generator = ../pkgs/flatbuffers-rust-products/generate.py;
      cppConsumer = ./flatbuffers-python/consumer.cpp;
    };
    passAsFile = [ "spec" ];
  }
  ''
    export HOME="$TMPDIR/home" CARGO_HOME="$TMPDIR/cargo-home"
    mkdir -p "$HOME" "$CARGO_HOME"
    python ${./flatbuffers-rust/consume.py} "$specPath" "$out"
  ''
