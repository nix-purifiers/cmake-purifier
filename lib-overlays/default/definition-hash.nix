# SPDX-License-Identifier: MIT
#
# The hash of the build definition of a CMake project at the path `src`,
# as definition-hash.sh computes it: every regular CMakeLists.txt, *.cmake
# and *.cmake.in file under `src`, outside .git, .cmake-purifier and build
# directories (a directory with a CMakeCache.txt), as a line
# `<SHA-256 of the file> <path relative to src>`, the lines sorted by path,
# hashed with SHA-256. It reads `src` at evaluation time, so `src` must be
# a path rather than the output of a build.
src:
let
  inherit (builtins)
    concatLists
    attrNames
    readDir
    pathExists
    hashFile
    hashString
    sort
    concatStringsSep
    match
    ;

  definition = name: name == "CMakeLists.txt" || match ".*\\.cmake(\\.in)?" name != null;

  walk =
    dir: prefix:
    let
      entries = readDir dir;
    in
    concatLists (
      map (
        name:
        let
          type = entries.${name};
          path = dir + "/${name}";
          relative = prefix + name;
        in
        if type == "directory" then
          if name == ".git" || name == ".cmake-purifier" || pathExists (path + "/CMakeCache.txt") then
            [ ]
          else
            walk path "${relative}/"
        else if type == "regular" && definition name then
          [
            {
              inherit relative path;
            }
          ]
        else
          [ ]
      ) (attrNames entries)
    );

  files = sort (a: b: a.relative < b.relative) (walk src "");
in
hashString "sha256" (
  concatStringsSep "" (map (f: "${hashFile "sha256" f.path} ${f.relative}\n") files)
)
