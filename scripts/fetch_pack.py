#!/usr/bin/env python3
"""Downloads a community pack from an allow-listed host, for
community-pack-validate.yml. Two things make this more than a plain `curl`:

1. The allow-list check runs on every hop, not just the URL the issue
   submitter typed. `requests`/`curl -L` would happily follow a redirect
   from an allowed host to an arbitrary one; here every redirect target is
   re-validated against the same allow-list before being followed.
2. Before connecting, the target host's resolved IPs are checked against
   private/loopback/link-local/reserved ranges (this also catches the
   cloud-metadata address, 169.254.169.254) and rejected. The allow-listed
   hosts are all public multi-tenant platforms (GitHub, Google Drive, MediaFire) whose
   DNS we don't control, so this is what actually stands in for "no SSRF",
   not the hostname string match by itself.

Google Drive (`kind: "google-drive"` in the allow-list) needs a second
request: the first response for a file too large to virus-scan is an HTML
warning page, not the file -- the real bytes come from
drive.usercontent.google.com/download with a confirm token.

MediaFire (`kind: "mediafire"`) is the same shape: the /file/ share URL
is an HTML page, and the zip is on downloadN.mediafire.com (matched via
`host_ends_with: ".mediafire.com"`).

Usage:
  python3 scripts/fetch_pack.py <url> <out-path> --max-bytes N
      [--allowlist scripts/pack_host_allowlist.json]

Exit 0 and writes <out-path> on success. Exit 1 with a message on stderr for
any rejection (disallowed host, private-IP target, over the size cap,
malformed Drive link) -- the workflow step treats any non-zero exit as a
download failure, same as a network error.
"""
import html as htmlmod
import ipaddress
import json
import re
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_ALLOWLIST = "scripts/pack_host_allowlist.json"
USER_AGENT = "MesenCE-community-pack-validator/1.0"


def load_allowlist(path):
    with open(path) as f:
        return json.load(f)["hosts"]


def match_host(url, hosts):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        return None
    for entry in hosts:
        host = entry.get("host") or ""
        suffix = entry.get("host_ends_with") or ""
        host_match = bool(host) and parsed.netloc == host
        suffix_match = bool(suffix) and parsed.netloc.endswith(suffix)
        if not (host_match or suffix_match):
            continue
        substrings = entry.get("path_contains_any")
        if substrings and not any(s in parsed.path for s in substrings):
            continue
        return entry
    return None


def assert_public_host(host):
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise ValueError(f"could not resolve host {host!r}: {e}")
    for family, _, _, _, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ValueError(f"host {host!r} resolved to non-public address {ip}")


def open_validated(url, hosts, max_redirects=5):
    """Follows redirects manually, re-checking the allow-list and DNS on
    every hop, instead of trusting urllib's/curl's built-in follower."""
    for _ in range(max_redirects + 1):
        entry = match_host(url, hosts)
        if entry is None:
            raise ValueError(f"host not allow-listed: {urllib.parse.urlparse(url).netloc}")
        assert_public_host(urllib.parse.urlparse(url).netloc)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            resp = urllib.request.urlopen(req, timeout=30)  # noqa: S310 - host validated above
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308):
                location = e.headers.get("Location")
                if not location:
                    raise ValueError(f"redirect ({e.code}) with no Location header")
                url = urllib.parse.urljoin(url, location)
                continue
            raise
        return resp, entry
    raise ValueError("too many redirects")


MEDIAFIRE_DOWNLOAD = re.compile(
    r"""href=["'](https://download\d+\.mediafire\.com/[^"'<>]+)["']""",
    re.IGNORECASE,
)


def extract_mediafire_download_url(page_html):
    m = MEDIAFIRE_DOWNLOAD.search(page_html)
    return htmlmod.unescape(m.group(1)) if m else None


def extract_drive_id(url):
    parsed = urllib.parse.urlparse(url)
    m = re.search(r"/d/([a-zA-Z0-9_-]+)", parsed.path)
    if m:
        return m.group(1)
    qs = urllib.parse.parse_qs(parsed.query)
    if "id" in qs:
        return qs["id"][0]
    raise ValueError(f"could not extract a file id from Google Drive URL: {url}")


def stream_to_file(resp, out_path, max_bytes):
    declared = resp.headers.get("Content-Length")
    if declared is not None and int(declared) > max_bytes:
        raise ValueError(f"Content-Length ({declared}) exceeds the {max_bytes}-byte cap")
    written = 0
    with open(out_path, "wb") as f:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if written > max_bytes:
                raise ValueError(f"download exceeded the {max_bytes}-byte cap mid-transfer")
            f.write(chunk)
    return written


def fetch_direct(url, hosts, out_path, max_bytes):
    resp, _ = open_validated(url, hosts)
    return stream_to_file(resp, out_path, max_bytes)


def fetch_google_drive(url, hosts, out_path, max_bytes):
    file_id = extract_drive_id(url)
    first_url = f"https://drive.google.com/uc?export=download&id={file_id}"
    resp, _ = open_validated(first_url, hosts)
    body_preview = resp.read(1024 * 1024)
    content_type = resp.headers.get("Content-Type", "")
    if "text/html" in content_type:
        # Large-file virus-scan-warning page; the real bytes are one hop
        # away with a confirm token. Small files return the bytes directly
        # from the first request instead, so this branch is conditional.
        second_url = (
            f"https://drive.usercontent.google.com/download"
            f"?id={file_id}&export=download&confirm=t"
        )
        resp2, _ = open_validated(second_url, hosts)
        return stream_to_file(resp2, out_path, max_bytes)
    declared = resp.headers.get("Content-Length")
    if declared is not None and int(declared) > max_bytes:
        raise ValueError(f"Content-Length ({declared}) exceeds the {max_bytes}-byte cap")
    written = len(body_preview)
    if written > max_bytes:
        raise ValueError(f"download exceeded the {max_bytes}-byte cap mid-transfer")
    with open(out_path, "wb") as f:
        f.write(body_preview)
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if written > max_bytes:
                raise ValueError(f"download exceeded the {max_bytes}-byte cap mid-transfer")
            f.write(chunk)
    return written


def fetch_mediafire(url, hosts, out_path, max_bytes):
    resp, _ = open_validated(url, hosts)
    content_type = resp.headers.get("Content-Type", "")
    if "text/html" not in content_type.lower():
        return stream_to_file(resp, out_path, max_bytes)
    page = resp.read(16 * 1024 * 1024).decode("utf-8", errors="replace")
    href = extract_mediafire_download_url(page)
    if not href:
        raise ValueError("mediafire share page has no downloadN.mediafire.com link")
    resp2, _ = open_validated(href, hosts)
    return stream_to_file(resp2, out_path, max_bytes)


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    url = argv[1]
    out_path = argv[2]
    max_bytes = None
    allowlist_path = DEFAULT_ALLOWLIST
    rest = argv[3:]
    i = 0
    while i < len(rest):
        if rest[i] == "--max-bytes":
            max_bytes = int(rest[i + 1])
            i += 2
        elif rest[i] == "--allowlist":
            allowlist_path = rest[i + 1]
            i += 2
        else:
            print(f"unknown argument: {rest[i]}", file=sys.stderr)
            return 2
    if max_bytes is None:
        print("--max-bytes is required", file=sys.stderr)
        return 2

    hosts = load_allowlist(allowlist_path)
    entry = match_host(url, hosts)
    if entry is None:
        print(f"host not allow-listed: {urllib.parse.urlparse(url).netloc}", file=sys.stderr)
        return 1

    try:
        if entry["kind"] == "google-drive":
            written = fetch_google_drive(url, hosts, out_path, max_bytes)
        elif entry["kind"] == "mediafire":
            written = fetch_mediafire(url, hosts, out_path, max_bytes)
        else:
            written = fetch_direct(url, hosts, out_path, max_bytes)
    except (ValueError, urllib.error.URLError, OSError) as e:
        print(f"download failed: {e}", file=sys.stderr)
        return 1

    print(f"wrote {out_path} ({written} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
