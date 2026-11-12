# SPDX-License-Identifier: MIT
{
  lib,
  stdenv,
  runCommand,
  python3,
  cmake,
  ninja,
  pkg-config,
  capnproto,
}:
{ resources, capnprotoPackage }:
let
  options = capnprotoPackage;
  valid =
    builtins.isAttrs options
    &&
      builtins.attrNames options == [
        "name"
        "version"
      ]
    && builtins.isString options.name
    && builtins.match "[A-Za-z][A-Za-z0-9_]*" options.name != null
    && builtins.isString options.version
    && builtins.match "[0-9]+\\.[0-9]+\\.[0-9]+" options.version != null;
  inspector =
    runCommand "capnp-native-request-inspector"
      {
        nativeBuildInputs = [
          stdenv.cc
          cmake
          ninja
        ];
        buildInputs = [ capnproto ];
      }
      ''
        cmake -S ${./.} -B build -G Ninja -DCAPNP_SDK=${capnproto} -DCMAKE_INSTALL_PREFIX=$out
        cmake --build build
        cmake --install build
      '';
  package = stdenv.mkDerivation {
    pname = "${options.name}-capnproto";
    version = options.version;
    dontUnpack = true;
    nativeBuildInputs = [
      python3
      cmake
      ninja
      pkg-config
      capnproto
    ];
    buildInputs = [ capnproto ];
    propagatedBuildInputs = [ capnproto ];
    spec = builtins.toJSON {
      resources = toString resources;
      sdk = toString capnproto;
      inspector = "${inspector}/bin/inspect";
      inherit (options) name version;
    };
    passAsFile = [ "spec" ];
    configurePhase = ''
      runHook preConfigure
      python ${./.}/generate.py "$specPath" source
      cmake -S source -B build -G Ninja -DCMAKE_INSTALL_PREFIX="$out" -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
      runHook postConfigure
    '';
    buildPhase = ''
      runHook preBuild
      cmake --build build
      runHook postBuild
    '';
    installPhase = ''
      runHook preInstall
      cmake --install build
      runHook postInstall
    '';
    postFixup = ''
      python ${./.}/generate.py --finalize "$out"
    '';
    passthru = {
      schemaResources = resources;
      sdk = capnproto;
      nativeInspector = inspector;
    };
  };
in
assert
  valid
  || throw "cmake-purifier: capnprotoPackage requires a CMake identifier name and numeric x.y.z version";
package
