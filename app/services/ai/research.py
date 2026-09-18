"""Research fetches are explicit user-selected, administrator-allowed public HTTPS URLs.

DNS is resolved once per hop and the validated address is pinned to the socket;
TLS still validates the original hostname. Redirects repeat all checks. No browser,
credentials, cookies, uploads or arbitrary user headers are available to a model.
"""

import asyncio
import http.client
import ipaddress
import os
import re
import socket
import ssl
from urllib.parse import urljoin, urlsplit
from fastapi import HTTPException

MAX_BYTES = 100000


def validate_url(url, allowed_urls):
    if url not in allowed_urls or len(url) > 1000:
        raise HTTPException(403, "Research URL must be explicitly selected by the user")
    parsed = urlsplit(url)
    hosts = {
        h.strip().lower()
        for h in os.environ.get("WORKFORCE_RESEARCH_ALLOWED_HOSTS", "").split(",")
        if h.strip()
    }
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.hostname.lower() not in hosts
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or parsed.query
        or parsed.fragment
        or "\\" in url
    ):
        raise HTTPException(422, "Research URL is outside the configured public HTTPS policy")
    return parsed


def resolve_public(host):
    addresses = list(
        {item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    )
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise HTTPException(422, "Non-public research address forbidden")
    return sorted(addresses)[0]


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, address):
        super().__init__(host, timeout=8, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        raw = socket.create_connection((self.address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except Exception:
            raw.close()
            raise


def fetch_public(url, allowed_urls):
    current = url
    for _ in range(4):
        parsed = validate_url(current, allowed_urls)
        address = resolve_public(parsed.hostname)
        connection = PinnedHTTPSConnection(parsed.hostname, address)
        try:
            connection.request(
                "GET",
                parsed.path or "/",
                headers={"Accept": "text/plain, text/html", "User-Agent": "GlobexaResearch/1.0"},
            )
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                current = urljoin(current, response.getheader("Location", ""))
                continue
            if response.status != 200:
                raise HTTPException(502, "Research source unavailable")
            content_type = response.getheader("Content-Type", "").split(";")[0].lower()
            if content_type not in ("text/plain", "text/html"):
                raise HTTPException(422, "Research supports only bounded text documents")
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise HTTPException(422, "Research source too large")
            content = raw.decode("utf-8", errors="replace")
            content = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", "", content, flags=re.I | re.S)
            content = re.sub(r"<[^>]+>", " ", content)
            return {
                "url": current,
                "content": content[:12000],
                "untrusted": True,
                "truncated": len(content) > 12000,
            }
        finally:
            connection.close()
    raise HTTPException(422, "Too many research redirects")


async def research_web(url, allowed_urls):
    return await asyncio.wait_for(asyncio.to_thread(fetch_public, url, allowed_urls), timeout=35)
