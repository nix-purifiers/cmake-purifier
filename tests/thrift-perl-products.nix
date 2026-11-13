# SPDX-License-Identifier: MIT
{ pkgs, build }:
let
  perl = pkgs.perl.withPackages (ps: [
    ps.BitVector
    ps.ClassAccessor
  ]);
  qualified = pkgs.runCommand "thrift-perl-qualified-schema" { } ''
    cp -R ${./fixtures/thrift-cpp} "$out"
    chmod -R u+w "$out"
    sed -i '1i namespace perl SchemaMain' "$out/schemas/main.thrift"
    sed -i '1i namespace perl SchemaValue' "$out/schemas/common/value.thrift"
  '';
  source2 = pkgs.runCommand "thrift-perl-qualified-schema-v2" { } ''
    cp -R ${qualified} "$out"
    chmod -R u+w "$out"
    substituteInPlace "$out/schemas/common/value.thrift" --replace-fail '1: i32 answer' '2: i32 answer'
  '';
  make =
    src: version:
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
          thriftPerlRuntime = perl;
          thriftPerlPackage = {
            name = "Example::ThriftProof";
            inherit version;
          };
        }
      );
    in
    assert raw.packages.thrift-schema.drvPath == result.packages.thrift-schema.drvPath;
    result.packages.thrift-perl-bindings;
  shadow =
    namespace: service:
    let
      src = pkgs.runCommand "thrift-perl-shadow-${service}" { } ''
        cp -R ${./fixtures/thrift-cpp} "$out"
        chmod -R u+w "$out"
        cat > "$out/schemas/main.thrift" <<'EOF'
        ${pkgs.lib.optionalString (namespace != "") "namespace perl ${namespace}"}
        service ${service} { i32 answer(1: i32 delta) }
        EOF
      '';
    in
    (build {
      inherit src;
      lockFile = ./fixtures/thrift-cpp/cmake-purifier.lock.json;
      pname = "thrift-shadow-schema";
      version = "1.0.0";
      resourceRoots."." = "share/schemas";
      resourceSchema = {
        format = "thrift";
        entrypoints = [ "main.thrift" ];
      };
    }).projections.resources;
  first = make qualified "1.0.0";
  second = make source2 "2.0.0";
in
pkgs.runCommand "thrift-perl-native-cmake-consumers"
  {
    nativeBuildInputs = [ pkgs.python3 ];
    controls = builtins.toJSON {
      sdk = toString pkgs.thrift;
      runtimeProof = "${first.runtime.proof}/runtime.json";
      makefileTool = ../pkgs/thrift-perl-products/Makefile.PL;
      generator = ../pkgs/thrift-perl-products/generate.py;
      cases = [
        {
          resources = toString (shadow "Thrift" "BinaryProtocol");
          module = "Thrift/BinaryProtocol.pm";
        }
        {
          resources = toString (shadow "Class" "Accessor");
          module = "Class/Accessor.pm";
        }
        {
          resources = toString (shadow "" "Config");
          module = "Config.pm";
        }
      ];
    };
    passAsFile = [ "controls" ];
    passthru = { inherit first second; };
  }
  ''
    mkdir -p "$out"
    python ${./thrift-perl/controls.py} "$controlsPath" "$out/runtime-shadow-controls.json"
    ${perl}/bin/perl -I ${first}/lib/perl5 -I ${first.runtime}/lib/perl5 ${./thrift-perl/consume.pl} 0c00010800010000002a0000 > "$out/first.json"
    ${perl}/bin/perl -I ${second}/lib/perl5 -I ${second.runtime}/lib/perl5 ${./thrift-perl/consume.pl} 0c00010800020000002a0000 > "$out/second.json"
  ''
