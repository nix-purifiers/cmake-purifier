# SPDX-License-Identifier: MIT
{
  lib,
  stdenv,
  python3,
  cmake,
  ninja,
  pkg-config,
  thrift,
  callPackage,
}:
{
  resources,
  thriftCGLibPackage,
  thriftCGLibRuntimeBuilder ? null,
}:
let
  options = thriftCGLibPackage;
  runtime =
    if thriftCGLibRuntimeBuilder == null then
      callPackage ./runtime.nix { inherit thrift; }
    else
      thriftCGLibRuntimeBuilder {
        src = thrift.src;
        version = thrift.version;
      };
  package = stdenv.mkDerivation {
    pname = "${options.name}-thrift-c-glib";
    version = options.version;
    dontUnpack = true;
    nativeBuildInputs = [
      python3
      cmake
      ninja
      pkg-config
      thrift
    ];
    buildInputs = [ runtime ];
    propagatedBuildInputs = [ runtime ];
    spec = builtins.toJSON {
      resources = toString resources;
      sdk = toString thrift;
      sdkSource = toString thrift.src;
      runtime = toString runtime;
      processorAdapter = ./processor-adapter.h;
      inherit (options) name version;
    };
    passAsFile = [ "spec" ];
    configurePhase = ''
      runHook preConfigure
      python ${./generate.py} "$specPath" source
      # Darwin consumers that link through pkg-config load the library by its
      # install name, so it names the installed path.
      cmake -S source -B build -G Ninja -DCMAKE_INSTALL_PREFIX="$out" -DCMAKE_INSTALL_NAME_DIR="$out/lib" -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
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
    postFixup = ''python ${./generate.py} --finalize "$out"'';
    passthru = {
      schemaResources = resources;
      sdk = thrift;
      sdkRuntime = runtime;
    };
  };
in
assert
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
assert thriftCGLibRuntimeBuilder == null || builtins.isFunction thriftCGLibRuntimeBuilder;
package
