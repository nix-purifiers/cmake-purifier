{ pkgs, build }:
let
  changed = pkgs.runCommand "thrift-lua-field2" { } ''
    cp -r ${./fixtures/thrift-cpp} "$out"
    chmod -R u+w "$out"
    sed -i 's/1: value.Value/2: value.Value/' "$out/schemas/main.thrift"
  '';
  qualified = pkgs.runCommand "thrift-lua-qualified" { } ''
    cp -r ${./fixtures/thrift-cpp} "$out"
    chmod -R u+w "$out"
    sed -i '1i namespace lua proof.main' "$out/schemas/main.thrift"
    sed -i '1i namespace lua proof.common' "$out/schemas/common/value.thrift"
  '';
  package =
    src:
    (build {
      inherit src;
      lockFile = ./fixtures/thrift-cpp/cmake-purifier.lock.json;
      pname = "thrift-lua-schema";
      version = "1.0.0";
      resourceRoots."." = "share/schemas";
      resourceSchema = {
        format = "thrift";
        entrypoints = [ "main.thrift" ];
      };
      thriftLuaPackage = { };
    }).packages.thrift-lua-bindings;
  first = package ./fixtures/thrift-cpp;
  second = package changed;
  namespaced = package qualified;
  consumer =
    product: main: value: field:
    pkgs.runCommand "ordinary-native-thrift-lua-consumer" { } ''
      mkdir "$out"
      export LUA_PATH="${product.projections.lua.modulePath}/?.lua"
      export LUA_CPATH=""
      ${product.projections.lua.runtime}/bin/lua ${./thrift-lua/consume.lua} "$out/native-modules.tsv" ${main} ${value} ${toString field} > "$out/consumer.txt"
      cp ${product.proof}/native-lua.json "$out/package.json"
    '';
  a = consumer first "main" "value" 1;
  b = consumer second "main" "value" 2;
  c = consumer namespaced "proof.main" "proof.common" 1;
  standard = pkgs.runCommand "standard-nix-native-thrift-lua-consumer" { } ''
    mkdir "$out"
    export LUA_PATH="" LUA_CPATH=""
    ${
      first.lua.withPackages (_: [ first ])
    }/bin/lua ${./thrift-lua/consume.lua} "$out/native-modules.tsv" main value 1 > "$out/consumer.txt"
  '';

  resourceCase =
    script:
    (package (
      pkgs.runCommand "invalid-native-lua-schema" { } ''
        cp -r ${./fixtures/thrift-cpp} "$out"
        chmod -R u+w "$out"
        ${script}
      ''
    )).schemaResources;
  sdkShadow = resourceCase ''printf '\nstruct TBinaryProtocol {1:i32 answer}\n' >> "$out/schemas/main.thrift"'';
  builtinShadow = resourceCase ''printf '\nstruct _G {1:i32 answer}\n' >> "$out/schemas/main.thrift"'';
  globalsCollision = resourceCase ''
    printf '\nstruct Clash {1:i32 answer}\n' >> "$out/schemas/main.thrift"
    printf '\nstruct Clash {1:i32 answer}\n' >> "$out/schemas/common/value.thrift"
  '';
  moduleCollision = resourceCase ''
    sed -i '1i namespace lua collision' "$out/schemas/main.thrift"
    sed -i '1i namespace lua collision' "$out/schemas/common/value.thrift"
  '';
  invalidSDK =
    kind:
    pkgs.runCommand "invalid-original-native-lua-sdk-${kind}" { nativeBuildInputs = [ pkgs.python3 ]; }
      ''
        python3 ${./thrift-lua/invalid-sdk.py} ${first.runtime} "$out" ${kind}
      '';
  badABI = build {
    src = ./fixtures/thrift-cpp;
    pname = "invalid-lua-abi";
    version = "1";
    resourceRoots."." = "share/schemas";
    resourceSchema = {
      format = "thrift";
      entrypoints = [ "main.thrift" ];
    };
    thriftLuaPackage.lua = pkgs.lua5_3;
  };

in
assert !(builtins.tryEval badABI.packages.thrift-lua-bindings.drvPath).success;
pkgs.runCommand "native-thrift-lua-consumers"
  {
    nativeBuildInputs = [ pkgs.python3 ];
    controls = builtins.toJSON {
      generation = builtins.fromJSON (builtins.unsafeDiscardStringContext first.source.spec);
      installation = builtins.fromJSON (builtins.unsafeDiscardStringContext first.spec);
      source = toString first.source;
      generator = ../pkgs/thrift-lua-products/generate.py;
      installer = ../pkgs/thrift-lua-products/install.py;
      cases = [
        {
          phase = "generate";
          resources = toString moduleCollision;
          diagnostic = "native generated Lua output collision";
        }
        {
          phase = "install";
          resources = toString sdkShadow;
          diagnostic = "generated Lua global shadows original or earlier native binding";
        }
        {
          phase = "install";
          resources = toString builtinShadow;
          diagnostic = "generated Lua global shadows original or earlier native binding";
        }
        {
          phase = "install";
          resources = toString globalsCollision;
          diagnostic = "generated Lua global shadows original or earlier native binding";
        }
      ];
      runtimeCases = [
        {
          override.runtime = toString (invalidSDK "bytes");
          diagnostic = "original native Lua SDK source changed or is incomplete";
        }
        {
          override.runtime = toString (invalidSDK "library");
          diagnostic = "original native Lua SDK shared library is missing";
        }
        {
          override = {
            lua = toString pkgs.lua5_3;
            luaVersion = pkgs.lua5_3.version;
          };
          diagnostic = "native Lua SDK was built for a different original interpreter";
        }
      ];
    };
    nativeInputs = first.spec + first.source.spec;
    passAsFile = [ "controls" ];
  }
  ''
      mkdir "$out"
      cp -r ${a} "$out/first"
      cp -r ${b} "$out/second"
      cp -r ${c} "$out/qualified"
      cp -r ${standard} "$out/standard"
      python3 ${./thrift-lua/byte-joins.py} ${first.source} ${first.source.proof} ${first} ${first.proof} ${a} > "$out/first-byte-joins.json"
    python3 ${./thrift-lua/byte-joins.py} ${second.source} ${second.source.proof} ${second} ${second.proof} ${b} > "$out/second-byte-joins.json"
    python3 ${./thrift-lua/byte-joins.py} ${namespaced.source} ${namespaced.source.proof} ${namespaced} ${namespaced.proof} ${c} > "$out/qualified-byte-joins.json"
    python3 ${./thrift-lua/controls.py} "$controlsPath" "$out/rejections.json"
  ''
