# SPDX-License-Identifier: MIT
{ cmakeSource }:
let
  f = builtins.getFlake "path:${cmakeSource}";
  carton = builtins.getFlake (builtins.unsafeDiscardStringContext "path:${f.inputs.carton-purifier}");
  pkgs = import f.inputs.nixpkgs {
    system = builtins.currentSystem;
    overlays = [ f.overlays.default ];
  };
  cartonPkgs = import carton.inputs.nixpkgs {
    system = builtins.currentSystem;
    overlays = [ carton.overlays.default ];
  };
  perl = cartonPkgs.perl.withPackages (ps: [
    ps.BitVector
    ps.ClassAccessor
  ]);
  scope = cartonPkgs.carton-purifier.overrideScope (_: _: { inherit perl; });
  source = pkgs.runCommand "carton-owned-thrift-perl-schemas" { } ''
    cp -R ${f.outPath + "/tests/fixtures/thrift-cpp"} "$out"
    chmod -R u+w "$out"
    sed -i '1i namespace perl SchemaMain' "$out/schemas/main.thrift"
    sed -i '1i namespace perl SchemaValue' "$out/schemas/common/value.thrift"
  '';
  product = pkgs.cmake-purifier.buildCMakeProject {
    src = source;
    lockFile = f.outPath + "/tests/fixtures/thrift-cpp/cmake-purifier.lock.json";
    pname = "thrift-schema";
    version = "1.0.0";
    resourceRoots."." = "share/schemas";
    resourceSchema = {
      format = "thrift";
      entrypoints = [ "main.thrift" ];
    };
    thriftPerlRuntime = perl;
    thriftPerlPackage = {
      name = "Example::ThriftProof";
      version = "1.0.0";
    };
  };
in
{
  packages.${builtins.currentSystem} = {
    default = product.packages.thrift-perl-bindings;
    cli = scope.cli;
  };
}
