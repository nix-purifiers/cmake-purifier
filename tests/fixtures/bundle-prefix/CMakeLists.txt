# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(bundle_prefix VERSION 1.0 LANGUAGES C)

# Flutter applications such as RustDesk use build-local bundle prefixes and
# absolute destinations, so --install --prefix cannot relocate their files.
set(CMAKE_INSTALL_PREFIX "${CMAKE_CURRENT_BINARY_DIR}/bundle" CACHE PATH "" FORCE)
add_executable(bundle-probe main.c)
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/payload.txt" "bundle payload\n")
install(TARGETS bundle-probe RUNTIME DESTINATION "${CMAKE_INSTALL_PREFIX}/bin")
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/payload.txt"
  DESTINATION "${CMAKE_INSTALL_PREFIX}/share")
enable_testing()
add_test(NAME bundle-probe COMMAND bundle-probe)
