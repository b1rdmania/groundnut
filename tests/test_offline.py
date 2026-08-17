import socket

import pytest


def test_test_suite_blocks_network_connections():
    with pytest.raises(AssertionError, match="network access is disabled"):
        socket.create_connection(("example.invalid", 443))

    with pytest.raises(AssertionError, match="network access is disabled"):
        socket.getaddrinfo("example.invalid", 443)
