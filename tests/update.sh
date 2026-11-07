#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
#
# conformance-update: `cmake-purifier update` moves a dependency that
# follows a branch, and `cmake-purifier lock` keeps it where it is.
#
# The project takes two FetchContent dependencies from local git
# repositories, each at its branch `main`: `alpha` with a full clone and
# `beta` with GIT_SHALLOW, whose locked commit a later shallow clone no
# longer has. After the lock, both branches move on. Then:
#
# - `lock` keeps both at their locked commits, and writes the same
#   lockfile byte for byte.
# - `update beta` moves beta only.
# - `update` moves both.
#
# After each step, the test reads the locked commits from the lockfile,
# and readLock of the flake must find no problem with it, the stale check
# included. The repositories are local, so the test needs no network.
# The Nix sandbox cannot read them, so the test fetches nothing; the vcs
# fixture builds from repositories of the same kind in the store.
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
scratch=$(mktemp -d)
trap 'chmod -R u+w "$scratch"; rm -rf "$scratch"' EXIT

tools=$(nix build --no-link --print-out-paths "$root#test-tools")
export PATH="$tools/bin:$PATH"
export GIT_AUTHOR_NAME=test GIT_AUTHOR_EMAIL=test@example.invalid GIT_COMMITTER_NAME=test GIT_COMMITTER_EMAIL=test@example.invalid
export GIT_CONFIG_NOSYSTEM=1

# Commits a header that defines <NAME>_VERSION as <version> to the
# repository <name>, which it creates on the first call.
commit() {
  local name=$1 version=$2 repo=$scratch/repos/$1 upper
  if [ ! -d "$repo" ]; then
    git init -q -b main "$repo"
  fi
  upper=$(printf '%s' "$name" | tr '[:lower:]' '[:upper:]')
  printf '#define %s_VERSION "%s"\n' "$upper" "$version" > "$repo/$name.h"
  {
    echo "add_library($name INTERFACE)"
    # CMake expands the variable, not the shell.
    # shellcheck disable=SC2016
    echo "target_include_directories($name INTERFACE \${CMAKE_CURRENT_SOURCE_DIR})"
  } > "$repo/CMakeLists.txt"
  git -C "$repo" add -A
  git -C "$repo" commit -q -m "$version"
}

head_of() {
  git -C "$scratch/repos/$1" rev-parse HEAD
}

commit alpha 1
commit beta 1

project=$scratch/project
mkdir "$project"
cat > "$project/CMakeLists.txt" <<EOF
cmake_minimum_required(VERSION 3.30)
project(purifier-update LANGUAGES CXX)
include(FetchContent)
FetchContent_Declare(alpha GIT_REPOSITORY file://$scratch/repos/alpha GIT_TAG main)
FetchContent_Declare(beta GIT_REPOSITORY file://$scratch/repos/beta GIT_TAG main GIT_SHALLOW TRUE)
FetchContent_MakeAvailable(alpha beta)
add_executable(versions main.cpp)
target_link_libraries(versions PRIVATE alpha beta)
install(TARGETS versions)
EOF
cat > "$project/main.cpp" <<'EOF'
#include <cstdio>
#include "alpha.h"
#include "beta.h"
int main() { std::printf("%s %s\n", ALPHA_VERSION, BETA_VERSION); }
EOF

# Checks that the lockfile holds alpha and beta at the commits <alpha> and
# <beta>, and that readLock of the flake finds no problem with it.
locked_at() {
  local name expected actual problems
  for name in alpha beta; do
    if [ "$name" = alpha ]; then expected=$1; else expected=$2; fi
    actual=$(jq -r --arg url "file://$scratch/repos/$name" \
      '(.artifacts | map({ key: .path, value: .git.rev }) | from_entries) as $rev
       | .gitCheckouts[] | select(.url == $url) | $rev[.artifact]' "$project/cmake-purifier.lock.json")
    [ "$actual" = "$expected" ] || {
      echo "update: the lockfile holds $name at $actual, not $expected" >&2
      exit 1
    }
  done
  problems=$(nix eval --impure --json --expr \
    "(builtins.getFlake \"git+file://$root\").lib.cmake-purifier.readLock { src = $project; }" \
    --apply 'lock: lock.problems')
  [ "$problems" = "[]" ] || {
    echo "update: readLock found problems: $problems" >&2
    exit 1
  }
}

cmake-purifier lock -S "$project"
alpha1=$(head_of alpha)
beta1=$(head_of beta)
locked_at "$alpha1" "$beta1"
cp "$project/cmake-purifier.lock.json" "$scratch/locked.json"

commit alpha 2
commit beta 2

cmake-purifier lock -S "$project"
cmp "$scratch/locked.json" "$project/cmake-purifier.lock.json" || {
  echo "update: lock moved a locked branch" >&2
  exit 1
}
locked_at "$alpha1" "$beta1"

cmake-purifier update -S "$project" beta
locked_at "$alpha1" "$(head_of beta)"

cmake-purifier update -S "$project"
locked_at "$(head_of alpha)" "$(head_of beta)"

if cmake-purifier update -S "$project" gamma 2> "$scratch/unknown.log"; then
  echo "update: an update of an unknown dependency succeeded" >&2
  exit 1
fi
grep -q 'has no dependency or repository named gamma' "$scratch/unknown.log"

echo "update: passed"
