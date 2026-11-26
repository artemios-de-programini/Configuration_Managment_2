"""Reader of the test repository file.

The test mode replaces the network registry with a small text file that
describes the dependency graph directly:

```text
# имя пакета : список прямых зависимостей
A: B C
B: C
C:
```

Package names consist of capital Latin letters only.  Every dependency
must be declared somewhere in the file, which makes the graph complete
and catches typos."""

import re
from models import Package, SourceError


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
