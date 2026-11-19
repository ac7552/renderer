import socket
from pathlib import Path

import pytest

import renderer.garment_import as garment_import

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Nothing in the tests reaches another machine: a connection fails at once, as an unreachable site's would."""

    def refuse(*args, **kwargs):
        raise ConnectionRefusedError("the tests don't use the network")

    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture(autouse=True)
def footwear_on():
    """Footwear is off by default; the tests keep covering it, and one test turns it off."""
    garment_import.footwear = True
    yield
    garment_import.footwear = None
    garment_import.bags = None
    garment_import.IMPORTS.clear()


def page(name):
    return (FIXTURES / f"{name}.html").read_text()
