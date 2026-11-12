# SPDX-License-Identifier: MIT
{
  lib,
  stdenv,
  cmake,
  python3,
  mitm-cache,
  runCommand,
  gnutar,
  writeText,
  callPackage,
  purifier,
  legacyProjectName,
  legacySdkAdapter,
}:
{
  src,
  lockFile ? src + "/cmake-purifier.lock.json",
  fetchers ? { },
  ...
}@args:
assert lib.assertMsg
  (
    (args.cmakeFlags or [ ]) == [ ]
    && (args.resourceRoots or { }) == { }
    && (args.resourceDependencies or [ ]) == [ ]
    && (args.resourceSchema or null) == null
    && (args.flatbuffersPackage or null) == null
    && (args.flatbuffersPythonPackage or null) == null
    && (args.flatbuffersJavaPackage or null) == null
    && (args.flatbuffersJavaRuntimeBuilder or null) == null
    && (args.capnprotoPackage or null) == null
    && (args.thriftPackage or null) == null
    && (args.thriftGoPackage or null) == null
    && (args.thriftGoProjector or null) == null
    && (args.thriftPythonPackage or null) == null
  )
  "cmake-purifier: legacy profile accepts locked configure definitions and installed-file outputs only";
let
  sources = callPackage ./legacy-sources.nix {
    inherit lockFile fetchers purifier;
    projectSrc = src;
  };
  lock = sources.lock;
  sdk = import ./legacy-sdk.nix {
    inherit
      lib
      stdenv
      cmake
      legacyProjectName
      legacySdkAdapter
      ;
  };
  valid = lock.sdk == sdk && lock.project.name == legacyProjectName;
  config = writeText "cmake-legacy-build-context.json" (
    builtins.toJSON {
      inherit sdk;
      projectName = legacyProjectName;
      projectHook = "${../../cmake/legacy/Project.cmake}";
    }
  );
  pname = args.pname or lock.project.name;
  version = args.version or "0";
  unavailable = throw "cmake-purifier: legacy acquisition profile has no native target metadata or projections";
  package =
    assert lib.assertMsg valid
      "cmake-purifier: legacy lock SDK/project differs from the explicit source-owned scope";
    stdenv.mkDerivation (
      removeAttrs args [
        "lockFile"
        "fetchers"
        "resourceRoots"
        "resourceDependencies"
        "resourceSchema"
        "flatbuffersPackage"
        "flatbuffersPythonPackage"
        "flatbuffersJavaPackage"
        "flatbuffersJavaRuntimeBuilder"
        "capnprotoPackage"
        "thriftPackage"
        "thriftGoPackage"
        "thriftGoProjector"
        "thriftPythonPackage"
        "cmakeFlags"
      ]
      // {
        inherit pname version src;
        nativeBuildInputs = [
          cmake
          python3
          mitm-cache
        ]
        ++ (args.nativeBuildInputs or [ ]);
        mitmCache = sources.tree;
        dontConfigure = true;
        buildPhase = ''
          runHook preConfigure
          runHook preBuild
          ${python3}/bin/python3 -B ${../../lock}/legacy.py build ${config} "$PWD" "$NIX_BUILD_TOP/legacy-native" ${lockFile} "$out"
          runHook postBuild
        '';
        installPhase = "runHook preInstall; runHook postInstall";
        passthru = (args.passthru or { }) // {
          inherit sources;
          installed = lib.genAttrs lock.outputs.files (file: "${package}/${file}");
          targetMetadataAvailable = false;
          dependencyMetadataAvailable = false;
          targets = unavailable;
          projections = unavailable;
        };
      }
    );
in
{
  packages.${pname} = package;
  tests = package;
  projections = unavailable;
  fetches = sources.memory.entries;
  release = runCommand "${pname}-${version}-release" { nativeBuildInputs = [ gnutar ]; } ''
    mkdir $out
    tar --sort=name --mtime=@1 --owner=0 --group=0 --numeric-owner -C ${package} -cf - . |
      gzip -9n > $out/${pname}-${version}-${stdenv.hostPlatform.system}.tar.gz
  '';
}
