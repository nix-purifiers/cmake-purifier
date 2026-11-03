# SPDX-License-Identifier: MIT
{

  description = "cmake-purifier: lock the FetchContent downloads of a CMake build, and build it in the Nix sandbox";

  inputs = {
    caisson.url = "github:nix-caisson/caisson";
    # The shared library of the nix-purifiers: the download entries and
    # their fetches.
    purifier.url = "github:nix-purifiers/purifier";
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    # The library comes from the nixpkgs.lib mirror. The package sets
    # take nixpkgs.
    nixpkgs-lib.url = "github:nix-community/nixpkgs.lib";
    flake-parts.url = "github:hercules-ci/flake-parts";
  };

  outputs =
    inputs@{ caisson, purifier, ... }:
    let
      lib = caisson.lib.caisson.mkLib {
        inherit (caisson.lib.caisson.pins.flake inputs) sources root;
        name = "cmake-purifier";
        systems = [
          "x86_64-linux"
          "aarch64-linux"
          "aarch64-darwin"
        ];
        projects = {
          inherit caisson purifier;
        };

        configs = lib: lib.caisson.mkModules ./configs;

        pkgSets = lib: lib.caisson.nixpkgs.mkConfigurations { };

        libOverlays = lib: lib.caisson.mkLibOverlays ./lib-overlays;
        pkgOverlays = lib: lib.caisson.mkPkgOverlays ./pkg-overlays;
      };
    in
    lib.caisson.flake-parts.mkTopConfiguration { };

}
