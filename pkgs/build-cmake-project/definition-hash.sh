# SPDX-License-Identifier: MIT
#
# Prints the hash of the build definition of a CMake project: every
# CMakeLists.txt, *.cmake and *.cmake.in file under <source dir>, by its
# path and content. definition-hash.nix computes the same hash at
# evaluation time, from the copy of the project that Nix builds.
#
#   bash definition-hash.sh <source dir>
#
# In a git checkout, the files are the ones git tracks, as in the copy of
# the project that a flake builds. Elsewhere they are all such files,
# outside build directories (a directory with a CMakeCache.txt), outside the
# .cmake-purifier directory that `cmake-purifier prefetch` writes, and outside
# .git. The lock run records the hash, and a build or a prefetch from the
# lockfile fails when the definition hashes differently, since a changed
# definition may download what the lockfile does not hold. The script needs bash,
# coreutils, findutils, and git for a git checkout.
set -eu

source=$1
cd "$source"

files() {
  if command -v git > /dev/null 2>&1 && git rev-parse --is-inside-work-tree > /dev/null 2>&1; then
    git ls-files -z -- . | tr '\0' '\n'
  else
    find . \( -name .git -o -name .cmake-purifier -o -type d -exec test -e '{}/CMakeCache.txt' ';' \) -prune \
      -o -type f -print | sed 's|^\./||'
  fi
}

files | while IFS= read -r file; do
  # Regular files only, as definition-hash.nix reads them.
  [ -f "$file" ] && [ ! -L "$file" ] || continue
  case "${file##*/}" in
    CMakeLists.txt | *.cmake | *.cmake.in) printf '%s\n' "$file" ;;
  esac
done | LC_ALL=C sort | while IFS= read -r file; do
  printf '%s %s\n' "$(sha256sum < "$file" | cut -d' ' -f1)" "$file"
done | sha256sum | cut -d' ' -f1
