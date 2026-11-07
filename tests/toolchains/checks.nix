# SPDX-License-Identifier: MIT
{ pkgs, buildCMakeProject }:
let
  sdks = import ./. { inherit pkgs; };
  sample = import ../real-world/spdlog { inherit pkgs buildCMakeProject; };
in
pkgs.lib.mapAttrs' (
  version: cmake:
  pkgs.lib.nameValuePair "sdk-basic-${builtins.replaceStrings [ "." ] [ "_" ] version}"
    ((buildCMakeProject.override { inherit cmake; }) {
      src = ../fixtures/basic;
      postConfigure = ''
        test "$(cmake --version | head -1)" = 'cmake version ${version}'
        grep -Fx 'CMAKE_COMMAND:INTERNAL=${cmake}/bin/cmake' CMakeCache.txt
      '';
    }).tests
) sdks
// {
  real-world-spdlog = sample.tests;
  real-world-spdlog-consumer =
    pkgs.runCommand "spdlog-ordinary-installed-consumer"
      {
        nativeBuildInputs = [
          pkgs.cmake
          pkgs.stdenv.cc
          pkgs.gnumake
        ];
      }
      ''
        cmake -S ${../real-world/spdlog/consumer} -B build -DCMAKE_PREFIX_PATH=${sample.tests}
        cmake --build build -j2
        ./build/consumer
        if cmake -S ${../real-world/spdlog/consumer} -B missing \
          -DCMAKE_FIND_ROOT_PATH="$TMPDIR/missing" \
          -DCMAKE_FIND_ROOT_PATH_MODE_PACKAGE=ONLY > missing.log 2>&1; then
          echo 'consumer configured without its producer' >&2
          exit 1
        fi
        grep -q spdlog missing.log
        mkdir $out
        cp missing.log $out/
        cp build/consumer $out/
      '';
}
