# SPDX-License-Identifier: MIT
{ ... }:
{
  perSystem =
    { pkgs, ... }:
    let
      sdks = import ./. { inherit pkgs; };
      tools =
        cmake: cli:
        pkgs.buildEnv {
          name = "cmake-purifier-test-tools";
          paths = [
            cmake
            cli
            pkgs.stdenv.cc
            pkgs.gnumake
            pkgs.clang-tools
            pkgs.python3
            pkgs.jq
            pkgs.git
            pkgs.coreutils
          ]
          ++ pkgs.lib.optionals pkgs.stdenv.hostPlatform.isLinux [
            pkgs.util-linux
            pkgs.iproute2
          ];
        };
      selected = cmake: pkgs.cmake-purifier.overrideScope (_: _: { inherit cmake; });
      sample = import ../real-world/spdlog {
        inherit pkgs;
        inherit (pkgs.cmake-purifier) buildCMakeProject;
      };
    in
    {
      packages =
        pkgs.lib.mapAttrs' (
          version: cmake:
          pkgs.lib.nameValuePair "test-tools-${builtins.replaceStrings [ "." ] [ "_" ] version}" (
            tools cmake (selected cmake).cmake-purifier
          )
        ) sdks
        // pkgs.lib.mapAttrs' (
          version: cmake:
          pkgs.lib.nameValuePair "test-basic-${builtins.replaceStrings [ "." ] [ "_" ] version}"
            ((selected cmake).buildCMakeProject {
              src = ../fixtures/basic;
            }).tests
        ) sdks
        // {
          test-tools = tools pkgs.cmake pkgs.cmake-purifier.cmake-purifier;
          test-spdlog-src = sample.src;
          test-spdlog = sample.tests;
        };
    };
}
