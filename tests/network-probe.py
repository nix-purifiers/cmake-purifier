#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise Darwin loopback permissions and external outbound denial with real sockets."""
import errno
import socket
import sys

assert sys.platform == "darwin", sys.platform

denials = {}
for kind in [socket.SOCK_STREAM, socket.SOCK_DGRAM]:
    with socket.socket(socket.AF_INET, kind) as client:
        client.settimeout(2)
        try:
            if kind == socket.SOCK_DGRAM:
                client.sendto(b"forbidden", ("198.51.100.1", 443))
            else:
                client.connect(("198.51.100.1", 443))
        except OSError as error:
            assert error.errno in (errno.EPERM, errno.EACCES), (kind, error)
            denials[kind.name] = errno.errorcode[error.errno]
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

print(f"Darwin TCP/UDP loopback and external outbound denial controls passed: {denials}")
