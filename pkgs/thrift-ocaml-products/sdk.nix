# SPDX-License-Identifier: MIT
{
  stdenv,
  thrift,
  scope,
}:
stdenv.mkDerivation {
  pname = "thrift-native-ocaml-sdk";
  version = thrift.version;
  src = thrift.src;
  sourceRoot = "source/lib/ocaml";
  nativeBuildInputs = [
    scope.ocaml
    scope.findlib
    scope.ocamlbuild
    scope.ocaml_oasis
  ];
  preConfigure = "oasis setup";
  configureFlags = [
    "--prefix"
    (builtins.placeholder "out")
  ];
  prefixKey = "";
  OCAMLFIND_DESTDIR = builtins.placeholder "out" + "/lib/ocaml/${scope.ocaml.version}/site-lib";
  preInstall = ''mkdir -p "$OCAMLFIND_DESTDIR"'';
  postInstall = ''
    mkdir -p "$out/original-source" "$out/native-build"
    cp -r ${thrift.src}/lib/ocaml/. "$out/original-source/"
    cp setup.data src/META "$out/native-build/"
  '';
  passthru = {
    inherit scope;
    sdk = thrift;
    sdkSource = thrift.src;
  };
}
