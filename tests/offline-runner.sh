#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Source after putting the pinned test tools on PATH. Loopback stays usable
# for mitm-cache; all external network access is denied by the OS.
if [ "$(uname -s)" = Darwin ]; then
  offline() {
    /usr/bin/sandbox-exec -p '(version 1) (allow default) (deny network*) (allow network-bind (local ip "localhost:*")) (allow network-inbound (local ip "localhost:*")) (allow network-outbound (remote ip "localhost:*"))' "$@"
  }
  # Verify the policy itself, without relying on DNS or a remote response.
  offline python3 - <<'PY'
import errno
import socket
try:
    socket.create_connection(("1.1.1.1", 443), timeout=2)
except OSError as error:
    assert error.errno == errno.EPERM, error
else:
    raise SystemExit("offline policy allowed an external connection")
# Replay needs a real loopback listener and connection under the same
# policy. Bind, accept and connect are separate Seatbelt operations.
with socket.socket() as server:
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    with socket.create_connection(server.getsockname(), timeout=2) as client:
        with server.accept()[0] as accepted:
            client.sendall(b"offline")
            assert accepted.recv(7) == b"offline"
PY
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
