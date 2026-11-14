# SPDX-License-Identifier: MIT
{
  inputs.caisson.url = "github:nix-caisson/caisson";
  inputs.flake-parts.url = "github:hercules-ci/flake-parts";
  # Same channel as the main flake, so dev-partition evals agree with the
  # exported pkgSet.
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  inputs.cargo-projector = {
    url = "git+https://github.com/nix-purifiers/cargo-purifier?ref=refs/tags/v0.1.9";
    flake = false;
  };
  inputs.npm-projector.url = "git+https://github.com/nix-purifiers/npm-purifier?ref=refs/tags/v0.1.13";
  inputs.go-projector.url = "github:nix-purifiers/go-purifier/v0.1.6";
  inputs.go-projector.inputs.nixpkgs.follows = "nixpkgs";
  inputs.gradle-projector = {
    url = "git+https://github.com/nix-purifiers/gradle-purifier?ref=refs/tags/v0.1.23";
    flake = false;
  };
  inputs.treefmt-nix.url = "github:numtide/treefmt-nix";
  inputs.treefmt-nix.inputs.nixpkgs.follows = "nixpkgs";
  outputs = { ... }: { };
}
