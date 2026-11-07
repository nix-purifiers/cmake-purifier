#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
evidence=${1:-$(mktemp -d)}
sdk_version=${2:-2.8.12.2}
mkdir -p "$evidence"
evidence=$(realpath "$evidence")
nix build --impure --no-link --print-out-paths --file "$root/tests/legacy-external/tools.nix" --argstr sdkVersion "$sdk_version" \
  cli sdk toolchain foreignCli modernCli modernCmake > "$evidence/tools.txt"
mapfile -t legacy_tools < "$evidence/tools.txt"
[ "${#legacy_tools[@]}" = 6 ]
export PATH="${legacy_tools[2]}/bin:$PATH"
python3 -B "$root/tests/legacy-external/run.py" \
  --cli "${legacy_tools[0]}" --sdk "${legacy_tools[1]}" \
  --foreign-cli "${legacy_tools[3]}" --modern-cmake "${legacy_tools[5]}" \
  --work "$evidence/native"
unshare -rn sh -c 'ip link set lo up && exec "$@"' legacy-cold \
  python3 -B "$root/tests/legacy-external/cold.py" --work "$evidence/native"
nix build --impure --no-link --print-out-paths --option allow-import-from-derivation false \
  --file "$root/tests/legacy-external/project.nix" --argstr sdkVersion "$sdk_version" --argstr fixtureRoot "$evidence/native/source" \
  package release > "$evidence/pure-paths.txt"
mapfile -t legacy_pure < "$evidence/pure-paths.txt"
python3 -B - "$root" "${legacy_pure[0]}" "${legacy_tools[1]}" <<'PY'
import sys
sys.path.insert(0, sys.argv[1] + '/tests/legacy-external')
from run import verify_install
verify_install(sys.argv[2], sys.argv[3])
PY
nix build --impure --no-link --rebuild --option allow-import-from-derivation false \
  --file "$root/tests/legacy-external/project.nix" --argstr sdkVersion "$sdk_version" --argstr fixtureRoot "$evidence/native/source" \
  package release > "$evidence/rebuild.log" 2>&1
for unavailable in targets projections; do
  if nix eval --impure --json --file "$root/tests/legacy-external/project.nix" --argstr sdkVersion "$sdk_version" \
    --argstr fixtureRoot "$evidence/native/source" "$unavailable" > "$evidence/$unavailable.log" 2>&1; then
    echo "legacy unexpectedly supplied $unavailable" >&2
    exit 1
  fi
  rg -q 'no native target metadata or projections' "$evidence/$unavailable.log"
done
printf 'Legacy CMake native/capture/cold/pure/rebuild checks passed: %s\n' "$evidence"
