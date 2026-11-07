# SPDX-License-Identifier: MIT
# Source-built SDKs selected independently of the purifier's ambient nixpkgs.
# Hashes come from Kitware's per-release SHA-256 manifests in sources.json.
{ pkgs }:
pkgs.lib.mapAttrs (
  version: source:
  pkgs.cmake.overrideAttrs (previous: {
    inherit version;
    # Same nixpkgs prefix lookup, rebased onto the 3.31 source layout.
    # The ambient nixpkgs patch removing system search paths is tied to
    # its own module layout. Keep functional Nix prefix/SDK patches for
    # other releases; the build checks still run in the Nix sandbox.
    patches =
      map
        (
          patch:
          if
            pkgs.lib.versionOlder version "4" && builtins.baseNameOf patch == "nixpkgs-cmake-prefix-path.patch"
          then
            ./cmake3-prefix.patch
          else if
            pkgs.lib.versionOlder version "4" && pkgs.lib.hasSuffix "darwin-binary-paths.patch" (toString patch)
          then
            pkgs.replaceVars ./cmake3-darwin-binary-paths.patch {
              sw_vers = pkgs.lib.getExe' pkgs.darwin.DarwinTools "sw_vers";
              vm_stat = pkgs.lib.getExe' pkgs.darwin.system_cmds "vm_stat";
            }
          else if
            pkgs.lib.versionOlder version "4"
            && pkgs.lib.hasSuffix "darwin-bsd-binary-paths.patch" (toString patch)
          then
            pkgs.replaceVars ./cmake3-darwin-bsd-binary-paths.patch {
              ps = pkgs.lib.getExe pkgs.ps;
              sysctl = pkgs.lib.getExe pkgs.sysctl;
            }
          else
            patch
        )
        (
          builtins.filter (
            patch: version == "4.4.5" || builtins.baseNameOf patch != "remove-impure-search-paths.patch"
          ) previous.patches
        );
    src = pkgs.fetchurl {
      inherit (source) url sha256;
    };
  })
) (builtins.fromJSON (builtins.readFile ./sources.json))
