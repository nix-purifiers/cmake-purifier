#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
#
# conformance-offline: after `cmake-purifier prefetch`, the development loop
# of each fixture works with no network. The loop is CMake's own commands
# on the initial cache that the prefetch writes: the configure, the build,
# ctest, and clangd on the build directory's compile_commands.json. The
# fixtures that download files outside FetchContent run the configure and
# the build under `cmake-purifier replay`.
#
# The prefetch runs with the network. The loop runs in a new network
# namespace that has only the loopback interface, when `unshare` can make
# one. Without user namespaces, the loop runs on the host's network, and
# the test only shows that FetchContent populated none of the basic
# fixture's dependencies itself; CI sets CMAKE_PURIFIER_REQUIRE_OFFLINE=1
# to fail instead.
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
scratch=$(mktemp -d)
trap 'chmod -R u+w "$scratch"; rm -rf "$scratch"' EXIT

# The tools of the loop, built with the network, so that the loop itself
# needs no Nix. unshare and ip, for the namespace, are Linux tools.
netTools=()
if [ "$(uname -s)" = Linux ]; then
  netTools=('nixpkgs#iproute2' 'nixpkgs#util-linux')
fi
tools=$(nix build --no-link --print-out-paths 'nixpkgs#gcc' 'nixpkgs#gnumake' 'nixpkgs#cmake' \
  'nixpkgs#clang-tools' ${netTools[@]+"${netTools[@]}"} "$root#cmake-purifier")
# $tools is one store path per line, which the split makes arguments.
# shellcheck disable=SC2086
loopPath=$(printf '%s/bin:' $tools)$PATH

if PATH=$loopPath unshare -rn true 2> /dev/null; then
  offline() {
    PATH=$loopPath unshare -rn bash -c 'ip link set lo up && exec "$@"' offline "$@"
  }
elif [ "${CMAKE_PURIFIER_REQUIRE_OFFLINE:-}" = 1 ]; then
  echo "offline: unshare cannot make a network namespace here" >&2
  exit 1
else
  echo "offline: unshare cannot make a network namespace here; the loop runs on the host's network" >&2
  offline() {
    PATH=$loopPath "$@"
  }
fi

# Copies a fixture to $scratch/<name> and prefetches it, with the network.
prefetch() {
  cp -r "$root/tests/fixtures/$1" "$scratch/$1"
  chmod -R u+w "$scratch/$1"
  PATH=$loopPath cmake-purifier prefetch -S "$scratch/$1"
}

prefetch basic
basic=$scratch/basic
offline cmake -S "$basic" -B "$basic/build" -C "$basic/.cmake-purifier/initial-cache.txt"
# The editor: clangd reads the build directory's compile_commands.json and
# finds the headers of fmt and argparse in the prefetched sources. On macOS
# the C headers are in the SDK, which only the compiler's wrapper names, so
# clangd asks the compiler for its include paths.
clangdArgs=()
if [ "$(uname -s)" = Darwin ]; then
  clangdArgs=("--query-driver=$(dirname "$(PATH=$loopPath command -v c++)")/*")
fi
offline clangd --check="$basic/main.cpp" --compile-commands-dir="$basic/build" ${clangdArgs[@]+"${clangdArgs[@]}"} \
  > "$scratch/clangd.log" 2>&1 || {
  echo "clangd failed on the offline build directory:" >&2
  cat "$scratch/clangd.log" >&2
  exit 1
}
offline cmake --build "$basic/build" -j4
[ "$(offline "$basic/build/greet" --name offline)" = "Hello, offline!" ]
offline ctest --test-dir "$basic/build" --output-on-failure
populated=$(find "$basic/build/_deps" -mindepth 1 -maxdepth 1 \( -name '*-src' -o -name '*-subbuild' \))
if [ -n "$populated" ]; then
  echo "FetchContent populated a dependency itself:" >&2
  echo "$populated" >&2
  exit 1
fi

prefetch extras
extras=$scratch/extras
offline cmake-purifier replay -S "$extras" -- cmake -S "$extras" -B "$extras/build" -C "$extras/.cmake-purifier/initial-cache.txt"
offline cmake-purifier replay -S "$extras" -- cmake --build "$extras/build" -j4
[ "$(offline "$extras/build/extras" --count 7)" = "count 7, zlib 1.3.1" ]
grep -q 'Victor Zverovich' "$extras/build/fmt-LICENSE"

# The vcs fixture checks out from repositories in the store. Its fetches
# name them by plain store path, which gives a fetch no access to them, so
# the flake check `vcs` must have fetched them before this test runs; a
# fetch whose output is already in the store does not run again.
prefetch vcs
vcs=$scratch/vcs
offline cmake -S "$vcs" -B "$vcs/build" -C "$vcs/.cmake-purifier/initial-cache.txt"
offline cmake --build "$vcs/build" -j4
[ "$(offline "$vcs/build/vcs")" = "svn hg sub_a sub_b" ]

# nixpkgs' cvs aborts on aarch64-linux, so the CVS fixture runs on
# x86_64-linux only.
if [ "$(uname -m)" = x86_64 ]; then
  prefetch cvs
  cvs=$scratch/cvs
  offline cmake -S "$cvs" -B "$cvs/build" -C "$cvs/.cmake-purifier/initial-cache.txt"
  offline cmake --build "$cvs/build" -j4
  [ "$(offline "$cvs/build/cvs")" = cvs ]
fi

echo "offline: passed"
