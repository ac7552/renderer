import socket

import pytest

from renderer.garment_import import fetcher


@pytest.mark.parametrize("url", ["http://localhost/", "http://127.0.0.1:3000/", "http://10.0.0.5/", "http://192.168.1.1/",
                                 "http://169.254.169.254/latest/meta-data", "http://[::1]/"])
def test_refuses_links_to_this_machine_private_networks_and_cloud_metadata(url):
    with pytest.raises(fetcher.Error) as error:
        fetcher.get(url)
    assert "private address" in str(error.value)


@pytest.mark.parametrize("url", ["ftp://example.com/x", "javascript:alert(1)", "not a link", ""])
def test_refuses_things_that_arent_web_links(url):
    with pytest.raises(fetcher.Error):
        fetcher.get(url)


def test_a_name_that_resolves_to_a_private_address_is_refused_too(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", 0))])
    with pytest.raises(fetcher.Error) as error:
        fetcher.get("https://shop.example/products/tee")
    assert "private address" in str(error.value)


def test_an_ipv4_address_inside_ipv6_is_checked_as_itself():
    assert not fetcher.allowed("::ffff:127.0.0.1")
    assert not fetcher.allowed("::ffff:10.0.0.1")
    assert fetcher.allowed("93.184.216.34")


def test_a_site_that_turns_away_every_app_isnt_asked():
    with pytest.raises(fetcher.GaveUp) as error:
        fetcher.get("https://www.therealreal.com/products/x")
    assert error.value.reason == "therealreal.com doesn't let apps read its pages"


def test_a_site_that_cant_be_reached_gives_up_with_why(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))])
    with pytest.raises(fetcher.GaveUp) as error:
        fetcher.get("https://shop.example/products/tee")
    assert error.value.reason == "shop.example couldn't be reached"
