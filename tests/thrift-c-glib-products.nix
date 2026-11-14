# SPDX-License-Identifier: MIT
{ pkgs, build }:
let
  source = pkgs.runCommand "thrift-c-glib-qualified" { } ''
    cp -r ${./fixtures/thrift-cpp} $out
    chmod -R u+w $out
    printf 'namespace c_glib qa\nnamespace cpp qa\nstruct Value { 1: i32 answer = 7 }\n' > $out/schemas/alpha.thrift
    printf 'namespace c_glib qb\nnamespace cpp qb\nstruct Value { 1: i32 answer = 8 }\n' > $out/schemas/beta.thrift
    sed -i '1i include "alpha.thrift"\ninclude "beta.thrift"' $out/schemas/main.thrift
    printf 'service BaseService { i32 base(1: i32 delta) }\n' > $out/schemas/base.thrift
    sed -i '1i include "base.thrift"' $out/schemas/main.thrift
    substituteInPlace $out/schemas/main.thrift --replace-fail 'service AnswerService {' 'service AnswerService extends base.BaseService {'

  '';
  make =
    runtimeBuilder: src:
    let
      args = {
        inherit src;
        lockFile = ./fixtures/thrift-cpp/cmake-purifier.lock.json;
        pname = "thrift-schema";
        version = "1.0.0";
        resourceRoots."." = "share/schemas";
        resourceSchema = {
          format = "thrift";
          entrypoints = [ "main.thrift" ];
        };
      };
      raw = build args;
      result = build (
        args
        // {
          thriftCGLibRuntimeBuilder = runtimeBuilder;
          thriftCGLibPackage = {
            name = "thrift_c_proof";
            version = "1.0.0";
          };
          thriftPackage = {
            name = "thrift_proof";
            version = "1.0.0";
          };
        }
      );
      package = result.packages.thrift-c-glib-bindings;
    in
    assert raw.packages.thrift-schema.drvPath == result.packages.thrift-schema.drvPath;
    {
      generated = package;
      runtime = package.sdkRuntime;
      cpp = result.packages.thrift-bindings;
    };
  source2 = pkgs.runCommand "thrift-c-glib-second-field" { } ''
    cp -r ${source} $out
    chmod -R u+w $out
    substituteInPlace $out/schemas/common/value.thrift --replace-fail '1: i32 answer' '2: i32 answer'
  '';
  check =
    runtimeBuilder:
    let
      versions = [
        (make runtimeBuilder source)
        (make runtimeBuilder source2)
      ];
    in
    pkgs.runCommand "thrift-c-glib-native-consumers"
      {
        nativeBuildInputs = [
          (pkgs.python3.withPackages (ps: [ ps.cffi ]))
          pkgs.pkg-config
          pkgs.stdenv.cc
          pkgs.cmake
          pkgs.ninja
          pkgs.jdk25
        ];
        buildInputs = [ pkgs.thrift ] ++ map (case: case.runtime) versions;
        spec = builtins.toJSON {
          inherit versions;
          generator = ../pkgs/thrift-c-glib-products/generate.py;
          cConsumer = ./thrift-c-glib/consumer.c;
          cppConsumer = ./thrift-c-glib/consumer.cpp;
          ctypesConsumer = ./thrift-c-glib/ctypes-consumer.py;
          javaConsumer = ./thrift-c-glib/GlibConsumer.java;
          cffiConsumer = ./thrift-c-glib/cffi-consumer.py;
          dlLibs = pkgs.lib.optionals (!pkgs.stdenv.hostPlatform.isDarwin) [ "-ldl" ];
        };
        passAsFile = [ "spec" ];
      }
      ''
        export HOME="$TMPDIR/home"
        mkdir -p "$HOME"
        python ${./thrift-c-glib/consume.py} "$specPath" "$out"
      '';
  defaultCheck = check null;
  callerCheck = check (
    args:
    assert toString args.src == toString pkgs.thrift.src && args.version == pkgs.thrift.version;
    (pkgs.callPackage ../pkgs/thrift-c-glib-products/runtime.nix { }).overrideAttrs (_: {
      pname = "thrift-c-glib-caller-sdk";
      src = args.src;
      version = args.version;
    })
  );
in
pkgs.runCommand "thrift-c-glib-projection-proof" { nativeBuildInputs = [ pkgs.python3 ]; } ''
  python - <<'PY'
  import os,json
  from pathlib import Path
  default=json.loads(Path('${defaultCheck}/verification.json').read_text())
  caller=json.loads(Path('${callerCheck}/verification.json').read_text())
  for a,b in zip(default['consumers'],caller['consumers']):
      assert a['model']['runtime']!=b['model']['runtime']
      assert a['model']['sdk']==b['model']['sdk']
      assert a['model']['runtimeHeaderHashes']==b['model']['runtimeHeaderHashes']
      assert a['c'][0]==b['c'][0]
  default['callerRuntime']=caller
  out=Path(os.environ['out']);out.mkdir();(out/'verification.json').write_text(json.dumps(default,sort_keys=True,indent=2)+'\n')
  PY
''
