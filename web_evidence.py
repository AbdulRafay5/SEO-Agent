"""Optional bounded public HTTPS extraction. Never follow redirects."""
import http.client
import ipaddress
import socket
import ssl
import time
from html.parser import HTMLParser
from urllib.parse import urlsplit

MAX_BYTES = 512 * 1024


class PublicHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, address):
        super().__init__(host, port=443, timeout=5, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        # Connect to the validated numeric IP, retaining hostname verification.
        raw = socket.create_connection((self.address, 443), timeout=self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except Exception:
            raw.close()
            raise


def resolve_public(host):
    if not host or "." not in host or host.endswith(".") or "%" in host:
        raise ValueError("Use a public HTTPS hostname.")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("IP address URLs are not supported.")
    addresses = {item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    if not addresses or any(not ipaddress.ip_address(address).is_global or ipaddress.ip_address(address).is_multicast or ipaddress.ip_address(address).is_reserved for address in addresses):
        raise ValueError("Private or non-public addresses are not allowed.")
    return sorted(addresses)[0]


class PageText(HTMLParser):
    ignored = {"script", "style", "noscript", "nav", "footer", "header", "aside", "svg", "template", "form", "head"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocked = []
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in self.ignored:
            self.blocked.append(tag)

    def handle_endtag(self, tag):
        if self.blocked and self.blocked[-1] == tag:
            self.blocked.pop()

    def handle_data(self, data):
        if not self.blocked and data.strip():
            self.parts.append(" ".join(data.split()))


def extract_page(url):
    if not isinstance(url, str) or len(url) > 2048 or any(ord(c) <= 32 or ord(c) == 127 for c in url):
        raise ValueError("Invalid page URL.")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("Only public HTTPS pages on port 443 are supported.")
    host = parsed.hostname.encode("idna").decode("ascii")
    address = resolve_public(host)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    connection = PublicHTTPSConnection(host, address)
    deadline = time.monotonic() + 12
    try:
        connection.request("GET", path, headers={"User-Agent": "SEOStudioEvidence/1.0", "Accept": "text/html,text/plain", "Accept-Encoding": "identity"})
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError("Page unavailable or redirected. Use its final public HTTPS URL or paste an excerpt.")
        content_type = response.headers.get_content_type()
        if content_type not in {"text/html", "text/plain"} or response.headers.get("Content-Encoding", "identity").lower() != "identity":
            raise ValueError("Only uncompressed HTML and plain text are supported.")
        data = bytearray()
        while len(data) <= MAX_BYTES:
            if time.monotonic() > deadline:
                raise ValueError("Page download timed out.")
            chunk = response.read1(min(16384, MAX_BYTES + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > MAX_BYTES:
            raise ValueError("Page exceeds the extraction size limit.")
        decoded = data.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
        if content_type == "text/html":
            parser = PageText()
            parser.feed(decoded)
            decoded = "\n".join(parser.parts)
        text = decoded.strip()[:12000]
        if not text:
            raise ValueError("No readable text found.")
        return {"title": host, "url": url, "text": text, "kind": "webpage"}
    finally:
        connection.close()
