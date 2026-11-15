# SPDX-License-Identifier: MIT
{
  runCommand,
  python3,
  jdk,
  gradle,
}:
{ repository }:
let
  nativeGradle = gradle.unwrapped or gradle;
in
runCommand "native-maven-ivy-repository"
  {
    outputs = [
      "out"
      "proof"
    ];
    nativeBuildInputs = [
      python3
      jdk
    ];
    passthru.catalog = repository.catalog;
  }
  ''
    export HOME="$TMPDIR/home"
    mkdir -p "$HOME" "$proof"
    jars=( ${nativeGradle}/libexec/gradle/lib/plugins/ivy-*.jar )
    test "''${#jars[@]}" = 1
    ivy="''${jars[0]}"
    javac -cp "$ivy" -d . ${./.}/Convert.java
    java -cp ".:$ivy" Convert ${repository} "$out" "$TMPDIR/ivy-cache" > "$proof/native-conversion.log"
    python ${./verify.py} ${repository} "$out" "$proof" "$ivy"
  ''
