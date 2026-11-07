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
if [ "$(uname -s)" = Darwin ]; then
  # CMake before 4.0 otherwise discovers the host Xcode SDK independently
  # of the Nix compiler wrapper. Bind both to the declared Nix SDK.
  export SDKROOT DEVELOPER_DIR
  SDKROOT=$(readlink -f "$tools/nix-support/darwin-sdkroot")
  DEVELOPER_DIR=$(readlink -f "$tools/nix-support/darwin-developer-dir")
  [ -d "$SDKROOT/usr/include" ]
  [ "$(readlink -f "$DEVELOPER_DIR/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk")" = "$SDKROOT" ]
  echo "Darwin SDKROOT=$SDKROOT, DEVELOPER_DIR=$DEVELOPER_DIR, compiler=$(readlink -f "$(command -v c++)")"
  c++ -### -x c++ -c /dev/null > "$scratch/compiler.log" 2>&1
  cat "$scratch/compiler.log"
  grep -F -- "\"-isysroot\" \"$SDKROOT\"" "$scratch/compiler.log"
fi
cp -r "$root/tests/fixtures/basic" "$scratch/basic"
chmod -R u+w "$scratch/basic"
cmake-purifier lock -S "$scratch/basic"
cmp "$root/tests/fixtures/basic/cmake-purifier.lock.json" "$scratch/basic/cmake-purifier.lock.json"
cmake-purifier prefetch -S "$scratch/basic"
# shellcheck source=tests/offline-runner.sh
source "$root/tests/offline-runner.sh"
offline cmake -S "$scratch/basic" -B "$scratch/basic/build" -C "$scratch/basic/.cmake-purifier/initial-cache.txt" -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
if [ "$(uname -s)" = Darwin ]; then
  grep -Fx "CMAKE_OSX_SYSROOT:PATH=$SDKROOT" "$scratch/basic/build/CMakeCache.txt"
  cat "$scratch/basic/build/compile_commands.json"
  if grep -F /Applications/ "$scratch/basic/build/compile_commands.json"; then
    echo 'compile commands selected an undeclared host SDK' >&2
    exit 1
  fi
fi
offline cmake --build "$scratch/basic/build" -j2
offline ctest --test-dir "$scratch/basic/build" --output-on-failure
[ "$(offline "$scratch/basic/build/greet" --name "$version")" = "Hello, $version!" ]
nix build --option sandbox true --option allow-import-from-derivation false --no-link -L "$root#test-basic-$key"
echo "toolchain $version: lock/prefetch/offline/pure build passed"
