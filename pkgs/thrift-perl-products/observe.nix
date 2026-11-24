# SPDX-License-Identifier: MIT
{
  lib,
  python3,
  purifier,
  cartonPurifierSource,
  perl,
}:
{
  source,
  sourceRoot,
  dependencies ? [ ],
  probeModules ? [ ],
}:
let
  helpers = cartonPurifierSource + "/pkgs/build-carton-project";
  sdk = import (helpers + "/perl-library-sdk.nix") { inherit lib purifier; } perl;
  suppliers = import (helpers + "/perl-library-inputs.nix") { inherit lib purifier; } dependencies;
  inputs =
    supplier:
    supplier.declared.runtimeInputPaths
    ++ [
      {
        path = supplier.declared.sourcePath;
        identity = supplier.declared.sourceIdentity;
      }
    ]
    ++ map (output: { inherit (output) path identity; }) supplier.declared.producerOutputs
    ++ lib.concatMap inputs supplier.declared.suppliers;
  roots =
    supplier:
    map (root: "${supplier.declared.producerPath}/${root}") supplier.declared.roots
    ++ lib.concatMap roots supplier.declared.suppliers;
  request = sdk // {
    sourcePath = toString source;
    sourceIdentity = purifier.inputIdentity source;
    roots = [ "lib/perl5" ];
    sourceRoots."lib/perl5" = sourceRoot;
    xsProbeModules = probeModules;
    allowedRoots = lib.unique (
      sdk.allowedRoots
      ++ [ (toString source) ]
      ++ lib.concatMap (supplier: supplier.declared.allowedRoots) suppliers
    );
    dependencyInputPaths = lib.unique (lib.concatMap inputs suppliers);
    dependencyLibraryRoots = lib.unique (lib.concatMap roots suppliers);
    dependencyCatalogs = map (supplier: {
      path = supplier.catalog;
      identity = supplier.declared.producerIdentity;
    }) suppliers;
  };
in
{
  requestJSON = builtins.toJSON request;
  command = ''
    ${python3}/bin/python3 -B ${./observe.py} "$requestJSONPath" "$out" "$proof" ${cartonPurifierSource}/carton_purifier
  '';
}
