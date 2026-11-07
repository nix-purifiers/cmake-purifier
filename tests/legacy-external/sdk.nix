{
  pkgs,
  sdkVersion ? "2.8.12.2",
}:
assert builtins.elem sdkVersion [
  "2.8.12.2"
  "3.0.2"
];
pkgs.gcc13Stdenv.mkDerivation {
  pname = "cmake-source-native-epoch";
  version = sdkVersion;
  src = pkgs.fetchurl {
    url =
      if sdkVersion == "2.8.12.2" then
        "https://cmake.org/files/v2.8/cmake-2.8.12.2.tar.gz"
      else
        "https://cmake.org/files/v3.0/cmake-3.0.2.tar.gz";
    hash =
      if sdkVersion == "2.8.12.2" then
        "sha256-jGV06a+ry5/Gb0Y7sfLwUZWNhshcN/zPBn6xpEoSDl4="
      else
        "sha256-a06mHq272b7AzLODwp0fRJbqzBIe96zzfHokd3gFaT4=";
  };
  configurePhase = ''
    runHook preConfigure
    ./bootstrap --prefix="$out" --parallel=4
    runHook postConfigure
  '';
  enableParallelBuilding = true;
  CXXFLAGS = "-std=gnu++98";
  CFLAGS = "-std=gnu99";
  hardeningDisable = [ "format" ];
}
