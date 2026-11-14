# SPDX-License-Identifier: MIT
{
  runCommand,
  ruby,
  thrift,
}:
runCommand "thrift-native-ruby-runtime-gem"
  {
    outputs = [
      "out"
      "proof"
    ];
    nativeBuildInputs = [ ruby ];
    passthru = {
      sdk = thrift;
      sdkSource = thrift.src;
    };
  }
  ''
    export HOME="$TMPDIR/home" SOURCE_DATE_EPOCH=1
    mkdir -p "$HOME" source "$proof"
    cp -r ${thrift.src}/lib/rb/. source/
    chmod -R u+w source
    cd source
    gem build thrift.gemspec --output "$out"
    ${thrift}/bin/thrift --version > "$proof/compiler-version.txt"
    ruby ${./runtime-proof.rb} "$out" "$proof" ${thrift.src}/lib/rb ${thrift} ${ruby}
  ''
