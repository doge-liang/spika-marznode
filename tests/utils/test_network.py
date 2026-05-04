"""Tests for marznode.utils.network."""

from __future__ import annotations

import socket

from marznode.utils.network import find_free_port


def test_find_free_port_returns_int_in_user_range():
    port = find_free_port()
    assert isinstance(port, int)
    assert 0 < port < 65536


def test_returned_port_is_immediately_bindable():
    port = find_free_port()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("127.0.0.1", port))
    finally:
        s.close()


def test_repeated_calls_succeed():
    # Not asserting uniqueness — the kernel is free to reuse a freshly closed
    # ephemeral port. The contract is just that each call returns a valid port.
    for _ in range(20):
        port = find_free_port()
        assert isinstance(port, int) and port > 0
