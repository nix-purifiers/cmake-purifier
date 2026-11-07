# SPDX-License-Identifier: MIT
# A fixture consumer supplies its old SDK; the purifier default stays modern.
{
  sdkVersion ? "2.8.12.2",
}:
let
  flake = builtins.getFlake ("path:" + toString ../..);
  pkgs = import flake.inputs.nixpkgs {
    system = "x86_64-linux";
    overlays = [ flake.overlays.default ];
  };
  sdk = import ./sdk.nix { inherit pkgs sdkVersion; };
  makeScope =
    selected:
    pkgs.cmake-purifier.overrideScope (
      final: prev: {
        cmake = selected;
        nativeProfile = "legacy-external-v1";
        legacyProjectName = "legacy_native";
        legacySdkAdapter = {
          version = 1;
          package = selected;
          moduleRoot = "share/cmake-${pkgs.lib.versions.majorMinor sdkVersion}";
          source = {
            url =
              if sdkVersion == "2.8.12.2" then
                "https://cmake.org/files/v2.8/cmake-2.8.12.2.tar.gz"
              else
                "https://cmake.org/files/v3.0/cmake-3.0.2.tar.gz";
            sha256 =
              if sdkVersion == "2.8.12.2" then
                "8c6574e9afabcb9fc66f463bb1f2f051958d86c85c37fccf067eb1a44a120e5e"
              else
                "6b4ea61eadbbd9bec0ccb383c29d1f4496eacc121ef7acf37c7a24777805693e";
          };
        };
      }
    );
  scope = makeScope sdk;
  foreignSdk = pkgs.runCommand "cmake-legacy-foreign-wrapper" { version = sdk.version; } ''
    mkdir -p $out/bin
    cat > $out/bin/cmake <<'WRAPPER'
    #!${pkgs.runtimeShell}
    exec ${sdk}/bin/cmake "$@"
    WRAPPER
    chmod +x $out/bin/cmake
    ln -s ${sdk}/bin/ctest $out/bin/ctest
    ln -s ${sdk}/share $out/share
  '';
in
{
  inherit sdk scope pkgs;
  foreignCli = (makeScope foreignSdk).cmake-purifier;
  cli = scope.cmake-purifier;
  modernCli = pkgs.cmake-purifier.cmake-purifier;
  modernCmake = pkgs.cmake;
  toolchain = pkgs.buildEnv {
    name = "legacy-cmake-native-fixture-toolchain";
    paths = [
      pkgs.stdenv.cc
      pkgs.gnumake
      pkgs.python3
      pkgs.util-linux
      pkgs.iproute2
      pkgs.ripgrep
    ];
  };
}
