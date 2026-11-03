#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
#
# Relocks the fixtures with the cmake-purifier of this checkout. The lock
# run configures and builds each fixture, so it needs the network and a C
# and C++ compiler, which nixpkgs provides here.
#
# The vcs fixture locks against the repositories of tests/vcs-repos.nix,
# which the flake check `vcs-repos` builds. They are in the read-only
# store, so CVSREADONLYFS tells cvs to leave no lock files in the CVS one,
# and git clones the git one's submodules over the file transport only
# with protocol.file.allow set, as the GIT_CONFIG_* variables do.
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
system=$(nix eval --impure --raw --expr builtins.currentSystem)

lock() {
  nix shell 'nixpkgs#gcc' 'nixpkgs#gnumake' "$root#cmake-purifier" -c cmake-purifier lock "$@"
}

lock -S "$root/tests/fixtures/basic"
lock -S "$root/tests/fixtures/extras"

# The vcs lockfile names the repositories by their store path, which is
# the path of `vcs-repos` on x86_64-linux. On a system where `vcs-repos`
# has another path, the fixture locks into a scratch lockfile, which must
# equal the committed one once the path of this system is replaced by the
# committed path. The contentHash is left out of the comparison, since it
# covers the path.
repos=$(nix build --no-link --print-out-paths "$root#checks.$system.vcs-repos")
vcsLock=$root/tests/fixtures/vcs/cmake-purifier.lock.json
committedRepos=$(grep -o '/nix/store/[a-z0-9]*-cmake-purifier-vcs-repos' "$vcsLock" | head -n 1)
lockArgs=()
if [ "$repos" != "$committedRepos" ]; then
  scratch=$(mktemp -d)
  trap 'rm -rf "$scratch"' EXIT
  lockArgs=(--lockfile "$scratch/vcs.lock.json")
fi
GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=protocol.file.allow GIT_CONFIG_VALUE_0=always \
  lock -S "$root/tests/fixtures/vcs" ${lockArgs[@]+"${lockArgs[@]}"} \
  -DPURIFIER_SVN_URL="file://$repos/svn" \
  -DPURIFIER_HG_URL="file://$repos/hg" \
  -DPURIFIER_GIT_URL="file://$repos/git/super.git"
if [ "$repos" != "$committedRepos" ]; then
  normalize() {
    nix shell 'nixpkgs#jq' -c jq -S 'del(.contentHash)' "$1" | sed "s|$repos|$committedRepos|g"
  }
  if ! diff <(normalize "$scratch/vcs.lock.json") <(normalize "$vcsLock"); then
    echo "relock: the vcs fixture locks differently on $system" >&2
    exit 1
  fi
fi

# libcpr/cpr, from its pinned source, in its development shell, into the
# lockfile kept in tests/real-world/cpr. The lockfile records the names of
# cpr's shared libraries on Linux, which differ elsewhere, so it locks on
# Linux only.
if [ "${system##*-}" = linux ]; then
  cpr=$(nix build --no-link --print-out-paths "$root#checks.$system.real-world-cpr-src")
  nix develop "$root#checks.$system.real-world-cpr-shell" -c \
    cmake-purifier lock -S "$cpr" --lockfile "$root/tests/real-world/cpr/cmake-purifier.lock.json" -DCPR_BUILD_TESTS=ON
fi

# nixpkgs' cvs aborts on aarch64-linux, so the CVS fixture locks on
# x86_64-linux only.
if [ "$system" = x86_64-linux ]; then
  CVSREADONLYFS=1 lock -S "$root/tests/fixtures/cvs" -DPURIFIER_CVS_ROOT="$repos/cvs"
fi
