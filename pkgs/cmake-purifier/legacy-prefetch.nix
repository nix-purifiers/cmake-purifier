# SPDX-License-Identifier: MIT
{
  nixpkgs,
  purifier,
  lockFile,
}:
let
  pkgs = import nixpkgs { };
in
(pkgs.callPackage ../build-cmake-project/legacy-sources.nix {
  inherit lockFile;
  purifier = import purifier { inherit (pkgs) lib; };
}).tree
