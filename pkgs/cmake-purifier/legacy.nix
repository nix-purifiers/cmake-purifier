# SPDX-License-Identifier: MIT
# Explicit opt-in; an SDK derivation and its source identity stay live in
# the Nix scope. A lockfile never reconstructs a tool from a serialized path.
{
  lib,
  stdenv,
  pkgs,
  purifier,
  mitm-cache,
  openssl,
  writeShellApplication,
  writeText,
  python3,
  cmake,
  mitmproxy,
  legacyProjectName,
  legacySdkAdapter,
}:
let
  config = writeText "cmake-legacy-context.json" (
    builtins.toJSON {
      sdk = import ../../nix/lib/legacy-sdk.nix {
        inherit
          lib
          stdenv
          cmake
          legacyProjectName
          legacySdkAdapter
          ;
      };
      projectName = legacyProjectName;
      projectHook = "${../../cmake/legacy/Project.cmake}";
      mitmdump = "${mitmproxy}/bin/mitmdump";
      recorder = "${../../lock/record.py}";
      replay = "${mitm-cache}/bin/mitm-cache";
      openssl = "${openssl}/bin/openssl";
      nixpkgs = toString pkgs.path;
      purifier = toString purifier;
      prefetchExpression = "${../../nix/lib}/legacy-prefetch.nix";
    }
  );
in
writeShellApplication {
  name = "cmake-purifier";
  runtimeInputs = [
    cmake
    python3
  ];
  text = ''
    exec ${python3}/bin/python3 -B ${../../lock}/legacy.py --config ${config} "$@"
  '';
}
