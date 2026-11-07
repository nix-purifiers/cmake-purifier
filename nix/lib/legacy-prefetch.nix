# SPDX-License-Identifier: MIT
{
  nixpkgs,
  purifier,
  lockFile,
}:
let
  pkgs = import nixpkgs { };
in
(pkgs.callPackage ./legacy-sources.nix {
  inherit lockFile;
  purifier = import purifier { inherit (pkgs) lib; };
}).tree
