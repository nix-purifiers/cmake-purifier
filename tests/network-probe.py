#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise Darwin loopback permissions and external outbound denial with real sockets."""
import errno
import socket
import sys

assert sys.platform == "darwin", sys.platform

for kind, port in [(socket.SOCK_STREAM, 443), (socket.SOCK_DGRAM, 53)]:
    with socket.socket(socket.AF_INET, kind) as client:
        client.settimeout(2)
        try:
            client.connect(("1.1.1.1", port))
        except OSError as error:
            assert error.errno == errno.EPERM, (kind, error)
        else:
            raise AssertionError(f"external connection allowed for socket kind {kind}")

with socket.socket() as server:
    server.settimeout(2)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    with socket.create_connection(server.getsockname(), timeout=2) as client:
        with server.accept()[0] as accepted:
            accepted.settimeout(2)
            client.sendall(b"tcp")
            assert accepted.recv(3) == b"tcp"
            accepted.sendall(b"reply")
            assert client.recv(5) == b"reply"

with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
    server.settimeout(2)
    server.bind(("127.0.0.1", 0))
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        client.settimeout(2)
        client.sendto(b"udp", server.getsockname())
        data, peer = server.recvfrom(64)
        assert data == b"udp"
        server.sendto(b"reply", peer)
        assert client.recvfrom(64)[0] == b"reply"

print("Darwin TCP/UDP loopback and external EPERM controls passed")
