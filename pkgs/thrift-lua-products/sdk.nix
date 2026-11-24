# SPDX-License-Identifier: MIT
{
  stdenv,
  autoreconfHook,
  bison,
  flex,
  pkg-config,
  python3,
  thrift,
  lua,
}:
lua.pkgs.toLuaModule (
  stdenv.mkDerivation {
    pname = "thrift-native-lua-sdk";
    version = thrift.version;
    src = thrift.src;
    nativeBuildInputs = [
      autoreconfHook
      bison
      flex
      pkg-config
      python3
    ];
    buildInputs = [ lua ];
    configureFlags = [
      "--enable-dependency-tracking"
      "--disable-tests"
      "--disable-tutorial"
      "--with-lua=yes"
    ]
    ++ map (name: "--without-${name}") [
      "cpp"
      "c_glib"
      "cl"
      "java"
      "kotlin"
      "python"
      "py3"
      "ruby"
      "haxe"
      "netstd"
      "perl"
      "php"
      "php_extension"
      "dart"
      "erlang"
      "go"
      "d"
      "nodejs"
      "nodets"
      "rs"
    ];
    LUA = "${lua}/bin/lua";
    LUA_INCLUDE = "-I${lua}/include";
    LUA_LIB = "-L${lua}/lib -llua";
    buildPhase = ''
      runHook preBuild
      make -C lib/lua V=1 > native-build.log 2>&1
      cat native-build.log
      runHook postBuild
    '';
    installPhase = ''
        runHook preInstall
        make -C lib/lua install
        mkdir -p "$out/native-build" "$out/runtime-source"
        # Keep the original source inventory separate from generated build metadata.
        cp -r ${thrift.src}/lib/lua/. "$out/runtime-source/"
        cat config.log
      cp config.status lib/lua/Makefile native-build.log "$out/native-build/"
        cp -r lib/lua/src/.deps "$out/native-build/dependencies"
        mkdir -p "$out/share/lua/${lua.luaversion}" "$out/lib/lua/${lua.luaversion}"
        cp ${thrift.src}/lib/lua/*.lua "$out/share/lua/${lua.luaversion}/"
        for declaration in "$out/lib/"*.la; do
          module="''${declaration##*/}"
          module="''${module%.la}"
          ln -s "$out/lib/$module${stdenv.hostPlatform.extensions.sharedLibrary}" \
            "$out/lib/lua/${lua.luaversion}/$module.so"
        done
        cp ${thrift.src}/LICENSE ${thrift.src}/NOTICE "$out/"
        runHook postInstall
    '';
    passthru = {
      inherit lua;
      sdk = thrift;
      sdkSource = thrift.src;
    };
  }
)
