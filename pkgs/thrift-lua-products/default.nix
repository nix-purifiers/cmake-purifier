# SPDX-License-Identifier: MIT
{
  lib,
  runCommand,
  python3,
  thrift,
  lua5_4,
  callPackage,
  purifier,
}:
{ resources, thriftLuaPackage }:
let
  options = thriftLuaPackage;
  lua = options.lua or lua5_4;
  valid =
    builtins.isAttrs options
    && builtins.all (key: key == "lua") (builtins.attrNames options)
    && lib.isDerivation lua
    && !(lua ? lua)
    && lua.luaversion == "5.4";
  runtime = callPackage ./sdk.nix { inherit lua thrift; };
  environment = lua.withPackages (_: [ runtime ]);
  source =
    runCommand "thrift-generated-lua-source"
      {
        outputs = [
          "out"
          "proof"
        ];
        nativeBuildInputs = [ python3 ];
        spec = builtins.toJSON {
          resources = toString resources;
          sdk = toString thrift;
        };
        passAsFile = [ "spec" ];
      }
      ''
        python3 ${./generate.py} "$specPath" "$out" "$proof"
      '';
  package = lua.pkgs.toLuaModule (
    runCommand "thrift-generated-lua-package"
      {
        outputs = [
          "out"
          "proof"
        ];
        nativeBuildInputs = [ python3 ];
        propagatedBuildInputs = [ runtime ];
        spec = builtins.toJSON {
          runtime = toString runtime;
          sdkSource = toString thrift.src;
          sourceProof = toString source.proof;
          lua = toString lua;
          luaVersion = lua.version;
          abi = lua.luaversion;
          loader = ./load.lua;
        };
        passAsFile = [ "spec" ];
        passthru = {
          inherit source runtime lua;
          sdk = thrift;
          schemaResources = resources;
          projectInputs = {
            compiler = purifier.inputIdentity thrift;
            sdkSource = purifier.inputIdentity thrift.src;
            interpreter = purifier.inputIdentity lua;
            sdkRuntime = purifier.inputIdentity runtime;
            schema = purifier.inputIdentity resources;
          };
        };
      }
      ''
        mkdir -p "$out/share/lua/${lua.luaversion}"
        python3 ${./install.py} "$specPath" ${source} "$out/share/lua/${lua.luaversion}" "$proof"
        cp ${source.proof}/thrift-lua.json "$proof/"
        mkdir -p "$out/nix-support"
        cp "$proof/native-lua.json" "$out/nix-support/native-lua.json"
        printf '%s\n' ${runtime} > "$out/nix-support/propagated-build-inputs"
      ''
  );
in
assert
  valid || throw "cmake-purifier: thriftLuaPackage accepts an original unwrapped Lua 5.4 interpreter";
package
// {
  projections.lua = {
    producer = package;
    runtime = environment;
    modulePath = "${package}/share/lua/${lua.luaversion}";
    moduleCatalog = "${package}/nix-support/native-lua.json";
    abi = lua.luaversion;
    inherit lua;
  };
}
