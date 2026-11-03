# SPDX-License-Identifier: MIT
#
# Writes the initial cache of a build from the lockfile.
#
#   bash write-cache.sh <sources tree> <copies dir> <cache file> <provider> <nix lib dir>
#     <git> <hg> <svn> <cvs>
#
# <sources tree> is the `tree` of sources.nix: `deps/` with an entry per
# FetchContent name, a table of locked checkouts per tool, and `http/`
# with the locked file downloads. Some builds write into their
# dependencies' source directories, and the store is read-only, so each
# entry of `deps/` is copied into <copies dir> first. A copy is made again
# only when its store path changes.
#
# The cache file sets CMAKE_PURIFIER_SOURCE_<NAME> to the copy of every
# dependency, where <NAME> is the FetchContent name in upper case, as
# FetchContent spells it, and the provider points
# FETCHCONTENT_SOURCE_DIR_<NAME> at it. FETCHCONTENT_FULLY_DISCONNECTED stops FetchContent from
# downloading those dependencies, and FETCHCONTENT_TRY_FIND_PACKAGE_MODE
# NEVER makes every declared dependency come from its source, as in the
# lock run. <provider> is cmake/CMakePurifierLocked.cmake, which the cache
# names in CMAKE_PROJECT_TOP_LEVEL_INCLUDES; it stops a configure that
# declares a dependency the lockfile does not hold, or a dependency whose
# declaration changed since the lock run, which it reads from
# CMAKE_PURIFIER_DECLARED_<NAME>.
#
# Next to the cache file, the script writes `git`, a wrapper that runs
# git-shim.sh of <nix lib dir> with the table of locked checkouts and the
# real <git>, and the cache names it in GIT_EXECUTABLE. For each of
# Mercurial, Subversion and CVS that the lockfile has checkouts of, it
# writes `hg`, `svn` or `cvs`, a wrapper that runs vcs-shim.sh with its
# table and the real tool, and names it in HG_EXECUTABLE,
# Subversion_SVN_EXECUTABLE or CVS_EXECUTABLE. Every entry is FORCE, so
# `cmake -C` with this file also updates an existing build directory.
set -eu
# The glob of deps/ sorts by the locale. With none set, as in a Nix build,
# nixpkgs' bash on macOS takes the system's, so the C locale keeps the
# order of CMAKE_PURIFIER_LOCKED the same everywhere.
export LC_ALL=C

tree=$1
copies=$2
cache=$3
provider=$4
lib=$5
git=$6
hg=$7
svn=$8
cvs=$9

dir=$(dirname "$cache")
mkdir -p "$copies" "$dir"

# Writes the wrapper $1 that exports the variables "$2=$3" ... and runs
# the shim script $last.
wrapper() {
  local file=$1
  shift
  {
    echo "#!$BASH"
    while [ $# -gt 1 ]; do
      printf 'export %s=%q\n' "$1" "$2"
      shift 2
    done
    printf 'exec %q %q "$@"\n' "$BASH" "$1"
  } > "$file.tmp"
  chmod +x "$file.tmp"
  mv "$file.tmp" "$file"
}

wrapper "$dir/git" CMAKE_PURIFIER_GIT_TABLE "$tree/git-checkouts.tsv" CMAKE_PURIFIER_REAL_GIT "$git" \
  CMAKE_PURIFIER_PRUNE "$lib/prune-submodules.sh" "$lib/git-shim.sh"

{
  echo '# Written by cmake-purifier from the lockfile; do not edit.'
  echo 'set(FETCHCONTENT_FULLY_DISCONNECTED ON CACHE BOOL "" FORCE)'
  echo 'set(FETCHCONTENT_TRY_FIND_PACKAGE_MODE NEVER CACHE STRING "" FORCE)'
  printf 'set(CMAKE_PROJECT_TOP_LEVEL_INCLUDES "%s" CACHE STRING "" FORCE)\n' "$provider"
  printf 'set(GIT_EXECUTABLE "%s" CACHE FILEPATH "" FORCE)\n' "$dir/git"
} > "$cache.tmp"

for entry in hg:HG_EXECUTABLE:"$hg" svn:Subversion_SVN_EXECUTABLE:"$svn" cvs:CVS_EXECUTABLE:"$cvs"; do
  tool=${entry%%:*}
  rest=${entry#*:}
  variable=${rest%%:*}
  real=${rest#*:}
  if [ -s "$tree/$tool-checkouts.tsv" ]; then
    wrapper "$dir/$tool" CMAKE_PURIFIER_VCS "$tool" CMAKE_PURIFIER_VCS_TABLE "$tree/$tool-checkouts.tsv" \
      CMAKE_PURIFIER_REAL_VCS "$real" "$lib/vcs-shim.sh"
    printf 'set(%s "%s" CACHE FILEPATH "" FORCE)\n' "$variable" "$dir/$tool" >> "$cache.tmp"
  fi
done
locked=

for entry in "$tree"/deps/*; do
  [ -e "$entry" ] || continue
  name=$(basename "$entry")
  store=$(readlink -f "$entry")
  copy="$copies/$name"
  if [ "$(cat "$copy.source" 2>/dev/null || true)" != "$store" ]; then
    if [ -e "$copy" ]; then
      chmod -R u+w "$copy"
      rm -rf "$copy"
    fi
    # $store is the resolved directory, and -R copies the symlinks inside
    # it as symlinks.
    cp -R "$store" "$copy"
    chmod -R u+w "$copy"
    echo "$store" > "$copy.source"
  fi
  upper=$(printf '%s' "$name" | tr '[:lower:]' '[:upper:]')
  # FetchContent calls no provider for a dependency whose
  # FETCHCONTENT_SOURCE_DIR_<NAME> is set, so the provider gets the path
  # and sets that variable itself, after its checks.
  printf 'unset(FETCHCONTENT_SOURCE_DIR_%s CACHE)\n' "$upper" >> "$cache.tmp"
  printf 'set(CMAKE_PURIFIER_SOURCE_%s "%s" CACHE INTERNAL "")\n' "$upper" "$copy" >> "$cache.tmp"
  locked="$locked${locked:+;}$name"
done
printf 'set(CMAKE_PURIFIER_LOCKED "%s" CACHE INTERNAL "")\n' "$locked" >> "$cache.tmp"
if [ -f "$tree/declared.tsv" ]; then
  while IFS=$'\t' read -r name declared; do
    upper=$(printf '%s' "$name" | tr '[:lower:]' '[:upper:]')
    printf 'set(CMAKE_PURIFIER_DECLARED_%s [==[%s]==] CACHE INTERNAL "")\n' "$upper" "$declared" >> "$cache.tmp"
  done < "$tree/declared.tsv"
fi

mv "$cache.tmp" "$cache"
