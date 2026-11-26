"""Read-only access to an npm compatible registry over HTTP.

Only the standard library is used: :mod:`urllib.request` sends the
requests and :mod:`json` parses the answers.  The client never calls the
npm command line tool, it works with the public registry API the same way
a browser does."""

import json
import time
import urllib.error
import urllib.request
from urllib.parse import quote
from models import Package


ACCEPT_HEADER = "application/json"

USER_AGENT = "depgraph/1.0"

DEFAULT_TIMEOUT = 20

RETRY_CODES = (406, 429, 500, 502, 503, 504)

MAX_ATTEMPTS = 3

RETRY_DELAY = 0.5

class RegistryError(Exception):
    """Raised when the registry cannot provide the requested data."""

class RegistryClient:
    """Minimal client that reads package documents from a registry."""

    def __init__(self, base_url, fetcher=None, timeout=DEFAULT_TIMEOUT):
        """Store the registry address and an optional custom fetcher."""
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._fetcher = fetcher or self._fetch_json

    def package(self, name, version):
        """Return the requested package with its direct dependencies."""
        manifest = self._fetch_manifest(name, version)
        resolved = manifest.get("version", version)
        dependencies = tuple(manifest.get("dependencies", {}).items())
        return Package(name=name, version=resolved,
                              dependencies=dependencies)

    def _fetch_manifest(self, name, version):
        """Read the manifest of one package version from the registry."""
        return self._fetcher(self._url(name, version))

    def _url(self, name, version):
        """Build the registry URL of a package manifest."""
        encoded = quote(name, safe="@")
        return f"{self.base_url}/{encoded}/{version}"

    def _fetch_json(self, url):
        """Download one JSON document, retrying temporary failures."""
        last_error = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                payload = self._read(url)
                break
            except urllib.error.HTTPError as exc:
                if exc.code not in RETRY_CODES:
                    raise RegistryError(
                        f"реестр вернул HTTP {exc.code} для {url}")
                last_error = exc
            except urllib.error.URLError as exc:
                raise RegistryError(f"нет связи с реестром: {exc.reason}")
            time.sleep(RETRY_DELAY * (attempt + 1))
        else:
            raise RegistryError(
                f"реестр недоступен после {MAX_ATTEMPTS} попыток: "
                f"{last_error}")
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            raise RegistryError(f"реестр вернул не JSON: {url}")

    def _read(self, url):
        """Read the raw body of one registry response."""
        request = urllib.request.Request(url, headers={
            "Accept": ACCEPT_HEADER,
            "User-Agent": USER_AGENT,
        })
        with urllib.request.urlopen(request,
                                    timeout=self.timeout) as response:
            return response.read().decode("utf-8")
