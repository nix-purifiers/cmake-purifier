# SPDX-License-Identifier: MIT
{
  pkgs,
  purifier,
  haxelibPurifierSource,
}:
{
  thrift,
  haxe,
  nativeHaxelib,
  neko,
}:
let
  scope = pkgs.lib.makeScope pkgs.newScope (self: {
    inherit haxe nativeHaxelib neko;
    sdkVersion = import (haxelibPurifierSource + "/pkgs/build-haxelib-project/sdk-version.nix") {
      nixpkgsSrc = pkgs.path;
    };
    toolchain = self.callPackage (
      haxelibPurifierSource + "/pkgs/build-haxelib-project/toolchain.nix"
    ) { };
    buildHaxeProject =
      self.callPackage (haxelibPurifierSource + "/pkgs/build-haxelib-project/default.nix")
        {
          inherit purifier;
        };
  });
  project = scope.buildHaxeProject {
    src = thrift.src + "/lib/haxe";
    lockFile = ./sdk.lock.json;
    buildCommand = "";
    doCheck = false;
  };
  producer =
    pkgs.runCommand "original-native-thrift-haxelib-sdk"
      {
        nativeBuildInputs = [ pkgs.python3 ];
        request = builtins.toJSON {
          source = "${thrift.src}/lib/haxe";
          lock = ./sdk.lock.json;
          repository = "${project.packages.environment}/repository";
          releaseTool = "${haxelibPurifierSource}/haxelib_purifier/release.py";
          haxelib = "${nativeHaxelib}/bin/haxelib";
          inspect = "${nativeHaxelib}/bin/haxelib-purifier-inspect";
        };
        passAsFile = [ "request" ];
      }
      ''
        export HOME="$TMPDIR/home"
        mkdir -p "$HOME"
        python3 ${./install-sdk.py} "$requestPath" "$out"
      '';
in
{
  inherit
    producer
    haxe
    nativeHaxelib
    neko
    ;
  source = thrift.src;
  installedRoot = "${producer}/sdk-source";
  repository = "${producer}/repository";
  dependencies = [ project.packages.environment ];
}
