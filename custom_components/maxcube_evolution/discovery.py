"""MAX! Cube UDP discovery/reboot, ported from Kazakov Ada client."""
import socket
import time
from dataclasses import dataclass

PORT = 23272
DISCOVERY = b"eQ3Max*\x00" + b"*" * 10 + b"I"

@dataclass(frozen=True)
class CubeDescriptor:
    host: str
    name: str
    serial: str

def discover(timeout=2.0):
    found = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        # Binding to the protocol's discovery port is important for responses.
        sock.bind(("", PORT))
        for _ in range(2):
            sock.sendto(DISCOVERY, ("255.255.255.255", PORT))
            deadline = time.monotonic() + timeout / 2
            while time.monotonic() < deadline:
                sock.settimeout(max(0.05, deadline - time.monotonic()))
                try:
                    payload, address = sock.recvfrom(256)
                except socket.timeout:
                    break
                if len(payload) != 26:
                    continue
                name = payload[:8].decode("ascii", "replace").strip("\x00 ")
                serial = payload[8:18].decode("ascii", "replace").strip("\x00 ")
                if len(serial) == 10:
                    found[serial] = CubeDescriptor(address[0], name, serial)
    return list(found.values())

def reboot(serial):
    if len(serial) != 10 or not serial.isascii():
        raise ValueError("Expected a 10-character Cube serial")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(b"eQ3Max*\x00" + serial.encode("ascii") + b"R", ("255.255.255.255", PORT))
