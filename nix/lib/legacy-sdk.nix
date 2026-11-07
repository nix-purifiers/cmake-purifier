# SPDX-License-Identifier: MIT
# Live consumer-owned SDK identity. Never instantiate a lockfile's store path.
{
  lib,
  stdenv,
  cmake,
  legacyProjectName,
  legacySdkAdapter,
}:
assert lib.assertMsg (stdenv.hostPlatform.system == "x86_64-linux")
  "cmake-purifier: this bounded legacy profile requires an explicit source-owned SDK on x86_64-linux";
assert lib.assertMsg (
  builtins.isString legacyProjectName
  && builtins.match "[A-Za-z][A-Za-z0-9_.+-]*" legacyProjectName != null
) "cmake-purifier: legacy profile requires its exact native root project name";
assert lib.assertMsg
  (
    builtins.isAttrs legacySdkAdapter
    &&
      builtins.attrNames legacySdkAdapter == [
        "moduleRoot"
        "package"
        "source"
        "version"
      ]
    && legacySdkAdapter.version == 1
    && lib.isDerivation legacySdkAdapter.package
    && toString legacySdkAdapter.package == toString cmake
  )
  "cmake-purifier: legacy profile requires a live source-owned adapter for its selected CMake derivation";
assert lib.assertMsg (
  builtins.isString legacySdkAdapter.moduleRoot
  &&
    builtins.match "[A-Za-z0-9_+-][A-Za-z0-9_.+-]*(/[A-Za-z0-9_+-][A-Za-z0-9_.+-]*)*" legacySdkAdapter.moduleRoot
    != null
) "cmake-purifier: SDK moduleRoot must be a safe relative path";
assert lib.assertMsg (
  builtins.isAttrs legacySdkAdapter.source
  &&
    builtins.attrNames legacySdkAdapter.source == [
      "sha256"
      "url"
    ]
  && builtins.isString legacySdkAdapter.source.sha256
  && builtins.match "[0-9a-f]{64}" legacySdkAdapter.source.sha256 != null
  && builtins.isString legacySdkAdapter.source.url
  && builtins.match "https?://[^ ]+" legacySdkAdapter.source.url != null
) "cmake-purifier: native SDK adapter requires its source URL and exact SHA256";
{
  package = toString cmake;
  version = cmake.version;
  moduleRoot = legacySdkAdapter.moduleRoot;
  source = legacySdkAdapter.source;
}
