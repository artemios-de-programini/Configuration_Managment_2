"""Визуализатор графа зависимостей пакетов npm (единый модуль).

Модуль собран из исходных файлов проекта: проверка параметров,
модель пакета, работа с реестром, семантические версии, граф
зависимостей, тестовый репозиторий, отрисовка и точка входа CLI.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import quote
from urllib.parse import urlparse


# ======================================================================
# config.py
# ======================================================================
# Validation of the command line parameters of the visualizer.
#
# The module checks every option of the command line, reports all errors at
# once and builds an immutable configuration object that the rest of the
# program uses.  Validation rules match the assignment: the package name
# follows the npm naming rules, the repository is either an HTTP URL or an
# existing file in the test mode, the version is a semantic version or the
# word ``latest``, and the output file must be an SVG image.

NPM_NAME = re.compile(
    r"^(@[a-z0-9-~][a-z0-9-._~]*/)?[a-z0-9-~][a-z0-9-._~]*$")

TEST_NAME = re.compile(r"^[A-Z]+$")

SEMANTIC_VERSION = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")

ALLOWED_SCHEMES = ("http", "https")

FORBIDDEN_OUTPUT_CHARS = '<>:"|?*'

OUTPUT_EXTENSION = ".svg"

BOOL_VALUES = ("true", "false")

LATEST = "latest"

class ConfigError(Exception):
    """Raised when the configuration has one or more errors."""

    def __init__(self, messages):
        """Store every error message found during the validation."""
        super().__init__("; ".join(messages))
        self.messages = list(messages)

@dataclass(frozen=True)
class ToolConfig:
    """Validated parameters of one run of the visualizer."""

    package: str
    repo: str
    test_mode: bool
    version: str
    output: str
    ascii_tree: bool

    def describe(self):
        """Return the key: value lines of all parameters."""
        return [
            f"package: {self.package}",
            f"repo: {self.repo}",
            f"test_mode: {bool_text(self.test_mode)}",
            f"version: {self.version}",
            f"output: {self.output}",
            f"ascii_tree: {bool_text(self.ascii_tree)}",
        ]

def bool_text(value):
    """Return the command line spelling of a boolean value."""
    return "true" if value else "false"

def build_config(args):
    """Validate parsed arguments and return a configuration object."""
    errors = []
    test_mode = parse_bool(args.test_mode, "--test-mode", errors)
    ascii_tree = parse_bool(args.ascii_tree, "--ascii-tree", errors)
    check_package(args.package, test_mode, errors)
    check_repo(args.repo, test_mode, errors)
    check_version(args.version, errors)
    check_output(args.output, errors)
    if errors:
        raise ConfigError(errors)
    return ToolConfig(
        package=args.package,
        repo=args.repo,
        test_mode=test_mode,
        version=args.version,
        output=args.output,
        ascii_tree=ascii_tree,
    )

def parse_bool(value, option, errors):
    """Convert a true/false command line value into a boolean."""
    if value in BOOL_VALUES:
        return value == "true"
    errors.append(
        f"Ошибка {option}: нужно 'true' или 'false', дано '{value}'.")
    return False

def check_package(package, test_mode, errors):
    """Check the package name against the npm or the test rules."""
    if not package:
        errors.append("Ошибка --package: имя пакета не задано.")
        return
    if test_mode:
        if not TEST_NAME.match(package):
            errors.append(
                "Ошибка --package: в тестовом режиме допустимы только "
                f"заглавные латинские буквы, дано '{package}'.")
        return
    if not NPM_NAME.match(package):
        errors.append(
            f"Ошибка --package: неверное имя пакета '{package}'.")

def check_repo(repo, test_mode, errors):
    """Check the repository URL or the path to the test repository."""
    if not repo:
        errors.append("Ошибка --repo: адрес репозитория не задан.")
        return
    if test_mode:
        if not os.path.isfile(repo):
            errors.append(f"Ошибка --repo: файл '{repo}' не найден.")
        return
    parsed = urlparse(repo)
    if parsed.scheme not in ALLOWED_SCHEMES or not parsed.netloc:
        errors.append(f"Ошибка --repo: неверный URL '{repo}'.")

def check_version(version, errors):
    """Check that the version is a semantic version or the word latest."""
    if version == LATEST:
        return
    if not SEMANTIC_VERSION.match(version):
        errors.append(
            f"Ошибка --version: неверный формат '{version}'.")

def check_output(output, errors):
    """Check the name of the generated SVG image."""
    if not output:
        errors.append("Ошибка --output: имя файла не задано.")
        return
    if not output.endswith(OUTPUT_EXTENSION):
        errors.append(
            "Ошибка --output: имя файла должно заканчиваться "
            f"на '{OUTPUT_EXTENSION}'.")
        return
    if len(output) == len(OUTPUT_EXTENSION):
        errors.append(
            f"Ошибка --output: имя файла '{output}' пустое.")
        return
    if any(char in FORBIDDEN_OUTPUT_CHARS for char in output):
        errors.append(
            f"Ошибка --output: запрещённые символы в '{output}'.")
    elif os.path.basename(output) != output:
        errors.append(
            f"Ошибка --output: '{output}' не должен содержать путь.")


# ======================================================================
# models.py
# ======================================================================
# Data model of a package and its dependencies.
#
# The same structure describes packages of the real npm registry and nodes
# of the test repository: a name, a concrete version and the list of direct
# dependencies together with the version requirements.

@dataclass(frozen=True)
class Package:
    """One concrete version of a package with its direct dependencies."""

    name: str
    version: str
    dependencies: tuple = ()

    def key(self):
        """Return the unique identifier of the package version."""
        if not self.version:
            return self.name
        return f"{self.name}@{self.version}"

    def dependency_names(self):
        """Return the names of all direct dependencies."""
        return [name for name, _ in self.dependencies]


# ======================================================================
# registry.py
# ======================================================================
# Read-only access to an npm compatible registry over HTTP.
#
# Only the standard library is used: :mod:`urllib.request` sends the
# requests and :mod:`json` parses the answers.  The client never calls the
# npm command line tool, it works with the public registry API the same way
# a browser does.

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


# ======================================================================
# main.py
# ======================================================================
# Entry point of the npm dependency graph visualizer.
#
# Stage 2 adds the data collection: the program reads the manifest of the
# requested package version from the registry and prints every direct
# dependency.  Test repositories are supported starting with stage 3.

PROGRAM_NAME = "depgraph"

DESCRIPTION = "Визуализатор графа зависимостей пакетов npm."

EXIT_OK = 0

EXIT_CONFIG = 2

EXIT_SOURCE = 3

DEFAULT_REPO = "https://registry.npmjs.org"

TEST_MODE_NOT_READY = (
    "Ошибка: тестовый режим будет добавлен на этапе 3.")

def parse_args(argv=None):
    """Parse the command line parameters of the visualizer."""
    parser = argparse.ArgumentParser(
        prog=PROGRAM_NAME,
        description=DESCRIPTION,
    )
    parser.add_argument(
        "--package",
        required=True,
        help="имя анализируемого пакета",
    )
    parser.add_argument(
        "--repo",
        required=True,
        help="URL реестра или путь к файлу тестового репозитория",
    )
    parser.add_argument(
        "--test-mode",
        required=True,
        metavar="true|false",
        help="режим работы с тестовым репозиторием",
    )
    parser.add_argument(
        "--version",
        required=True,
        help="версия пакета или слово latest",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="имя файла с изображением графа в формате SVG",
    )
    parser.add_argument(
        "--ascii-tree",
        default="false",
        metavar="true|false",
        help="вывод зависимостей в виде ASCII-дерева",
    )
    return parser.parse_args(argv)

def show_config(tool_config):
    """Print every parameter of the run as a key: value line."""
    for line in tool_config.describe():
        print(line)

def show_dependencies(package):
    """Print every direct dependency of the package."""
    print(f"Прямые зависимости {package.key()}:")
    if not package.dependencies:
        print("  (нет)")
        return
    for name, requirement in sorted(package.dependencies):
        print(f"  {name}: {requirement}")

def read_package(tool_config):
    """Read the requested package from the registry."""
    client = RegistryClient(tool_config.repo)
    return client.package(tool_config.package, tool_config.version)

def run(tool_config):
    """Execute the configured run and return the exit code."""
    if tool_config.test_mode:
        print(TEST_MODE_NOT_READY, file=sys.stderr)
        return EXIT_SOURCE
    try:
        package = read_package(tool_config)
    except RegistryError as exc:
        print(f"Ошибка репозитория: {exc}", file=sys.stderr)
        return EXIT_SOURCE
    show_dependencies(package)
    return EXIT_OK

def main(argv=None):
    """Validate the configuration and collect the dependencies."""
    args = parse_args(argv)
    try:
        tool_config = build_config(args)
    except ConfigError as exc:
        for message in exc.messages:
            print(message, file=sys.stderr)
        return EXIT_CONFIG
    show_config(tool_config)
    return run(tool_config)


if __name__ == "__main__":
    sys.exit(main())
