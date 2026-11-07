# SPDX-License-Identifier: MIT
{
  lib,
  stdenv,
  runCommand,
  fetchurl,
  fetchgit,
  fetchhg,
  fetchsvn,
  fetchcvs,
  unzip,
  zstd,
  python3,
  writeText,
  purifier,
  lockFile,
  projectSrc ? null,
  fetchers ? { },
}:
let
  memory = purifier.checkLock (
    import ./legacy-lock.nix {
      inherit lockFile;
      src = projectSrc;
    }
  );
  fetcherArgs = {
    inherit
      fetchurl
      fetchgit
      fetchhg
      fetchsvn
      fetchcvs
      runCommand
      unzip
      zstd
      python3
      writeText
      ;
  }
  // fetchers;
in
{
  inherit memory;
  lock = memory.cmake;
  tree = purifier.tree (
    fetcherArgs
    // {
      name = "cmake-legacy-http";
      entries = memory.entries;
    }
  );
}
