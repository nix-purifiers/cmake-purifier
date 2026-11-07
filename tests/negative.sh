#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
#
# The commands outside the sandbox. The mistakes a developer makes with a
# lockfile must stop `cmake-purifier prefetch` with an error that says what
# went wrong and names the command that fixes it:
#
# - A lockfile that is not valid JSON.
# - A lockfile whose hash of a download was edited.
# - A lockfile older than the build definition.
# - A build that declares a dependency the lockfile does not hold, which
#   the configure on the prefetched initial cache stops.
#
# Then --lockfile and CMAKE_PURIFIER_LOCKFILE: a lockfile kept outside the
# project prefetches it. Then `publish`, with a stand-in for gh that records its
# arguments: it uploads each file of the basic fixture's release.
#
# Each case runs on a copy of the basic fixture in a scratch directory.
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
scratch=$(mktemp -d)
trap 'chmod -R u+w "$scratch"; rm -rf "$scratch"' EXIT
system=$(nix eval --impure --raw --expr builtins.currentSystem)

run() {
  nix shell "$root#test-tools" -c "$@"
}

# Copies the basic fixture to $scratch/<name> and prints its path.
fixture() {
  cp -r "$root/tests/fixtures/basic" "$scratch/$1"
  chmod -R u+w "$scratch/$1"
  echo "$scratch/$1"
}

# Runs <command...> and checks that it fails with output that matches
# <pattern>.
fails_with() {
  local pattern=$1 log=$scratch/log
  shift
  if run "$@" > "$log" 2>&1; then
    echo "negative: $* succeeded" >&2
    exit 1
  fi
  grep -q -- "$pattern" "$log" || {
    echo "negative: $* failed without '$pattern':" >&2
    cat "$log" >&2
    exit 1
  }
}

broken=$(fixture broken)
echo '{ "version": 3,' > "$broken/cmake-purifier.lock.json"
fails_with "is not valid JSON; restore it from version control, or run cmake-purifier lock" \
  cmake-purifier prefetch -S "$broken"

tampered=$(fixture tampered)
run jq '(.artifacts[] | select(.url != null) | .hash) |= "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="' \
  "$root/tests/fixtures/basic/cmake-purifier.lock.json" > "$tampered/cmake-purifier.lock.json"
fails_with "was edited: its content no longer matches its contentHash" cmake-purifier prefetch -S "$tampered"

stale=$(fixture stale)
echo '# an edit that downloads nothing new' >> "$stale/CMakeLists.txt"
fails_with "is older than the project: a CMakeLists.txt or \*.cmake file changed since it was written. Run cmake-purifier lock" \
  cmake-purifier prefetch -S "$stale"

# The lockfile of the fixture without its dependency fmt, with the
# contentHash recomputed as `cmake-purifier lock` computes it.
missing=$(fixture missing)
run jq 'del(.contentHash) | .dependencies |= map(select(.name != "fmt"))' \
  "$root/tests/fixtures/basic/cmake-purifier.lock.json" > "$scratch/missing.json"
hash=$(run jq -cS . "$scratch/missing.json" | tr -d '\n' | sha256sum | cut -d' ' -f1)
run jq --arg hash "sha256:$hash" '. + { contentHash: $hash }' "$scratch/missing.json" > "$missing/cmake-purifier.lock.json"
run cmake-purifier prefetch -S "$missing"
fails_with "the build declares the dependency fmt, which the lockfile" \
  cmake -S "$missing" -B "$missing/build" -C "$missing/.cmake-purifier/initial-cache.txt"

# A project without a lockfile of its own, from a lockfile outside it,
# named by --lockfile and by CMAKE_PURIFIER_LOCKFILE. The prefetch writes
# .cmake-purifier beside the lockfile.
external=$(fixture external)
mkdir "$scratch/packaging"
mv "$external/cmake-purifier.lock.json" "$scratch/packaging/cmake-purifier.lock.json"
run cmake-purifier prefetch -S "$external" --lockfile "$scratch/packaging/cmake-purifier.lock.json"
run cmake -S "$external" -B "$external/build" -C "$scratch/packaging/.cmake-purifier/initial-cache.txt" > /dev/null
rm -rf "$scratch/packaging/.cmake-purifier"
CMAKE_PURIFIER_LOCKFILE=$scratch/packaging/cmake-purifier.lock.json run cmake-purifier prefetch -S "$external"
[ -f "$scratch/packaging/.cmake-purifier/initial-cache.txt" ]

# publish uploads every file of the release with gh.
mkdir "$scratch/bin"
cat > "$scratch/bin/gh" <<EOF
#!/usr/bin/env bash
printf '%s\n' "\$@" > "$scratch/gh.args"
EOF
chmod +x "$scratch/bin/gh"
release=$(nix build --no-link --print-out-paths --impure --expr \
  "let flake = builtins.getFlake \"git+file://$root\"; pkgs = import flake.inputs.nixpkgs { system = \"$system\"; overlays = [ flake.overlays.default ]; }; in (pkgs.cmake-purifier.buildCMakeProject { src = $root/tests/fixtures/basic; }).release")
PATH=$scratch/bin:$PATH run cmake-purifier publish --repo nix-purifiers/example v1.2.3 "$release"
grep -qx "$release/purifier-basic-1.2.3-$system.tar.gz" "$scratch/gh.args"
grep -qx -- --clobber "$scratch/gh.args"
grep -qx nix-purifiers/example "$scratch/gh.args"

echo "negative: passed"
