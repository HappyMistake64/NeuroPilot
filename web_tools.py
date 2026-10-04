"""Explicit read-only web access: public HTTP(S), bounded size, checked redirects."""
import html
import ipaddress
import re
import socket
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener


def validate_url(url, whitelist=None):
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().rstrip(".")
    if parts.scheme not in {"http", "https"} or not host or parts.username or parts.password or parts.port not in {None, 80, 443}:
        raise ValueError("Povoleny jsou veřejné HTTP(S) adresy bez přihlašovacích údajů.")
    if whitelist is not None and not any(host == w.lower().rstrip('.') or host.endswith('.' + w.lower().rstrip('.')) for w in whitelist if w):
        raise ValueError("Adresa je mimo whitelist.")
    addresses = socket.getaddrinfo(host, parts.port or (443 if parts.scheme == "https" else 80), type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(entry[4][0]).is_global for entry in addresses):
        raise ValueError("Soukromé a lokální adresy nejsou povoleny.")
    return url


class CheckedRedirect(HTTPRedirectHandler):
    def __init__(self, whitelist):
        self.whitelist = whitelist
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl, self.whitelist)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_bytes(url, timeout=5, max_bytes=800000, whitelist=None):
    validate_url(url, whitelist)
    opener = build_opener(CheckedRedirect(whitelist))
    with opener.open(Request(url, headers={"User-Agent": "NeuroPilot/3.1 (read-only)"}), timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "").lower()
        if "text" not in content_type and "json" not in content_type:
            raise ValueError("Podporován je pouze text/HTML/JSON.")
        data = response.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError("Webová stránka překročila limit velikosti.")
        return content_type, data


def clean_text(data):
    text = data.decode("utf-8", "replace")
    text = re.sub(r"(?is)<(script|style)\b.*?>.*?</\1\s*>", " ", text)
    text = re.sub(r"(?s)<[^>]*>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()[:20000]
