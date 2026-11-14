{ pkgs, build }:
let
  source1 = pkgs.runCommand "flatbuffers-python-qualified-types" { } ''
    cp -r ${./fixtures/flatbuffers-schema} $out
    chmod -R u+w $out
    echo 'namespace a; table Value { answer:int; }' > "$out/schemas/a.fbs"
    echo 'namespace b; table Value { answer:int; }' > "$out/schemas/b.fbs"
    substituteInPlace "$out/schemas/main.fbs" --replace-fail 'namespace proof;' 'include "a.fbs"; include "b.fbs"; namespace proof;'
  '';
  source2 = pkgs.runCommand "flatbuffers-python-long" { } ''
    cp -r ${source1} $out
    chmod -R u+w $out
    substituteInPlace $out/schemas/common/value.fbs --replace-fail 'answer:int' 'answer:long'
  '';
  make =
    src: bits:
    let
      args = {
        inherit src;
        lockFile = ./fixtures/flatbuffers-schema/cmake-purifier.lock.json;
        pname = "schema-bundle";
        version = "1.0.0";
        resourceRoots."." = "share/schemas";
        resourceSchema = {
          format = "flatbuffers";
          entrypoints = [ "main.fbs" ];
        };
      };
      raw = build args;
      built = build (
        args
        // {
          flatbuffersPackage = {
            name = "schema_proof";
            version = "1.0.0";
          };
          flatbuffersPythonPackage = {
            name = "flatbuffers-proof";
            version = "1.0.0";
          };
        }
      );
      wheel = built.packages.flatbuffers-python-bindings;
    in
    assert raw.packages.schema-bundle.drvPath == built.packages.schema-bundle.drvPath;
    {
      inherit bits;
      package = toString wheel;
      proof = toString wheel.proof;
      repository = toString built.projections.python;
      runtimeRepository = toString wheel.sdkRuntime.projections.python;
      cpp = toString built.packages.flatbuffers-bindings;
    };
  reject =
    options:
    !(builtins.tryEval
      (build {
        src = ./fixtures/flatbuffers-schema;
        flatbuffersPythonPackage = options;
      }).packages.schema-bundle.drvPath
    ).success;
in
assert reject {
  name = "invalid";
  version = "1.0.0";
};
pkgs.runCommand "flatbuffers-python-native-consumers"
  {
    nativeBuildInputs = [
      (pkgs.python3.withPackages (p: [
        p.pip
        p.packaging
      ]))
      pkgs.stdenv.cc
      pkgs.pkg-config
    ];
    buildInputs = [ pkgs.flatbuffers ];
    spec = builtins.toJSON {
      versions = [
        (make source1 32)
        (make source2 64)
      ];
      cppConsumer = ./flatbuffers-python/consumer.cpp;
      generator = ../pkgs/flatbuffers-python-products/generate.py;
    };
    passAsFile = [ "spec" ];
  }
  ''
    export HOME="$TMPDIR/home" PYTHONDONTWRITEBYTECODE=1
    mkdir -p "$HOME"
    python ${./flatbuffers-python/consume.py} "$specPath" "$out"
  ''
