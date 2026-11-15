{ pkgs, build }:
let
  source2 = pkgs.runCommand "thrift-python-schema-v2" { } ''
    cp -r ${./fixtures/thrift-cpp} $out
    chmod -R u+w $out
    substituteInPlace $out/schemas/common/value.thrift --replace-fail '1: i32 answer' '2: i32 answer'
  '';
  make =
    src:
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
      built = build (
        args
        // {
          thriftPackage = {
            name = "thrift_proof";
            version = "1.0.0";
          };
          thriftPythonPackage = {
            name = "thrift-proof";
            version = "1.0.0";
          };
        }
      );
      wheel = built.packages.thrift-python-bindings;
    in
    assert raw.packages.thrift-schema.drvPath == built.packages.thrift-schema.drvPath;
    assert built.projections.python == wheel.projections.python;
    {
      package = toString wheel;
      proof = toString wheel.proof;
      repository = toString wheel.projections.python;
      runtimeRepository = toString wheel.sdkRuntime.projections.python;
      cpp = toString built.packages.thrift-bindings;
    };
  reject =
    options:
    !(builtins.tryEval
      (build {
        src = ./fixtures/thrift-cpp;
        thriftPythonPackage = options;
      }).packages.thrift-schema.drvPath
    ).success;
in
assert reject {
  name = "invalid";
  version = "1.0.0";
};
pkgs.runCommand "thrift-python-native-consumers"
  {
    nativeBuildInputs = [
      (pkgs.python3.withPackages (p: [
        p.pip
        p.packaging
        p.build
        p.setuptools
        p.wheel
      ]))
      pkgs.stdenv.cc
      pkgs.pkg-config
    ];
    buildInputs = [ pkgs.thrift ];
    spec = builtins.toJSON {
      versions = [
        (make ./fixtures/thrift-cpp)
        (make source2)
      ];
      cppConsumer = ./thrift/consumer.cpp;
      generator = ../pkgs/thrift-python-products/generate.py;
      dlLibs = pkgs.lib.optionals (!pkgs.stdenv.hostPlatform.isDarwin) [ "-ldl" ];
    };
    passAsFile = [ "spec" ];
  }
  ''
    export HOME="$TMPDIR/home" PYTHONDONTWRITEBYTECODE=1
    mkdir -p "$HOME"
    python ${./thrift-python/consume.py} "$specPath" "$out"
  ''
