# SPDX-License-Identifier: MIT
{
  lib,
  runCommand,
  python3,
  cargo,
  rustc,
  flatbuffers,
}:
{
  resources,
  flatbuffersRustPackage,
  flatbuffersRustRuntimeLock,
  flatbuffersRustVendorBuilder,
  flatbuffersRustProjector,
}:
let
  options = flatbuffersRustPackage;
  valid =
    builtins.isAttrs options
    && builtins.attrNames options == [ "name" ]
    && builtins.isString options.name
    && builtins.match "[A-Za-z][A-Za-z0-9_-]*" options.name != null;
  fetched = flatbuffersRustVendorBuilder {
    src = flatbuffers.src;
    sourceRoot = "source/rust/flatbuffers";
    name = "flatbuffers-native-rust-vendor";
    postPatch = "cp ${flatbuffersRustRuntimeLock} Cargo.lock";
  };
  runtimeSource = runCommand "flatbuffers-rust-runtime-source" { } ''
    cp -r ${flatbuffers.src}/rust/flatbuffers $out
    chmod -R u+w $out
    cp ${flatbuffersRustRuntimeLock} $out/Cargo.lock
  '';
  vendor =
    runCommand "flatbuffers-rust-normalized-vendor"
      {
        nativeBuildInputs = [
          cargo
          rustc
        ];
      }
      ''
        export HOME="$TMPDIR/home" CARGO_HOME="$TMPDIR/cargo-home"
        mkdir -p "$HOME" "$CARGO_HOME"
        cp -r ${runtimeSource} sdk
        chmod -R u+w sdk
        mkdir -p sdk/.cargo
        substitute ${fetched}/.cargo/config.toml sdk/.cargo/config.toml --subst-var-by vendor ${fetched}
        cd sdk
        cargo vendor --offline --locked --respect-source-config --versioned-dirs "$out" > "$TMPDIR/config.toml"
        mkdir -p "$out/.cargo"
        cp "$TMPDIR/config.toml" "$out/.cargo/config.toml"
      '';
  runtimeRepository = flatbuffersRustProjector {
    src = runtimeSource;
    workspace = ".";
    dependencies = [ ];
    inherit vendor;
    cargoLock = "${runtimeSource}/Cargo.lock";
    entries = [ ];
    name = "flatbuffers-rust-runtime-repository";
  };
  runtime = runtimeSource // {
    projections.cargo = runtimeRepository;
  };
  generated =
    runCommand "flatbuffers-generated-rust-crate"
      {
        nativeBuildInputs = [
          python3
          cargo
          rustc
          flatbuffers
        ];
        spec = builtins.toJSON {
          resources = toString resources;
          sdk = toString flatbuffers;
          sdkSource = toString flatbuffers.src;
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
  repository = flatbuffersRustProjector {
    src = "${generated}/crate";
    workspace = ".";
    dependencies = [ runtime ];
    inherit vendor;
    cargoLock = "${generated}/crate/Cargo.lock";
    entries = [ ];
    name = "flatbuffers-generated-rust-repository";
  };
in
assert valid || throw "cmake-purifier: flatbuffersRustPackage requires a native Cargo package name";
assert
  flatbuffersRustRuntimeLock != null
  && builtins.isFunction flatbuffersRustVendorBuilder
  && builtins.isFunction flatbuffersRustProjector
  || throw "cmake-purifier: FlatBuffers Rust requires a captured native runtime lock, vendor builder and Cargo projector";
generated // { projections.cargo = repository; }
