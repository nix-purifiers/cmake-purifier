# SPDX-License-Identifier: MIT
{
  lib,
  runCommand,
  python3,
  thrift,
  ocaml-ng,
  callPackage,
  stdenv,
  purifier,
}:
{ resources, thriftOCamlPackage }:
let
  options = thriftOCamlPackage;
  scope = options.scope or ocaml-ng.ocamlPackages_4_14_unsafe_string;
  valid =
    builtins.isAttrs options
    && builtins.all (
      name:
      builtins.elem name [
        "oasis"
        "scope"
      ]
    ) (builtins.attrNames options)
    && options ? oasis
    && builtins.isAttrs scope
    && scope ? ocaml
    && scope ? findlib
    && scope ? ocamlbuild
    && scope ? ocaml_oasis;
  runtime = callPackage ./sdk.nix { inherit thrift scope; };
  source = runCommand "thrift-generated-ocaml-source" {
    outputs = [
      "out"
      "proof"
    ];
    nativeBuildInputs = [ python3 ];
    spec = builtins.toJSON {
      resources = toString resources;
      sdk = toString thrift;
    };
    passAsFile = [ "spec" ];
  } ''python3 ${./generate.py} "$specPath" "$out" "$proof"'';
  observation = builtins.toJSON {
    source = toString source;
    sourceProof = toString source.proof;
    runtime = toString runtime;
    sdkSource = toString thrift.src;
    ocaml = toString scope.ocaml;
    findlib = toString scope.findlib;
    ocamlVersion = scope.ocaml.version;
    oasis = "${options.oasis}";
  };
  package = stdenv.mkDerivation {
    name = "thrift-generated-ocaml-package";
    src = source;
    nativeBuildInputs = [
      scope.ocaml
      scope.findlib
      scope.ocamlbuild
      scope.ocaml_oasis
      python3
    ];
    propagatedBuildInputs = [ runtime ];
    dontConfigure = true;
    inherit observation;
    passAsFile = [ "observation" ];
    outputs = [
      "out"
      "proof"
    ];
    OCAMLPATH = "${runtime}/lib/ocaml/${scope.ocaml.version}/site-lib";
    OCAMLFIND_DESTDIR = builtins.placeholder "out" + "/lib/ocaml/${scope.ocaml.version}/site-lib";
    buildPhase = ''
      mkdir -p src "$proof"
      cp ${./inspect.ml} "$TMPDIR/native-inspect.ml"
      (cd "$TMPDIR"; ocamlfind ocamlopt -package compiler-libs.common -linkpkg native-inspect.ml -o native-inspect)
      mv ./*.ml ./*.mli src/
      cp ${options.oasis} _oasis
      oasis setup
      ocaml setup.ml -configure --prefix "$out"
      ocaml setup.ml -build
    '';
    installPhase = ''
      mkdir -p "$OCAMLFIND_DESTDIR"
      ocaml setup.ml -install
      cp _oasis "$proof/original_oasis"
      cp setup.data "$proof/"
      cp "$TMPDIR/native-inspect" "$proof/native-inspect"
      python3 ${./observe.py} "$observationPath" "$out" "$proof" "$TMPDIR/native-inspect"
    '';
    passthru = {
      inherit source runtime scope;
      sdk = thrift;
      schemaResources = resources;
    };
  };
in
assert
  valid
  || throw "cmake-purifier: thriftOCamlPackage requires an original authored Oasis definition and compatible original OCaml scope";
package
// {
  projections.ocaml = {
    producer = package;
    inherit runtime scope;
    findlibPath = "${package}/lib/ocaml/${scope.ocaml.version}/site-lib";
    runtimeFindlibPath = "${runtime}/lib/ocaml/${scope.ocaml.version}/site-lib";
  };
}
