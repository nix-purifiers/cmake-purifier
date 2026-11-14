# SPDX-License-Identifier: MIT
{ python3, flatbuffers }:
{ runtimeBuilder }:
runtimeBuilder {
  pname = "flatbuffers-native-java-runtime";
  inherit (flatbuffers) src version;
  sourceRoot = "source/java";
  nativeBuildInputs = [ python3 ];
  doCheck = false;
  postPatch = ''
    python ${./configure-runtime.py} pom.xml
  '';
  mvnParameters = "-Dmaven.test.skip=true -Dmaven.javadoc.skip=true -Dgpg.skip=true -Dproject.build.outputTimestamp=1980-01-01T00:00:02Z";
  installPhase = ''
    mkdir -p "$out"
    cp target/*.jar "$out/"
    cp pom.xml "$out/pom.xml"
    cp sdk-original.pom "$out/sdk-original.pom"
  '';
}
