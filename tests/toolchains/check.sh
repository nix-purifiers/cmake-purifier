#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Exercise one independently selected source-built CMake through the actual
# lock, prefetch, ordinary offline configure/build/test, and pure Nix build.
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
version=${1:?usage: tests/toolchains/check.sh VERSION}
key=${version//./_}
scratch=$(mktemp -d)
trap 'chmod -R u+w "$scratch"; rm -rf "$scratch"' EXIT
tools=$(nix build --no-link --print-out-paths "$root#test-tools-$key")
export PATH="$tools/bin:$PATH"
actual=$(cmake --version | head -1)
[ "$actual" = "cmake version $version" ]
echo "SDK $actual, executable $(readlink -f "$(command -v cmake)")"
cp -r "$root/tests/fixtures/basic" "$scratch/basic"
chmod -R u+w "$scratch/basic"
cmake-purifier lock -S "$scratch/basic"
cmp "$root/tests/fixtures/basic/cmake-purifier.lock.json" "$scratch/basic/cmake-purifier.lock.json"
cmake-purifier prefetch -S "$scratch/basic"
# shellcheck source=tests/offline-runner.sh
source "$root/tests/offline-runner.sh"
offline cmake -S "$scratch/basic" -B "$scratch/basic/build" -C "$scratch/basic/.cmake-purifier/initial-cache.txt"
offline cmake --build "$scratch/basic/build" -j2
offline ctest --test-dir "$scratch/basic/build" --output-on-failure
[ "$(offline "$scratch/basic/build/greet" --name "$version")" = "Hello, $version!" ]
nix build --option allow-import-from-derivation false --no-link -L "$root#test-basic-$key"
echo "toolchain $version: lock/prefetch/offline/pure build passed"
