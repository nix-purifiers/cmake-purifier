# SPDX-License-Identifier: MIT
{ thrift, glib }:
thrift.overrideAttrs (old: {
  pname = "thrift-c-glib-native-sdk";
  buildInputs = old.buildInputs ++ [ glib ];
  propagatedBuildInputs = old.propagatedBuildInputs ++ [ glib ];
  cmakeFlags = old.cmakeFlags ++ [
    "-DBUILD_COMPILER=OFF"
    "-DBUILD_CPP=OFF"
    "-DBUILD_C_GLIB=ON"
    "-DBUILD_JAVA=OFF"
    "-DBUILD_PYTHON=OFF"
    "-DBUILD_TESTING=OFF"
    "-DBUILD_TUTORIALS=OFF"
  ];
  doCheck = false;
  meta = builtins.removeAttrs old.meta [ "mainProgram" ];
  postPatch = (old.postPatch or "") + ''
    # Upstream CMake omits the native Autotools pkg-config template. Configure
    # that original template with the native project's version and prefix.
    cat >> lib/c_glib/CMakeLists.txt <<'CMAKE'
    set(prefix "''${CMAKE_INSTALL_PREFIX}")
    set(exec_prefix "\''${prefix}")
    set(libdir "\''${prefix}/lib")
    set(includedir "\''${prefix}/include")
    set(VERSION "''${thrift_VERSION}")
    configure_file(thrift_c_glib.pc.in thrift_c_glib.pc @ONLY)
    install(FILES "''${CMAKE_CURRENT_BINARY_DIR}/thrift_c_glib.pc" DESTINATION lib/pkgconfig)
    CMAKE
  '';
  postInstall = (old.postInstall or "") + ''
    mkdir -p "$out/share/licenses/thrift"
    cp ${thrift.src}/LICENSE ${thrift.src}/NOTICE "$out/share/licenses/thrift/"
  '';
})
