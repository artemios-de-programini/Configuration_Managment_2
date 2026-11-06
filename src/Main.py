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
import xml.etree.ElementTree as ET
from collections import deque
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
    reverse: bool

    def describe(self):
        """Return the key: value lines of all parameters."""
        return [
            f"package: {self.package}",
            f"repo: {self.repo}",
            f"test_mode: {bool_text(self.test_mode)}",
            f"version: {self.version}",
            f"output: {self.output}",
            f"ascii_tree: {bool_text(self.ascii_tree)}",
            f"reverse: {bool_text(self.reverse)}",
        ]

def bool_text(value):
    """Return the command line spelling of a boolean value."""
    return "true" if value else "false"

def build_config(args):
    """Validate parsed arguments and return a configuration object."""
    errors = []
    test_mode = parse_bool(args.test_mode, "--test-mode", errors)
    ascii_tree = parse_bool(args.ascii_tree, "--ascii-tree", errors)
    reverse = parse_bool(args.reverse, "--reverse", errors)
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
        reverse=reverse,
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
# Data model of a package and the common source errors.
#
# The same structure describes packages of the real npm registry and nodes
# of the test repository: a name, a concrete version and the list of direct
# dependencies together with the version requirements.

class SourceError(Exception):
    """Base class of the errors raised by a dependency source."""

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
# semver.py
# ======================================================================
# Semantic versions and npm style version ranges.
#
# Only a practical subset of the npm syntax is supported: exact versions,
# partial versions such as ``1.2`` or ``1.x``, the wildcard ``*``, the
# operators ``^``, ``~``, ``>=``, ``<=``, ``>``, ``<``, ``=`` and
# alternatives separated by ``||``.  Git and file requirements are not
# version ranges, so the caller reports them as unresolved dependencies.
#
# A version is compared as the tuple ``(major, minor, patch, release)``
# where ``release`` sorts a pre-release before the final release, exactly
# as the semantic versioning specification requires.

VERSION_PATTERN = re.compile(
    r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$")

COMPARATOR_SPACES = re.compile(r"(>=|<=|>|<|=|\^|~)\s+")

WILDCARDS = ("", "*", "x", "X")

ALTERNATIVE = "||"

CARET = "^"

TILDE = "~"

COMPARATORS = (">=", "<=", ">", "<", "=")

PART_DELIMITER = "."

PRERELEASE_DELIMITER = "-"

LATEST_WORD = "latest"

MAJOR_INDEX = 0

MINOR_INDEX = 1

PATCH_INDEX = 2

ONE_PART = 1

TWO_PARTS = 2

THREE_PARTS = 3

PRERELEASE_RANK = 0

RELEASE_RANK = 1

ZERO = 0

EMPTY_KEY = (ZERO, ZERO, ZERO, (PRERELEASE_RANK,))

def version_key(text):
    """Return a sortable key of a semantic version or None."""
    match = VERSION_PATTERN.match(text.strip())
    if not match:
        return None
    major, minor, patch = (int(match.group(index))
                           for index in (1, 2, 3))
    return (major, minor, patch, prerelease_key(match.group(4)))

def prerelease_key(text):
    """Build a key that puts a pre-release before the release."""
    if not text:
        return (RELEASE_RANK,)
    parts = []
    for chunk in text.split(PART_DELIMITER):
        if chunk.isdigit():
            parts.append((PRERELEASE_RANK, int(chunk), ""))
        else:
            parts.append((RELEASE_RANK, ZERO, chunk))
    return (PRERELEASE_RANK, tuple(parts))

def is_prerelease(key):
    """Tell whether a parsed version is a pre-release."""
    return key[3][0] == PRERELEASE_RANK

def satisfies(version, requirement):
    """Check whether a version satisfies an npm style requirement."""
    key = version_key(version)
    if key is None:
        return False
    normalized = COMPARATOR_SPACES.sub(r"\1", requirement)
    allow_prerelease = PRERELEASE_DELIMITER in normalized
    if is_prerelease(key) and not allow_prerelease:
        return False
    return any(matches_all(key, part.strip())
               for part in normalized.split(ALTERNATIVE))

def pick_version(versions, requirement, latest=None):
    """Return the highest version that satisfies the requirement."""
    names = list(versions)
    if not names:
        return None
    text = requirement.strip()
    if text in WILDCARDS or text == LATEST_WORD:
        if latest in versions:
            return latest
        return highest(names)
    if text in versions:
        return text
    matched = [name for name in names if satisfies(name, text)]
    if not matched:
        return None
    return highest(matched)

def highest(versions):
    """Return the highest version of the list."""
    return max(versions, key=lambda text: version_key(text) or EMPTY_KEY)

def matches_all(key, alternative):
    """Check all space separated comparators of one alternative."""
    tokens = alternative.split()
    if not tokens:
        return True
    return all(matches_one(key, token) for token in tokens)

def matches_one(key, token):
    """Check one comparator, caret, tilde or partial version."""
    if token in WILDCARDS:
        return True
    if token.startswith(CARET):
        return caret_matches(key, token[len(CARET):])
    if token.startswith(TILDE):
        return tilde_matches(key, token[len(TILDE):])
    for comparator in COMPARATORS:
        if token.startswith(comparator):
            return compare(key, comparator, token[len(comparator):])
    return partial_matches(key, token)

def caret_matches(key, text):
    """Check the caret range: compatible with the same major version."""
    base = loose_key(text)
    if base is None or key < base:
        return False
    if base[MAJOR_INDEX] > ZERO:
        return key[MAJOR_INDEX] == base[MAJOR_INDEX]
    if base[MINOR_INDEX] > ZERO:
        return (key[MAJOR_INDEX] == ZERO
                and key[MINOR_INDEX] == base[MINOR_INDEX])
    return (key[MAJOR_INDEX] == ZERO and key[MINOR_INDEX] == ZERO
            and key[PATCH_INDEX] == base[PATCH_INDEX])

def tilde_matches(key, text):
    """Check the tilde range: allows patch level changes only."""
    base = loose_key(text)
    if base is None or key < base:
        return False
    if specified_parts(text) == ONE_PART:
        return key[MAJOR_INDEX] == base[MAJOR_INDEX]
    return (key[MAJOR_INDEX] == base[MAJOR_INDEX]
            and key[MINOR_INDEX] == base[MINOR_INDEX])

def compare(key, comparator, text):
    """Compare a version key with a bound of a comparator."""
    bound = loose_key(text)
    if bound is None:
        return False
    if comparator == ">=":
        return key >= bound
    if comparator == "<=":
        return key <= bound
    if comparator == ">":
        return key > bound
    if comparator == "<":
        return key < bound
    return key == bound

def partial_matches(key, token):
    """Check a partial version such as 1, 1.2 or 1.2.x."""
    count = specified_parts(token)
    if count == ZERO:
        return False
    values = [int(part) for part in token.split(PART_DELIMITER)[:count]]
    if count == ONE_PART:
        return key[MAJOR_INDEX] == values[0]
    if count == TWO_PARTS:
        return (key[MAJOR_INDEX] == values[0]
                and key[MINOR_INDEX] == values[1])
    return compare(key, "=", token)

def specified_parts(text):
    """Count the numeric parts before the first wildcard."""
    count = 0
    for part in text.split(PART_DELIMITER):
        if not part.isdigit():
            break
        count += 1
    return count

def loose_key(text):
    """Parse a possibly partial version into a full version key."""
    if PRERELEASE_DELIMITER in text:
        return version_key(text)
    numbers = []
    for part in text.strip().split(PART_DELIMITER):
        if not part.isdigit():
            break
        numbers.append(int(part))
    if not numbers:
        return None
    while len(numbers) < THREE_PARTS:
        numbers.append(ZERO)
    return (numbers[MAJOR_INDEX], numbers[MINOR_INDEX],
            numbers[PATCH_INDEX], (RELEASE_RANK,))


# ======================================================================
# registry.py
# ======================================================================
# Read-only access to an npm compatible registry over HTTP.
#
# Only the standard library is used: :mod:`urllib.request` sends the
# requests and :mod:`json` parses the answers.  The client never calls the
# npm command line tool, it works with the public registry API the same way
# a browser does.  Version requirements are resolved with :mod:`semver`.
#
# A package document (packument) is downloaded once per package and kept in
# memory, so a graph of several dozen packages costs one request per
# package.

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


# ======================================================================
# testrep.py
# ======================================================================
# Reader of the test repository file.
#
# The test mode replaces the network registry with a small text file that
# describes the dependency graph directly:
#
# ```text
# # имя пакета : список прямых зависимостей
# A: B C
# B: C
# C:
# ```
#
# Package names consist of capital Latin letters only.  Every dependency
# must be declared somewhere in the file, which makes the graph complete
# and catches typos.

NAME_PATTERN = re.compile(r"^[A-Z]+$")

SEPARATOR = ":"

COMMENT = "#"

REQUIREMENT = ""

class TestRepositoryError(SourceError):
    """Raised when the test repository file is missing or broken."""

class TestRepository:
    """Dependency graph described by a text file instead of the network."""

    def __init__(self, path):
        """Read the file and build the in-memory dependency table."""
        self.path = path
        self.packages = {}
        self._load()

    def resolve(self, name, requirement=REQUIREMENT):
        """Return the package of the test repository by its name."""
        if name not in self.packages:
            raise TestRepositoryError(
                f"пакет '{name}' не найден в тестовом репозитории")
        return Package(name=name, version="",
                              dependencies=self.packages[name])

    def names(self):
        """Return all package names of the repository."""
        return sorted(self.packages)

    def _load(self):
        """Read every line of the file and validate the collected graph."""
        try:
            with open(self.path, encoding="utf-8") as handle:
                lines = handle.readlines()
        except OSError as exc:
            raise TestRepositoryError(
                f"не удалось прочитать '{self.path}': {exc}")
        for number, raw in enumerate(lines, 1):
            self._parse_line(raw, number)
        self._check_references()

    def _parse_line(self, raw, number):
        """Parse one line of the test repository file."""
        line = raw.strip()
        if not line or line.startswith(COMMENT):
            return
        if SEPARATOR not in line:
            raise TestRepositoryError(
                f"строка {number}: нет разделителя '{SEPARATOR}'")
        left, right = line.split(SEPARATOR, 1)
        name = left.strip()
        if not NAME_PATTERN.match(name):
            raise TestRepositoryError(
                f"строка {number}: неверное имя пакета '{name}'")
        if name in self.packages:
            raise TestRepositoryError(
                f"строка {number}: пакет '{name}' уже определён")
        dependencies = tuple(
            (item, REQUIREMENT) for item in right.split())
        for dependency, _ in dependencies:
            if not NAME_PATTERN.match(dependency):
                raise TestRepositoryError(
                    f"строка {number}: неверное имя зависимости "
                    f"'{dependency}'")
        self.packages[name] = dependencies

    def _check_references(self):
        """Make sure that every dependency is declared in the file."""
        for name, dependencies in self.packages.items():
            for dependency, _ in dependencies:
                if dependency not in self.packages:
                    raise TestRepositoryError(
                        f"пакет '{name}' зависит от необъявленного "
                        f"пакета '{dependency}'")


# ======================================================================
# graph.py
# ======================================================================
# Breadth first traversal of the dependency graph.
#
# The graph is built with an explicit queue, so no recursion is used and a
# very deep dependency tree cannot hit the recursion limit.  A package is
# expanded exactly once, which also stops the traversal on cyclic
# dependencies: a back edge is stored in the graph, but the package is not
# queued again.

WHITE = 0

GRAY = 1

BLACK = 2

ROOT_LEVEL = 0

class DependencyGraph:
    """Nodes, edges and traversal order of a dependency graph."""

    def __init__(self):
        """Create an empty graph."""
        self.packages = {}
        self.order = []
        self.edges = []
        self.problems = []

    def add_package(self, package):
        """Add a package to the graph and to the BFS order."""
        if package.key() in self.packages:
            return
        self.packages[package.key()] = package
        self.order.append(package.key())

    def add_edge(self, source_key, target_key):
        """Add one directed dependency edge without duplicates."""
        edge = (source_key, target_key)
        if edge not in self.edges:
            self.edges.append(edge)

    def add_problem(self, source_key, name, message):
        """Remember a dependency that could not be resolved."""
        self.problems.append((source_key, name, message))

    def children(self, key):
        """Return the direct dependencies of a package."""
        return [target for source, target in self.edges if source == key]

    def parents(self, key):
        """Return the packages that depend on the given package."""
        return [source for source, target in self.edges if target == key]

    def root(self):
        """Return the key of the first package of the traversal."""
        return self.order[0] if self.order else ""

    def levels(self):
        """Return the shortest distance from the root for every package."""
        levels = {}
        if not self.order:
            return levels
        start = self.root()
        levels[start] = ROOT_LEVEL
        queue = deque([start])
        while queue:
            current = queue.popleft()
            for child in self.children(current):
                if child in levels:
                    continue
                levels[child] = levels[current] + 1
                queue.append(child)
        return levels

    def cycle(self):
        """Return one dependency cycle as a list of keys or None."""
        colors = {key: WHITE for key in self.order}
        for start in self.order:
            if colors[start] != WHITE:
                continue
            found = self._walk(start, colors)
            if found:
                return found
        return None

    def _walk(self, start, colors):
        """Search one cycle with an explicit stack instead of recursion."""
        path = [start]
        stack = [(start, iter(self.children(start)))]
        colors[start] = GRAY
        while stack:
            node, iterator = stack[-1]
            child = next(iterator, None)
            if child is None:
                stack.pop()
                path.pop()
                colors[node] = BLACK
                continue
            if colors[child] == GRAY:
                return path[path.index(child):] + [child]
            if colors[child] == WHITE:
                colors[child] = GRAY
                path.append(child)
                stack.append((child, iter(self.children(child))))
        return None

def build_graph(source, root_package):
    """Build the dependency graph from the root package with BFS."""
    dependency_graph = DependencyGraph()
    dependency_graph.add_package(root_package)
    queue = deque([root_package])
    while queue:
        current = queue.popleft()
        for name, requirement in current.dependencies:
            child = resolve_dependency(source, current, name,
                                       requirement, dependency_graph)
            if child is None:
                continue
            dependency_graph.add_edge(current.key(), child.key())
            if child.key() in dependency_graph.packages:
                continue
            dependency_graph.add_package(child)
            queue.append(child)
    return dependency_graph

def build_full_graph(repository):
    """Build the graph of every package of the test repository."""
    dependency_graph = DependencyGraph()
    for name in repository.names():
        dependency_graph.add_package(repository.resolve(name))
    for name in repository.names():
        for dependency, _ in repository.packages[name]:
            dependency_graph.add_edge(name, dependency)
    return dependency_graph

def reverse_edges(dependency_graph):
    """Build a graph with the same packages and inverted edges."""
    inverted = DependencyGraph()
    for key in dependency_graph.order:
        inverted.add_package(dependency_graph.packages[key])
    for source, target in dependency_graph.edges:
        inverted.add_edge(target, source)
    return inverted

def reachable(dependency_graph, start_key):
    """Return the keys reachable from start_key in BFS order."""
    if start_key not in dependency_graph.packages:
        return []
    order = []
    visited = {start_key}
    queue = deque([start_key])
    while queue:
        current = queue.popleft()
        for child in dependency_graph.children(current):
            if child in visited:
                continue
            visited.add(child)
            order.append(child)
            queue.append(child)
    return order

def resolve_dependency(source, current, name, requirement,
                       dependency_graph):
    """Resolve one dependency and remember the problem if it fails."""
    try:
        return source.resolve(name, requirement)
    except SourceError as exc:
        dependency_graph.add_problem(current.key(), name, str(exc))
        return None


# ======================================================================
# render.py
# ======================================================================
# Graphviz text and SVG rendering of the dependency graph.
#
# The module turns the graph into three representations:
#
# * Graphviz DOT text, the format used by the ``dot`` tool;
# * an SVG picture drawn without any external program: nodes are placed on
#   the BFS levels of the graph and connected with arrows;
# * an ASCII tree for the terminal.
#
# The SVG document is built with :mod:`xml.etree.ElementTree`, so the
# output is always well formed XML with correctly escaped labels.

SVG_NAMESPACE = "http://www.w3.org/2000/svg"

SVG_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>\n'

NODE_WIDTH = 190

NODE_HEIGHT = 46

COLUMN_GAP = 80

ROW_GAP = 18

MARGIN = 36

FONT_SIZE = 12

FONT_FAMILY = "Helvetica, Arial, sans-serif"

ROOT_FILL = "#dbeafe"

NODE_FILL = "#f8fafc"

NODE_STROKE = "#334155"

EDGE_COLOR = "#64748b"

TEXT_COLOR = "#0f172a"

MAX_LABEL = 26

TRUNCATED = 23

ELLIPSIS = "..."

NO_LEVELS = 0

BRANCH = "├── "

LAST_BRANCH = "└── "

VERTICAL = "│   "

SPACE = "    "

REPEAT = " (повтор)"

def dot_escape(text):
    """Escape a label for the Graphviz DOT language."""
    return text.replace("\\", "\\\\").replace('"', '\\"')

def to_dot(dependency_graph, root_key):
    """Return the Graphviz DOT description of the graph."""
    lines = [
        "digraph dependencies {",
        '    rankdir="LR";',
        '    node [shape=box, style="rounded", fontname="Helvetica"];',
        f'    "{dot_escape(root_key)}" [style="rounded,filled", '
        f'fillcolor="{ROOT_FILL}"];',
    ]
    for key in dependency_graph.order:
        if key == root_key:
            continue
        lines.append(f'    "{dot_escape(key)}";')
    for source, target in dependency_graph.edges:
        lines.append(
            f'    "{dot_escape(source)}" -> "{dot_escape(target)}";')
    lines.append("}")
    return "\n".join(lines) + "\n"

def short_label(key):
    """Shorten a long package label for the picture."""
    if len(key) <= MAX_LABEL:
        return key
    return key[:TRUNCATED] + ELLIPSIS

def layout(dependency_graph):
    """Return the position and the size of every node of the picture."""
    levels = dependency_graph.levels()
    rows = {}
    for key in dependency_graph.order:
        rows.setdefault(levels.get(key, NO_LEVELS), []).append(key)
    positions = {}
    for level, keys in rows.items():
        for index, key in enumerate(keys):
            positions[key] = _position(level, index)
    width = _picture_width(len(rows) - 1)
    height = _picture_height(max((len(keys) for keys in rows.values()),
                                 default=0))
    return positions, width, height

def _position(level, index):
    """Return the top left corner of a node on the given level."""
    left = MARGIN + level * (NODE_WIDTH + COLUMN_GAP)
    top = MARGIN + index * (NODE_HEIGHT + ROW_GAP)
    return left, top

def _picture_width(levels):
    """Return the width of the picture for the number of levels."""
    return MARGIN * 2 + (levels + 1) * NODE_WIDTH + levels * COLUMN_GAP

def _picture_height(rows):
    """Return the height of the picture for the longest level."""
    return MARGIN * 2 + rows * NODE_HEIGHT + (rows - 1) * ROW_GAP

def to_svg(dependency_graph, root_key):
    """Return an SVG document with a layered drawing of the graph."""
    positions, width, height = layout(dependency_graph)
    svg = ET.Element("svg", {
        "xmlns": SVG_NAMESPACE,
        "width": str(width),
        "height": str(height),
        "viewBox": f"0 0 {width} {height}",
    })
    _add_marker(svg)
    edges = ET.SubElement(svg, "g", {"stroke": EDGE_COLOR,
                                     "fill": "none"})
    for source, target in dependency_graph.edges:
        _add_edge(edges, positions, source, target)
    nodes = ET.SubElement(svg, "g")
    for key in dependency_graph.order:
        _add_node(nodes, positions[key], key, key == root_key)
    tree = ET.ElementTree(svg)
    ET.indent(tree, space="  ")
    return SVG_DECLARATION + ET.tostring(svg, encoding="unicode") + "\n"

def _add_marker(svg):
    """Add the arrow head definition used by every edge."""
    defs = ET.SubElement(svg, "defs")
    marker = ET.SubElement(defs, "marker", {
        "id": "arrow",
        "viewBox": "0 0 10 10",
        "refX": "9",
        "refY": "5",
        "markerWidth": "6",
        "markerHeight": "6",
        "orient": "auto-start-reverse",
    })
    ET.SubElement(marker, "path", {
        "d": "M 0 0 L 10 5 L 0 10 z",
        "fill": EDGE_COLOR,
    })

def _add_edge(parent, positions, source, target):
    """Draw one arrow between two nodes."""
    source_left, source_top = positions[source]
    target_left, target_top = positions[target]
    start_x = source_left + NODE_WIDTH
    start_y = source_top + NODE_HEIGHT // 2
    end_x = target_left
    end_y = target_top + NODE_HEIGHT // 2
    ET.SubElement(parent, "line", {
        "x1": str(start_x),
        "y1": str(start_y),
        "x2": str(end_x),
        "y2": str(end_y),
        "stroke-width": "1.4",
        "marker-end": "url(#arrow)",
    })

def _add_node(parent, position, key, is_root):
    """Draw one rounded box with the package label."""
    left, top = position
    group = ET.SubElement(parent, "g")
    title = ET.SubElement(group, "title")
    title.text = key
    ET.SubElement(group, "rect", {
        "x": str(left),
        "y": str(top),
        "width": str(NODE_WIDTH),
        "height": str(NODE_HEIGHT),
        "rx": "8",
        "ry": "8",
        "fill": ROOT_FILL if is_root else NODE_FILL,
        "stroke": NODE_STROKE,
        "stroke-width": "1.6" if is_root else "1",
    })
    text = ET.SubElement(group, "text", {
        "x": str(left + NODE_WIDTH // 2),
        "y": str(top + NODE_HEIGHT // 2),
        "text-anchor": "middle",
        "dominant-baseline": "central",
        "font-family": FONT_FAMILY,
        "font-size": str(FONT_SIZE),
        "fill": TEXT_COLOR,
    })
    text.text = short_label(key)

def ascii_tree(dependency_graph, root_key):
    """Return the dependency tree of the root package as text lines."""
    lines = [root_key]
    expanded = {root_key}
    stack = []
    _push_children(stack, dependency_graph, root_key, "")
    while stack:
        key, prefix, is_last = stack.pop()
        marker = REPEAT if key in expanded else ""
        branch = LAST_BRANCH if is_last else BRANCH
        lines.append(prefix + branch + key + marker)
        if marker:
            continue
        expanded.add(key)
        indent = prefix + (SPACE if is_last else VERTICAL)
        _push_children(stack, dependency_graph, key, indent)
    return lines

def _push_children(stack, dependency_graph, key, prefix):
    """Push the children of a package so that they pop in order."""
    children = dependency_graph.children(key)
    for index in range(len(children) - 1, -1, -1):
        last = index == len(children) - 1
        stack.append((children[index], prefix, last))

def write_file(path, text):
    """Write a text file in UTF-8."""
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


# ======================================================================
# main.py
# ======================================================================
# Entry point of the npm dependency graph visualizer.
#
# Stage 3 adds the graph itself: the dependencies are collected with a
# breadth first search without recursion, cyclic dependencies are kept in
# the graph and reported, and the test mode reads the graph from a local
# text file instead of the network.

PROGRAM_NAME = "depgraph"

DESCRIPTION = "Визуализатор графа зависимостей пакетов npm."

EXIT_OK = 0

EXIT_CONFIG = 2

EXIT_SOURCE = 3

EXIT_OUTPUT = 4

DOT_EXTENSION = ".dot"

DEFAULT_REPO = "https://registry.npmjs.org"

REVERSE_REQUIRES_TEST = (
    "Ошибка: обратные зависимости вычисляются только в тестовом режиме, "
    "где известен весь граф зависимостей.")

def parse_args(argv=None):
    """Parse the command line parameters of the visualizer."""
    return build_parser().parse_args(argv)

def build_parser():
    """Create the argument parser with every option of the tool."""
    parser = argparse.ArgumentParser(
        prog=PROGRAM_NAME,
        description=DESCRIPTION,
    )
    add_input_options(parser)
    add_output_options(parser)
    return parser

def add_input_options(parser):
    """Register the options that select the package and its source."""
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

def add_output_options(parser):
    """Register the options that control the report and the image."""
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
    parser.add_argument(
        "--reverse",
        default="false",
        metavar="true|false",
        help="вывод пакетов, которые зависят от заданного",
    )

def show_config(tool_config):
    """Print every parameter of the run as a key: value line."""
    for line in tool_config.describe():
        print(line)

def create_source(tool_config):
    """Create the data source for the selected mode."""
    if tool_config.test_mode:
        return TestRepository(tool_config.repo)
    return RegistryClient(tool_config.repo)

def show_summary(dependency_graph):
    """Print the size of the graph and its cycle information."""
    print(f"Граф зависимостей {dependency_graph.root()}:")
    print(f"  всего пакетов: {len(dependency_graph.order)}")
    print(f"  всего связей: {len(dependency_graph.edges)}")
    cycle = dependency_graph.cycle()
    if cycle:
        print("  цикл: " + " -> ".join(cycle))
    else:
        print("  циклов нет")

def show_forward(dependency_graph):
    """Print the packages in the order of the BFS traversal."""
    print("Пакеты в порядке обхода BFS:")
    for key in dependency_graph.order:
        count = len(dependency_graph.children(key))
        print(f"  {key} ({count})")

def show_reverse(dependency_graph, target_key):
    """Print the packages that depend on the requested package."""
    inverted = reverse_edges(dependency_graph)
    dependents = reachable(inverted, target_key)
    print(f"Обратные зависимости для {target_key}:")
    if not dependents:
        print("  (нет)")
        return
    print(f"  всего пакетов: {len(dependents)}")
    for key in dependents:
        print(f"  {key}")

def run_reverse(tool_config):
    """Show the packages that depend on the requested package."""
    if not tool_config.test_mode:
        print(REVERSE_REQUIRES_TEST, file=sys.stderr)
        return EXIT_SOURCE
    try:
        repository = TestRepository(tool_config.repo)
        full_graph = build_full_graph(repository)
    except SourceError as exc:
        print(f"Ошибка источника: {exc}", file=sys.stderr)
        return EXIT_SOURCE
    if tool_config.package not in full_graph.packages:
        print(f"Ошибка источника: пакет '{tool_config.package}' "
              "не найден в тестовом репозитории", file=sys.stderr)
        return EXIT_SOURCE
    print(f"Граф тестового репозитория: пакетов {len(full_graph.order)}, "
          f"связей {len(full_graph.edges)}")
    show_reverse(full_graph, tool_config.package)
    return EXIT_OK

def show_problems(dependency_graph):
    """Print dependencies that could not be resolved."""
    for source_key, name, message in dependency_graph.problems:
        print(f"  пропущено: {name} из {source_key}: {message}",
              file=sys.stderr)

def dot_path_for(output):
    """Return the DOT file name for the requested SVG file name."""
    base, _ = os.path.splitext(output)
    return base + DOT_EXTENSION

def show_dot(dependency_graph):
    """Print the Graphviz description of the graph."""
    print("Graphviz (DOT):")
    print(to_dot(dependency_graph,
                        dependency_graph.root()).rstrip())

def show_ascii_tree(dependency_graph):
    """Print the dependency tree as an ASCII picture."""
    print("ASCII-дерево:")
    for line in ascii_tree(dependency_graph,
                                  dependency_graph.root()):
        print(line)

def save_pictures(tool_config, dependency_graph):
    """Write the DOT description and the SVG image of the graph."""
    root_key = dependency_graph.root()
    dot_file = dot_path_for(tool_config.output)
    write_file(dot_file, to_dot(dependency_graph, root_key))
    write_file(tool_config.output,
                      to_svg(dependency_graph, root_key))
    print(f"Файл Graphviz сохранён: {dot_file}")
    print(f"Изображение SVG сохранено: {tool_config.output}")

def run(tool_config):
    """Build the dependency graph and print it."""
    if tool_config.reverse:
        return run_reverse(tool_config)
    try:
        source = create_source(tool_config)
        root_package = source.resolve(tool_config.package,
                                      tool_config.version)
        dependency_graph = build_graph(source, root_package)
    except SourceError as exc:
        print(f"Ошибка источника: {exc}", file=sys.stderr)
        return EXIT_SOURCE
    show_summary(dependency_graph)
    show_forward(dependency_graph)
    show_dot(dependency_graph)
    try:
        save_pictures(tool_config, dependency_graph)
    except OSError as exc:
        print(f"Ошибка записи файла: {exc}", file=sys.stderr)
        return EXIT_OUTPUT
    if tool_config.ascii_tree:
        show_ascii_tree(dependency_graph)
    show_problems(dependency_graph)
    return EXIT_OK

def main(argv=None):
    """Validate the configuration and build the dependency graph."""
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
