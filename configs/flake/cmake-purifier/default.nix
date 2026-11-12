# SPDX-License-Identifier: MIT
{ closure-lib, ... }:
{
  config,
  inputs,
  lib,
  ...
}:
{

  imports = [
    ../../../tests/toolchains/module.nix
    inputs.flake-parts.flakeModules.partitions
    closure-lib.caisson.modules.flake."purifier/purifier-packages"
  ];

  debug = false;
  caisson.libOverlays.exported = libOverlays: {
    inherit (libOverlays) default;
  };

  # The scope `pkgs.cmake-purifier` is the `default` entry of the package
  # overlay registry (pkg-overlays/): the package set applies it by
  # default, and the flake exports it as `pkgOverlays` and as the plain
  # `overlays.default`. The module purifier-packages publishes the
  # derivations of the scope as `packages`.
  purifier.scope = "cmake-purifier";

  # `nix run github:nix-purifiers/cmake-purifier -- lock` locks the build in
  # the current directory. `nix develop github:nix-purifiers/cmake-purifier`
  # gives a shell with the command, CMake, Ninja, make, the C and C++
  # compilers of stdenv, and clangd, which is enough to lock, prefetch,
  # build and edit a project whose other dependencies come from
  # FetchContent.
  perSystem =
    { config, pkgs, ... }:
    {
      packages.default = config.packages.cmake-purifier;
      # The interactive toolchain is a package so nix shell can expose it
      # without entering the derivation's build environment.
      packages.toolchain = pkgs.buildEnv {
        name = "cmake-purifier-toolchain";
        paths = [
          config.packages.cmake-purifier
          pkgs.cmake
          pkgs.ninja
          pkgs.gnumake
          pkgs.stdenv.cc
          pkgs.clang-tools
        ];
      };
      devShells.default = pkgs.mkShell {
        packages = [
          config.packages.cmake-purifier
          pkgs.cmake
          pkgs.ninja
          pkgs.gnumake
          pkgs.clang-tools
        ];
      };
    };

  partitionedAttrs.checks = "checks";
  partitionedAttrs.formatter = "formatter";

  partitions.formatter = {
    extraInputs = (lib.caisson.pins.flake-compat ../../../tests/dependencies).sources;
    module =
      { inputs, ... }:
      {
        imports = [ inputs.treefmt-nix.flakeModule ];
        perSystem.treefmt.programs.nixfmt.enable = true;
      };
  };

  partitions.checks = {
    extraInputs = (lib.caisson.pins.flake-compat ../../../tests/dependencies).sources;
    module =
      { inputs, self, ... }:
      {
        imports = [ inputs.treefmt-nix.flakeModule ];
        perSystem =
          { pkgs, system, ... }:
          {
            checks = import ../../../tests {
              inherit pkgs;
              goProjector = inputs.go-projector.packages.${system}.default;
              cargoProjector =
                args:
                pkgs.callPackage (inputs.cargo-projector + "/nix/lib/cargo-projections.nix") (
                  args // { purifier = self.lib.purifier; }
                );
              inherit (self.lib) purifier;
              inherit ((pkgs.extend self.overlays.default).cmake-purifier) buildCMakeProject;
              inherit (self.lib.cmake-purifier) readLock;
              inherit (self.packages.${system}) cmake-purifier;
            };
            treefmt.programs.nixfmt.enable = true;
          };
      };
  };

}
