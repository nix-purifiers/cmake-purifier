# SPDX-License-Identifier: MIT
{
  pkgs,
  build,
  dependencies,
}:
let
  source2 = pkgs.runCommand "thrift-ruby-schema-v2" { } ''
    cp -r ${./fixtures/thrift-cpp} "$out"
    chmod -R u+w "$out"
    substituteInPlace "$out/schemas/common/value.thrift" --replace-fail '1: i32 answer' '2: i32 answer'
  '';
  qualifiedSource = pkgs.runCommand "thrift-ruby-qualified-schema" { } ''
        cp -r ${./fixtures/thrift-cpp} "$out"
        chmod -R u+w "$out"
        cat > "$out/schemas/first.thrift" <<'EOF'
    namespace cpp first_value
    namespace rb First
    struct Value { 1: i32 answer }
    service BaseService { i32 base_answer(1:i32 delta) }
    EOF
        cat > "$out/schemas/second.thrift" <<'EOF'
    namespace cpp second_value
    namespace rb Second
    struct Value { 1: i32 answer }
    EOF
        cat > "$out/schemas/root.thrift" <<'EOF'
    include "first.thrift"
    include "second.thrift"
    namespace cpp root_value
    namespace rb Root
    struct Pair { 1: first.Value left, 2: second.Value right }
    service AnswerService extends first.BaseService { i32 answer(1:i32 delta) }
    EOF
  '';
  make =
    src: entry:
    let
      args = {
        inherit src;
        lockFile = ./fixtures/thrift-cpp/cmake-purifier.lock.json;
        pname = "thrift-schema";
        version = "1.0.0";
        resourceRoots."." = "share/schemas";
        resourceSchema = {
          format = "thrift";
          entrypoints = [ entry ];
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
          thriftRubyPackage = {
            name = "thrift-ruby-proof";
            version = "1.0.0";
          };
          thriftRubyDependencies = dependencies;
        }
      );
      gem = built.packages.thrift-ruby-bindings;
    in
    assert raw.packages.thrift-schema.drvPath == built.packages.thrift-schema.drvPath;
    assert built.projections.rubygems == gem.projections.rubygems;
    {
      package = toString gem;
      proof = toString gem.proof;
      repository = toString gem.projections.rubygems;
      cpp = toString built.packages.thrift-bindings;
    };
in
pkgs.runCommand "thrift-ruby-native-consumers"
  {
    nativeBuildInputs = [
      pkgs.ruby
      pkgs.python3
      pkgs.stdenv.cc
      pkgs.pkg-config
    ];
    buildInputs = [ pkgs.thrift ];
    spec = builtins.toJSON {
      versions = [
        (make ./fixtures/thrift-cpp "main.thrift")
        (make source2 "main.thrift")
      ];
      qualified = make qualifiedSource "root.thrift";
      qualifiedConsumer = ./thrift-ruby/qualified.rb;
      qualifiedCpp = ./thrift-ruby/qualified.cpp;
      cppConsumer = ./thrift/consumer.cpp;
      generator = ../pkgs/thrift-ruby-products/generate.py;
      bindingsTool = ../pkgs/thrift-ruby-products/bindings.rb;
      packageTool = ../pkgs/thrift-ruby-products/package.rb;
      ruby = toString pkgs.ruby;
      sdkSource = toString pkgs.thrift.src;
      rubyConsumer = ./thrift-ruby/consume.rb;
      dlLibs = pkgs.lib.optionals (!pkgs.stdenv.hostPlatform.isDarwin) [ "-ldl" ];
    };
    passAsFile = [ "spec" ];
  }
  ''
    export HOME="$TMPDIR/home" PYTHONDONTWRITEBYTECODE=1
    mkdir -p "$HOME"
    python ${./thrift-ruby/consume.py} "$specPath" "$out"
  ''
