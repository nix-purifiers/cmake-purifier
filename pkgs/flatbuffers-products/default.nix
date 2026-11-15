# SPDX-License-Identifier: MIT
{
  lib,
  runCommand,
  python3,
  flatbuffers,
  cmake,
}:
{ resources, flatbuffersPackage }:
let
  options = flatbuffersPackage;
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
  package =
    runCommand "${options.name}-flatbuffers-${options.version}"
      {
        nativeBuildInputs = [
          python3
          flatbuffers
          cmake
        ];
        spec = builtins.toJSON {
          resources = toString resources;
          sdk = toString flatbuffers;
          inherit (options) name version;
        };
        passAsFile = [ "spec" ];
        passthru = {
          schemaResources = resources;
          sdk = flatbuffers;
        };
      }
      ''
        python ${./.}/generate.py "$specPath" "$out"
      '';
in
assert
  valid
  || throw "cmake-purifier: flatbuffersPackage requires a CMake identifier name and numeric x.y.z version";
package
