# SPDX-License-Identifier: MIT
{
  lib,
  runCommand,
  python3,
  perl,
  thrift,
  gnumake,
}:
{ resources, thriftPerlPackage }:
let
  options = thriftPerlPackage;
  valid =
    builtins.isAttrs options
    &&
      builtins.attrNames options == [
        "name"
        "version"
      ]
    && builtins.isString options.name
    && builtins.match "[A-Za-z_][A-Za-z0-9_]*(::[A-Za-z_][A-Za-z0-9_]*)*" options.name != null
    && builtins.isString options.version
    && builtins.match "[0-9]+(\\.[0-9]+)*" options.version != null;
  runtime = import ./runtime.nix {
    inherit
      runCommand
      perl
      thrift
      gnumake
      ;
  };
  source =
    runCommand "thrift-generated-perl-source"
      {
        outputs = [
          "out"
          "proof"
        ];
        nativeBuildInputs = [ python3 ];
        spec = builtins.toJSON {
          resources = toString resources;
          sdk = toString thrift;
          runtimeProof = "${runtime.proof}/runtime.json";
          makefileTool = ./Makefile.PL;
          inherit (options) name version;
        };
        passAsFile = [ "spec" ];
      }
      ''
        python ${./generate.py} "$specPath" "$out" "$proof"
      '';
  installed =
    runCommand "thrift-generated-perl-library"
      {
        outputs = [
          "out"
          "proof"
        ];
        nativeBuildInputs = [
          perl
          gnumake
        ];
        passthru = {
          inherit source runtime perl;
          schemaResources = resources;
          sdk = thrift;
        };
      }
      ''
        export HOME="$TMPDIR/home" PERL5LIB="${runtime}/lib/perl5"
        mkdir -p "$HOME" "$proof" work
        cp -R ${source}/. work/
        chmod -R u+w work
        cd work
        perl Makefile.PL INSTALL_BASE="$out"
        make
        make install
        cp MYMETA.json "$proof/native-MYMETA.json"
        cp ${source.proof}/thrift-perl.json "$proof/thrift-perl.json"
      '';
in
assert lib.assertMsg valid "thriftPerlPackage requires explicit Perl distribution name and version";
installed
