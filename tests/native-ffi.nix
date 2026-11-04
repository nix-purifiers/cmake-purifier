# SPDX-License-Identifier: MIT
{ pkgs, buildCMakeProject }:
let
  src = ./fixtures/native-ffi;
  body = {
    version = 3;
    project = {
      name = "purifier_ffi";
      version = "1.0.0";
    };
    definitionHash = import ../nix/lib/definition-hash.nix src;
    cmakeFlags = [ ];
    artifacts = [ ];
    dependencies = [ ];
    gitCheckouts = [ ];
    outputs = {
      files = [
        "lib/libproof${pkgs.stdenv.hostPlatform.extensions.sharedLibrary}"
        "include/proof.h"
        "lib/pkgconfig/proof.pc"
      ];
      targets.proof = {
        type = "SHARED_LIBRARY";
        files = [ "lib/libproof${pkgs.stdenv.hostPlatform.extensions.sharedLibrary}" ];
      };
    };
  };
  lockFile = pkgs.writeText "cmake-purifier.lock.json" (
    builtins.toJSON (
      body
      // {
        contentHash = "sha256:" + builtins.hashString "sha256" (builtins.toJSON body);
      }
    )
  );
  built = buildCMakeProject {
    inherit src lockFile;
    buildInputs = [ pkgs.zlib ];
  };
  ffi = built.packages.purifier_ffi.projections;
  advanced = buildCMakeProject {
    src = pkgs.runCommand "advanced-native-producer" { } ''
      cp -r ${src} "$out"
      chmod -R u+w "$out"
      substituteInPlace "$out/proof.c" --replace-fail '42' '43'
    '';
    inherit lockFile;
    buildInputs = [ pkgs.zlib ];
  };
  advancedFfi = advanced.packages.purifier_ffi.projections;
in
assert built.fetches == [ ];
assert advancedFfi.native.drvPath != ffi.native.drvPath;
pkgs.runCommand "cmake-native-foreign-consumers"
  {
    nativeBuildInputs = [
      pkgs.python3
      pkgs.jdk
      pkgs.pkg-config
      pkgs.stdenv.cc
    ];
  }
  ''
    export PYTHONPATH=${ffi.python-ffi}
    python - <<'PY'
    import json, purifier_native
    import runpy
    assert purifier_native.load("proof").answer() == 42
    changed = runpy.run_path('${advancedFfi.python-ffi}/purifier_native.py')
    assert changed['load']('proof').answer() == 43
    assert purifier_native.load("proof").answer() == 42
    catalog = json.load(open("${ffi.native.catalog}"))
    assert catalog["system"] == "${pkgs.stdenv.hostPlatform.system}"
    assert catalog["includeDirectories"] and catalog["pkgConfigDirectories"]
    open("library-path", "w").write(catalog["libraries"]["proof"])
    PY
    cat > Foreign.java <<'JAVA'
    import java.lang.foreign.*;
    public class Foreign {
      public static void main(String[] args) throws Throwable {
        try (var arena = Arena.ofConfined()) {
          var symbol = SymbolLookup.libraryLookup(args[0], arena).find("answer").orElseThrow();
          var call = Linker.nativeLinker().downcallHandle(symbol, FunctionDescriptor.of(ValueLayout.JAVA_INT));
          if ((int) call.invokeExact() != 42) throw new AssertionError();
        }
      }
    }
    JAVA
    javac --enable-preview --release ${pkgs.lib.versions.major pkgs.jdk.version} Foreign.java
    java --enable-preview --enable-native-access=ALL-UNNAMED Foreign "$(cat library-path)"
    export PKG_CONFIG_PATH=${built.packages.purifier_ffi}/lib/pkgconfig
    cat > ordinary.c <<'C'
    #include <proof.h>
    int main(void) { return answer() == 42 ? 0 : 1; }
    C
    $CC ordinary.c $(pkg-config --cflags --libs proof) -o ordinary
    ./ordinary
    touch $out
  ''
