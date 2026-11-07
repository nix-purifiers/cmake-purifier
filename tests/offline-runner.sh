#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Source after putting the pinned test tools on PATH. Loopback stays usable
# for mitm-cache; all external network access is denied by the OS.
if [ "$(uname -s)" = Darwin ]; then
  offline() {
    /usr/bin/sandbox-exec -p '(version 1) (allow default) (deny network*) (allow network-bind (local ip "localhost:*")) (allow network-inbound (local ip "localhost:*")) (allow network-outbound (remote ip "localhost:*"))' "$@"
  }
  # The same executable socket controls also run in the Darwin Nix check.
  offlineProbe=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/network-probe.py
  offline python3 "$offlineProbe"

elif unshare -rn true 2>/dev/null; then
  offline() {
    unshare -rn bash -c 'ip link set lo up && exec "$@"' offline "$@"
  }
elif [ "${CMAKE_PURIFIER_REQUIRE_OFFLINE:-}" = 1 ]; then
  echo "offline: unshare cannot make a network namespace here" >&2
  exit 1
else
  echo "offline: no network isolation available; this is not offline evidence" >&2
  offline() { "$@"; }
fi
