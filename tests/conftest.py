import socket

import pytest


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Tests are deterministic: inject fake resolvers instead of using sockets."""

    def blocked(*args, **kwargs):
        raise AssertionError("network access is disabled in the Groundnut test suite")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
