{
  pkgs,
  build,
  projector,
}:
let
  source1 = pkgs.runCommand "thrift-rust-qualified-types" { } ''
    cp -r ${./fixtures/thrift-cpp} $out
    chmod -R u+w $out
    echo 'namespace cpp a
    struct Value { 1: i32 answer }' > "$out/schemas/a.thrift"
    echo 'namespace cpp b
    struct Value { 1: i32 answer }' > "$out/schemas/b.thrift"
    substituteInPlace "$out/schemas/main.thrift" --replace-fail 'include "common/value.thrift"' 'include "common/value.thrift"
    include "a.thrift"
    include "b.thrift"'
  '';
  source2 = pkgs.runCommand "thrift-rust-second-field" { } ''
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
        pname = "schema-bundle";
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
          thriftRustPackage.name = "proof_schemas";
          thriftRustRuntimeLock = ./thrift-rust-runtime.Cargo.lock;
          thriftRustVendorBuilder =
            args:
            pkgs.rustPlatform.fetchCargoVendor (
              args // { hash = "sha256-0JrEFt/ZFkRlMvwlKiO2YzjvLLjdR9p+8CIwLTFExB8="; }
            );
          thriftRustProjector = projector;
        }
      );
      package = built.packages.thrift-rust-bindings;
    in
    assert raw.packages.schema-bundle.drvPath == built.packages.schema-bundle.drvPath;
    {
      generated = toString package;
      vendor = toString package.vendor;
      nativeVendor = toString package.vendor.nativeVendor;
      repository = toString package.projections.cargo;
      cpp = toString built.packages.thrift-bindings;
    };
  missingResources =
    !(builtins.tryEval
      (build {
        src = ./fixtures/thrift-cpp;
        thriftRustPackage.name = "proof_schemas";
      }).packages.schema_bundle.drvPath
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
        thriftRustPackage.name = "proof_schemas";
      }).packages.thrift-rust-bindings.drvPath
    ).success;
in
assert missingResources;
assert missingProjector;
pkgs.runCommand "thrift-rust-native-consumers"
  {
    nativeBuildInputs = [
      pkgs.python3
      pkgs.cargo
      pkgs.rustc
      pkgs.stdenv.cc
      pkgs.pkg-config
    ];
    buildInputs = [ pkgs.thrift ];
    spec = builtins.toJSON {
      versions = [
        (make source1)
        (make source2)
      ];
      consumer = ./thrift-rust/consumer.rs;
      generator = ../pkgs/thrift-rust-products/generate.py;
      cppConsumer = ./thrift/consumer.cpp;
      dlLibs = pkgs.lib.optionals (!pkgs.stdenv.hostPlatform.isDarwin) [ "-ldl" ];
    };
    passAsFile = [ "spec" ];
  }
  ''
    export HOME="$TMPDIR/home" CARGO_HOME="$TMPDIR/cargo-home"
    mkdir -p "$HOME" "$CARGO_HOME"
    python ${./thrift-rust/consume.py} "$specPath" "$out"
  ''
