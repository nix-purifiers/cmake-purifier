# SPDX-License-Identifier: MIT
{
  runCommand,
  perl,
  thrift,
  gnumake,
  observer,
}:
runCommand "thrift-native-perl-runtime"
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
      inherit perl;
      sdk = thrift;
      sdkSource = thrift.src;
    };
  }
  ''
    export HOME="$TMPDIR/home"
    mkdir -p "$HOME" "$proof" source
    cp -R ${thrift.src}/lib/perl/. source/
    chmod -R u+w source
    cd source
    perl Makefile.PL INSTALL_BASE="$out"
    make
    make install
    cp MYMETA.json "$proof/native-MYMETA.json"
    compilerVersion="$(${thrift}/bin/thrift --version)"
    perl -I "$out/lib/perl5" ${./runtime-proof.pl} MYMETA.json "$compilerVersion" > "$proof/runtime.json"
    ${observer.command}
  ''
