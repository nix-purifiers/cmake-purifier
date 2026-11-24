# SPDX-License-Identifier: MIT
{
  lib,
  runCommand,
  python3,
  thrift,
  haxe,
  neko,
  stdenv,
  callPackage,
  purifier,
  haxelibPurifierSource,
}:
{
  resources,
  thriftHaxePackage,
  thriftHaxeRuntimeBuilder,
}:
let
  nativeHaxelib = callPackage (haxelibPurifierSource + "/pkgs/build-haxelib-project/native.nix") {
    inherit haxe neko;
  };
  tools = {
    inherit
      thrift
      haxe
      nativeHaxelib
      neko
      ;
  };
  runtime = thriftHaxeRuntimeBuilder tools;
  toolPackages = {
    inherit haxe neko;
    haxelib = nativeHaxelib;
  };
  toolIdentities = lib.mapAttrs (_: purifier.inputIdentity) toolPackages;
  runtimeProof =
    runCommand "thrift-original-haxe-runtime-proof"
      {
        spec = builtins.toJSON {
          sdkSource = toString thrift.src;
          source = toString runtime.source;
          installedRoot = toString runtime.installedRoot;
          repository = toString runtime.repository;
          producerIdentity = purifier.inputIdentity runtime.producer;
          producerOutputs = map (
            name: toString (lib.getOutput name runtime.producer)
          ) runtime.producer.outputs;
          dependencyOutputs = lib.concatMap (
            dependency:
            map (name: {
              path = toString (lib.getOutput name dependency);
              identity = purifier.inputIdentity dependency;
            }) dependency.outputs
          ) (runtime.dependencies or [ ]);
          inherit toolIdentities;
          toolVersions = lib.mapAttrs (_: package: package.version) toolPackages;
          thrift = "${thrift}/bin/thrift";
          haxe = "${haxe}/bin/haxe";
          haxelib = "${nativeHaxelib}/bin/haxelib";
          inspect = "${nativeHaxelib}/bin/haxelib-purifier-inspect";
          neko = "${neko}/bin/neko";
        };
        passAsFile = [ "spec" ];
        nativeBuildInputs = [ python3 ];
      }
      ''
        export HOME="$TMPDIR/home"
        mkdir -p "$HOME" "$out"
        python3 ${./runtime-proof.py} "$specPath" "$out/runtime.json"
      '';
  source =
    runCommand "thrift-generated-haxe-source"
      {
        outputs = [
          "out"
          "proof"
        ];
        nativeBuildInputs = [ python3 ];
        spec = builtins.toJSON {
          resources = toString resources;
          sdk = toString thrift;
          runtimeProof = "${runtimeProof}/runtime.json";
          manifest = "${thriftHaxePackage.manifest}";
          inspect = "${nativeHaxelib}/bin/haxelib-purifier-inspect";
        };
        passAsFile = [ "spec" ];
      }
      ''
        python3 ${./generate.py} "$specPath" "$out" "$proof"
      '';
  installed =
    runCommand "thrift-generated-haxelib-package"
      {
        outputs = [
          "out"
          "proof"
        ];
        nativeBuildInputs = [ python3 ];
        spec = builtins.toJSON {
          sourceProof = toString source.proof;
          runtimeProof = "${runtimeProof}/runtime.json";
          repository = toString runtime.repository;
          haxelib = "${nativeHaxelib}/bin/haxelib";
          inspect = "${nativeHaxelib}/bin/haxelib-purifier-inspect";
          haxe = "${haxe}/bin/haxe";
          haxeRoot = toString haxe;
        };
        passAsFile = [ "spec" ];
      }
      ''
        export HOME="$TMPDIR/home"
        mkdir -p "$HOME" "$proof"
        python3 ${./install.py} "$specPath" ${source} "$out" "$proof"
      '';
  projection = installed // {
    archive = "${installed}/library.zip";
    repository = "${installed}/repository";
    inherit haxe nativeHaxelib neko;
    originalProducer = installed;
    target = "neko";
  };
in
assert lib.assertMsg stdenv.hostPlatform.isLinux
  "Thrift Haxe currently requires the supported Linux native Haxelib SDK";
assert lib.assertMsg (
  builtins.isAttrs thriftHaxePackage && builtins.attrNames thriftHaxePackage == [ "manifest" ]
) "thriftHaxePackage requires an authored native haxelib.json manifest";
assert lib.assertMsg (builtins.isFunction thriftHaxeRuntimeBuilder)
  "Thrift Haxe needs an original SDK runtime builder";
assert lib.assertMsg (lib.isDerivation runtime.producer)
  "Thrift Haxe runtime must retain its original Nix producer";
assert lib.assertMsg (builtins.all lib.isDerivation (
  runtime.dependencies or [ ]
)) "Thrift Haxe runtime suppliers must be original Nix derivations";
assert lib.assertMsg (
  purifier.inputIdentity runtime.haxe == toolIdentities.haxe
  && purifier.inputIdentity runtime.nativeHaxelib == toolIdentities.haxelib
  && purifier.inputIdentity runtime.neko == toolIdentities.neko
) "Thrift Haxe runtime must use the selected original native tools";
installed
// {
  inherit
    runtime
    runtimeProof
    tools
    source
    ;
  sdk = thrift;
  schemaResources = resources;
  projections.haxelib = projection;
}
