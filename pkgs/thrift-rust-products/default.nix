# SPDX-License-Identifier: MIT
{
  lib,
  runCommand,
  python3,
  cargo,
  rustc,
  thrift,
}:
{
  resources,
  thriftRustPackage,
  thriftRustRuntimeLock,
  thriftRustVendorBuilder,
  thriftRustProjector,
}:
let
  options = thriftRustPackage;
  valid =
    builtins.isAttrs options
    && builtins.attrNames options == [ "name" ]
    && builtins.isString options.name
    && builtins.match "[A-Za-z][A-Za-z0-9_-]*" options.name != null;
  fetched = thriftRustVendorBuilder {
    src = thrift.src;
    sourceRoot = "source/lib/rs";
    name = "thrift-native-rust-vendor";
    postPatch = "cp ${thriftRustRuntimeLock} Cargo.lock";
  };
  runtimeSource = runCommand "thrift-rust-runtime-source" { } ''
    cp -rL ${thrift.src}/lib/rs $out
    chmod -R u+w $out
    cp ${thriftRustRuntimeLock} $out/Cargo.lock
  '';
  vendor =
    runCommand "thrift-rust-preserved-vendor"
      {
        nativeBuildInputs = [ python3 ];
        passthru.nativeVendor = fetched;
      }
      ''
        python ${./prepare-vendor.py} ${fetched} "$out"
      '';
  runtimeRepository = thriftRustProjector {
    src = runtimeSource;
    workspace = ".";
    dependencies = [ ];
    inherit vendor;
    cargoLock = "${runtimeSource}/Cargo.lock";
    entries = [ ];
    name = "thrift-rust-runtime-repository";
  };
  runtime = runtimeSource // {
    projections.cargo = runtimeRepository;
  };
  generated =
    runCommand "thrift-generated-rust-crate"
      {
        nativeBuildInputs = [
          python3
          cargo
          rustc
          thrift
        ];
        spec = builtins.toJSON {
          resources = toString resources;
          sdk = toString thrift;
          sdkSource = toString thrift.src;
          runtime = toString runtimeSource;
          runtimeRepository = toString runtimeRepository;
          runtimeCatalog = runtimeRepository.catalog;
          inherit (options) name;
        };
        passAsFile = [ "spec" ];
        passthru = {
          sdkRuntime = runtime;
          schemaResources = resources;
          inherit vendor;
        };
      }
      ''
        export HOME="$TMPDIR/home" CARGO_HOME="$TMPDIR/cargo-home"
        mkdir -p "$HOME" "$CARGO_HOME"
        python ${./generate.py} "$specPath" "$out"
      '';
  repository = thriftRustProjector {
    src = "${generated}/crate";
    workspace = ".";
    dependencies = [ runtime ];
    inherit vendor;
    cargoLock = "${generated}/crate/Cargo.lock";
    entries = [ ];
    name = "thrift-generated-rust-repository";
  };
in
assert valid || throw "cmake-purifier: thriftRustPackage requires a native Cargo package name";
assert
  thriftRustRuntimeLock != null
  && builtins.isFunction thriftRustVendorBuilder
  && builtins.isFunction thriftRustProjector
  || throw "cmake-purifier: Thrift Rust requires a captured native runtime lock, vendor builder and Cargo projector";
generated // { projections.cargo = repository; }
