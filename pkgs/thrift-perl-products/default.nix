# SPDX-License-Identifier: MIT
{
  lib,
  runCommand,
  python3,
  perl,
  thrift,
  gnumake,
  purifier,
  cartonPurifierSource,
  callPackage,
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
  observe = import ./observe.nix {
    inherit
      lib
      python3
      purifier
      cartonPurifierSource
      perl
      ;
  };
  project = callPackage (
    cartonPurifierSource + "/pkgs/build-carton-project/project-perl-library.nix"
  ) { inherit purifier; };
  nativeRuntime = import ./runtime.nix {
    inherit
      runCommand
      perl
      thrift
      gnumake
      ;
    observer = observe {
      source = thrift.src;
      sourceRoot = "lib/perl/lib";
      probeModules = [ "Thrift" ];
    };
  };
  runtimeProjection = project {
    producer = nativeRuntime;
    source = thrift.src;
    roots = [ "lib/perl5" ];
    sourceRoots."lib/perl5" = "lib/perl/lib";
    observation = "${nativeRuntime.proof}/observation.json";
    applicationPerl = perl;
  };
  runtime = nativeRuntime.overrideAttrs (old: {
    passthru = (old.passthru or { }) // {
      projections.perl = runtimeProjection;
    };
  });
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
  observer = observe {
    inherit source;
    sourceRoot = "lib";
    dependencies = [ runtime ];
  };
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
        requestJSON = observer.requestJSON;
        passAsFile = [ "requestJSON" ];
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
        ${observer.command}
      '';
  projection = project {
    producer = installed;
    inherit source;
    roots = [ "lib/perl5" ];
    sourceRoots."lib/perl5" = "lib";
    observation = "${installed.proof}/observation.json";
    dependencies = [ runtime ];
    applicationPerl = perl;
  };
in
assert lib.assertMsg valid "thriftPerlPackage requires explicit Perl distribution name and version";
installed.overrideAttrs (old: {
  passthru = (old.passthru or { }) // {
    projections.perl = projection;
  };
})
