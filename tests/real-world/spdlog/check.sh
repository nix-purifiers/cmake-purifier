#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Both upstream test suites run, in ordinary CMake and in the Nix sandbox.
set -euo pipefail
root=$(cd "$(dirname "$0")/../../.." && pwd)
scratch=$(mktemp -d)
trap 'chmod -R u+w "$scratch"; rm -rf "$scratch"' EXIT
tools=$(nix build --no-link --print-out-paths "$root#test-tools")
src=$(nix build --no-link --print-out-paths "$root#test-spdlog-src")
export PATH="$tools/bin:$PATH"
cp -r "$src" "$scratch/spdlog"
chmod -R u+w "$scratch/spdlog"
project=$scratch/spdlog
cp "$root/tests/real-world/spdlog/cmake-purifier.lock.json" "$project/"
cmake-purifier lock -S "$project" -DSPDLOG_BUILD_TESTS=ON -DSPDLOG_BUILD_TESTS_HO=ON -DSPDLOG_BUILD_EXAMPLE=OFF
cmp "$root/tests/real-world/spdlog/cmake-purifier.lock.json" "$project/cmake-purifier.lock.json"
cmake-purifier prefetch -S "$project"
# shellcheck source=tests/offline-runner.sh
source "$root/tests/offline-runner.sh"
offline cmake -S "$project" -B "$project/build" -C "$project/.cmake-purifier/initial-cache.txt"
offline cmake --build "$project/build" -j2
offline ctest --test-dir "$project/build" --output-on-failure --timeout 300
offline cmake --install "$project/build" --prefix "$scratch/install"
# An ordinary consumer discovers the installed CMake export and links it.
mkdir "$scratch/consumer"
cp "$root/tests/real-world/spdlog/consumer/"* "$scratch/consumer/"
consumer() {
  offline cmake -S "$scratch/consumer" -B "$scratch/consumer-$1" -DCMAKE_PREFIX_PATH="$2"
  offline cmake --build "$scratch/consumer-$1" -j2
  offline "$scratch/consumer-$1/consumer"
}
consumer ordinary "$scratch/install"
nixPackage=$(nix build --option sandbox true --option allow-import-from-derivation false --no-link --print-out-paths -L "$root#test-spdlog")
consumer nix "$nixPackage"
# A missing producer must fail discovery, rather than picking up the other
# installation from the earlier consumer's build cache.
if offline cmake -S "$scratch/consumer" -B "$scratch/consumer-missing" -DCMAKE_FIND_ROOT_PATH="$scratch/missing" -DCMAKE_FIND_ROOT_PATH_MODE_PACKAGE=ONLY > "$scratch/missing.log" 2>&1; then
  echo "spdlog consumer unexpectedly configured without its producer" >&2
  exit 1
fi
grep -q 'spdlog' "$scratch/missing.log"
echo "spdlog: ordinary and Nix upstream tests and consumers passed"
