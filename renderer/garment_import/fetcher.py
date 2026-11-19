"""Fetches one product page that someone pasted. Because the URL comes from outside, it only talks to public
addresses (no localhost, private networks or cloud metadata), pins the connection to the address it checked,
re-checks every redirect, and stops at a size and time limit.

Nothing is written anywhere: the page is read into memory, used for one answer, and dropped.
"""

from __future__ import annotations

import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
import time
from email.message import Message
from urllib.parse import urljoin, urlsplit

from ..util import presence, text

TURNS_AWAY = ("therealreal.com",)  # sites known to turn away every app (they answer only people's browsers)

MAX_BYTES = 3_000_000
MAX_REDIRECTS = 3
TIMEOUT = 8
# However the site answers (slowly, a little at a time, through redirects), one fetch gives up after this.
DEADLINE = 15
USER_AGENT = "Renderer/1.0 (reads one product page's size chart when a person asks)"
BLOCKED = [ipaddress.ip_network(net) for net in (
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12", "192.168.0.0/16",
    "198.18.0.0/15", "224.0.0.0/4", "240.0.0.0/4", "::/128", "::1/128", "fc00::/7", "fe80::/10", "ff00::/8",
)]
ACCEPT = {"page": "text/html,application/xhtml+xml", "image": "image/webp,image/jpeg,image/png", "json": "application/json"}
IMAGE_TYPES = re.compile(r"\Aimage/(jpeg|png|webp)\Z")
BOT_CHECK = re.compile(r"bm-verify|_Incapsula_Resource|cf-chl|challenge-platform|px-captcha|Pardon Our Interruption|Access to this page has been denied", re.I)
MAX_IMAGE_BYTES = 2_500_000
CHUNK = 64 * 1024


class Error(Exception):
    pass


class GaveUp(Error):
    """The store wouldn't give its page: it turns apps away, answered with an error page, or couldn't be reached.
    The link was right, so its own words can still say what the garment is. reason: what happened, to tell the
    person ("therealreal.com doesn't let apps read its pages")."""

    def __init__(self, message, reason):
        super().__init__(message)
        self.reason = reason


class TooSlow(GaveUp):
    """The site didn't answer in time; asking it again would only wait as long."""


def allow_private_hosts() -> bool:
    """For development against a shop running on this machine: RENDERER_ALLOW_PRIVATE_HOSTS=1."""
    return os.environ.get("RENDERER_ALLOW_PRIVATE_HOSTS") == "1"


def get(url) -> str:
    return Fetcher().get(url)


def get_image(url, max_bytes=MAX_IMAGE_BYTES, types=IMAGE_TYPES):
    """A product photo, with the same checks as a page. Returns (bytes, content type)."""
    return Fetcher(image_bytes=max_bytes, image_types=types).get(url, want="image")


def get_json(url, agent=None):
    """A JSON API that a shop's page loads its size chart from (see Page.kiwi_sizing), parsed."""
    return json.loads(Fetcher(agent=agent).get(url, want="json"))


def turned_away(host):
    host = text(host).lower()
    return next((site for site in TURNS_AWAY if host == site or host.endswith(f".{site}")), None)


def turned_away_message(host) -> str:
    return (f"{text(host).removeprefix('www.')} doesn't let apps read its pages. Paste its size chart, or just its size (like M), "
            "under \"Other ways to add clothes\".")


def turned_away_error(host) -> GaveUp:
    return GaveUp(turned_away_message(host), reason=f"{text(host).lower().removeprefix('www.')} doesn't let apps read its pages")


def site(url) -> str:
    """The site's name as people say it: "therealreal.com"."""
    try:
        host = urlsplit(text(url).strip()).hostname
    except ValueError:
        host = None
    return presence(text(host).lower().removeprefix("www.")) or "The store"


def allowed(address) -> bool:
    if allow_private_hosts():
        return True
    try:
        ip = ipaddress.ip_address(address.split("%")[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return not any(ip in network for network in BLOCKED)


class _Pinned(http.client.HTTPConnection):
    """A plain connection to the address that was checked, whatever the name resolves to by now."""

    def __init__(self, host, port, address, timeout):
        super().__init__(host, port, timeout=timeout)
        self.address = address

    def connect(self):
        self.sock = socket.create_connection((self.address, self.port), self.timeout)


class _PinnedTLS(http.client.HTTPSConnection):
    """A TLS connection to the address that was checked, its certificate checked against the site's name."""

    def __init__(self, host, port, address, timeout):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        sock = socket.create_connection((self.address, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class Fetcher:
    def __init__(self, image_bytes=MAX_IMAGE_BYTES, image_types=IMAGE_TYPES, agent=None):
        self.image_bytes = image_bytes
        self.image_types = image_types
        self.agent = agent
        self.deadline = None

    def get(self, url, redirects=0, want="page"):
        if self.deadline is None:
            self.deadline = time.monotonic() + DEADLINE
        return self.fetch(url, redirects, want)

    def remaining(self) -> float:
        left = self.deadline - time.monotonic()
        if left <= 0:
            raise TooSlow("That page took too long to answer. Try again, or paste its size chart, or just its size (like M), "
                          "under \"Other ways to add clothes\".", reason=f"{site(self.url)} took too long to answer")
        return min(TIMEOUT, max(left, 0.5))

    def fetch(self, url, redirects, want):
        self.url = url
        parts = self.parse(url)
        host = parts.hostname
        if turned_away(host):
            raise turned_away_error(host)
        connection = None
        try:
            connection = self.connect(parts, self.resolve(host))
            path = parts.path or "/"
            if parts.query:
                path += "?" + parts.query
            connection.request("GET", path, headers={"User-Agent": self.agent or USER_AGENT, "Accept": ACCEPT[want],
                                                     "Accept-Encoding": "identity", "Connection": "close"})
            connection.sock.settimeout(self.remaining())
            response = connection.getresponse()
            code = response.status
            if 300 <= code < 400:
                if redirects >= MAX_REDIRECTS:
                    raise GaveUp("That page redirects too many times.", reason=f"{site(url)} kept sending us elsewhere")
                location = response.getheader("Location")
                if not location:
                    raise GaveUp(f"The shop's site answered {code}. Check the link, or paste the size chart instead.",
                                 reason=f"{site(url)} answered with an error page")
                connection.close()
                return self.fetch(urljoin(url, location), redirects + 1, want)
            if 200 <= code < 300:
                return self.read_image(response, connection) if want == "image" else self.read_body(response, connection, want, host)
            if code in (401, 403, 429, 503):
                # Big shops often turn away any reader that isn't a person's browser. This doesn't pretend to be one.
                raise turned_away_error(host)
            raise GaveUp(f"The shop's site answered {code}. Check the link, or paste the size chart instead.",
                         reason=f"{site(url)} answered with an error page")
        except (OSError, http.client.HTTPException) as error:
            raise GaveUp(f"Couldn't load that page ({type(error).__name__}).", reason=f"{site(url)} couldn't be reached") from error
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def parse(url):
        try:
            parts = urlsplit(text(url).strip())
        except ValueError:
            raise Error("That doesn't look like a web link.") from None
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise Error("That doesn't look like a web link.")
        try:
            parts.port
        except ValueError:
            raise Error("That doesn't look like a web link.") from None
        return parts

    @staticmethod
    def resolve(host):
        """The system's resolver, IPv4 first."""
        try:
            found = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except (OSError, UnicodeError):
            found = []
        addresses = list(dict.fromkeys(info[4][0] for info in found))
        addresses.sort(key=lambda address: 1 if ":" in address else 0)
        if not addresses:
            raise Error("Couldn't find that website.")
        checked = [address for address in addresses if allowed(address)]
        if not checked:
            raise Error("That link points to a private address.")
        return checked

    def connect(self, parts, addresses):
        """Opens a connection to the first checked address that answers."""
        secure = parts.scheme == "https"
        port = parts.port or (443 if secure else 80)
        for index, address in enumerate(addresses):
            kind = _PinnedTLS if secure else _Pinned
            connection = kind(parts.hostname, port, address, self.remaining())
            try:
                connection.connect()
                return connection
            except OSError:
                connection.close()
                if index == len(addresses) - 1:
                    raise
        raise Error("Couldn't find that website.")

    def read_chunks(self, response, connection, limit, too_big):
        out = bytearray()
        while True:
            connection.sock.settimeout(self.remaining())
            chunk = response.read(CHUNK)
            if not chunk:
                return bytes(out)
            out.extend(chunk)
            if len(out) > limit:
                raise too_big()

    def read_image(self, response, connection):
        kind = text(response.getheader("Content-Type")).split(";")[0].strip()
        if not self.image_types.search(kind):
            raise Error("That isn't a photo.")

        def too_big():
            return Error("That photo is too big.")

        return self.read_chunks(response, connection, self.image_bytes, too_big), kind

    def read_body(self, response, connection, want, host):
        kind = text(response.getheader("Content-Type"))
        wanted = r"application/json" if want == "json" else r"text/html|application/xhtml"
        if not re.search(wanted, kind):
            raise Error("The shop's size chart service didn't answer with a chart." if want == "json" else "That link isn't a web page.")

        def too_big():
            return GaveUp("That page is too big to read.", reason=f"{site(self.url)} sent a page too big to read")

        raw = self.read_chunks(response, connection, MAX_BYTES, too_big)
        header = Message()
        header["Content-Type"] = kind
        charset = header.get_content_charset() or "utf-8"
        try:
            body = raw.decode(charset, errors="replace")
        except LookupError:
            body = raw.decode("utf-8", errors="replace")
        # Some shops answer with a bot check instead of the page (and a 200). This doesn't try to pass them.
        if want == "page" and len(body) < 20_000 and BOT_CHECK.search(body):
            raise turned_away_error(host)
        return body
