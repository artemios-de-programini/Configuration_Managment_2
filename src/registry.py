"""Read-only access to an npm compatible registry over HTTP.

Only the standard library is used: :mod:`urllib.request` sends the
requests and :mod:`json` parses the answers.  The client never calls the
npm command line tool, it works with the public registry API the same way
a browser does.  Version requirements are resolved with :mod:`semver`.

A package document (packument) is downloaded once per package and kept in
memory, so a graph of several dozen packages costs one request per
package."""

import json
import time
import urllib.error
import urllib.request
from urllib.parse import quote
from models import Package, SourceError
from semver import LATEST_WORD, pick_version


ACCEPT_HEADER = "application/vnd.npm.install-v1+json"

USER_AGENT = "depgraph/1.0"

DEFAULT_TIMEOUT = 20

RETRY_CODES = (406, 429, 500, 502, 503, 504)

MAX_ATTEMPTS = 3

RETRY_DELAY = 0.5

class RegistryError(SourceError):
    """Raised when the registry cannot provide the requested data."""

class RegistryClient:
    """Minimal client that reads package documents from a registry."""

    def __init__(self, base_url, fetcher=None, timeout=DEFAULT_TIMEOUT):
        """Store the registry address and an optional custom fetcher."""
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._fetcher = fetcher or self._fetch_json
        self._packuments = {}

    def resolve(self, name, requirement):
        """Return the package version that satisfies the requirement."""
        document = self.packument(name)
        versions = document.get("versions", {})
        latest = document.get("dist-tags", {}).get(LATEST_WORD)
        chosen = pick_version(versions, requirement, latest)
        if chosen is None:
            raise RegistryError(
                f"не найдена версия {name} для требования "
                f"'{requirement}'")
        manifest = versions[chosen]
        dependencies = tuple(manifest.get("dependencies", {}).items())
        return Package(name=name, version=chosen,
                              dependencies=dependencies)

    def packument(self, name):
        """Return the cached document with all versions of a package."""
        if name not in self._packuments:
            self._packuments[name] = self._fetcher(self._package_url(name))
        return self._packuments[name]

    def _package_url(self, name):
        """Build the registry URL of a package document."""
        return f"{self.base_url}/{quote(name, safe='@')}"

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
