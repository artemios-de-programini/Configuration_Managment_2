"""Data model of a package and its dependencies.

The same structure describes packages of the real npm registry and nodes
of the test repository: a name, a concrete version and the list of direct
dependencies together with the version requirements."""

from dataclasses import dataclass


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
