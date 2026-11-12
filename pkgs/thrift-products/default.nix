# SPDX-License-Identifier: MIT
{ lib, stdenv, python3, cmake, ninja, pkg-config, thrift }:
{ resources, thriftPackage }:
let
  options = thriftPackage;
  valid = builtins.isAttrs options && builtins.attrNames options == [ "name" "version" ]
    && builtins.isString options.name && builtins.match "[A-Za-z][A-Za-z0-9_]*" options.name != null
    && builtins.isString options.version && builtins.match "[0-9]+\\.[0-9]+\\.[0-9]+" options.version != null;
  package = stdenv.mkDerivation {
    pname = "${options.name}-thrift";
    version = options.version;
    dontUnpack = true;
    nativeBuildInputs = [ python3 cmake ninja pkg-config thrift ];
    buildInputs = [ thrift ];
    propagatedBuildInputs = [ thrift ];
    spec = builtins.toJSON { resources = toString resources; sdk = toString thrift; inherit (options) name version; };
    passAsFile = [ "spec" ];
    configurePhase = ''
      runHook preConfigure
      python ${./generate.py} "$specPath" source
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
    postFixup = ''python ${./generate.py} --finalize "$out"'';
    passthru = { schemaResources = resources; sdk = thrift; };
  };
in
assert valid || throw "cmake-purifier: thriftPackage requires a CMake identifier name and numeric x.y.z version";
package
