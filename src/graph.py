"""Breadth first traversal of the dependency graph.

The graph is built with an explicit queue, so no recursion is used and a
very deep dependency tree cannot hit the recursion limit.  A package is
expanded exactly once, which also stops the traversal on cyclic
dependencies: a back edge is stored in the graph, but the package is not
queued again."""

from collections import deque
from models import SourceError


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

def resolve_dependency(source, current, name, requirement,
                       dependency_graph):
    """Resolve one dependency and remember the problem if it fails."""
    try:
        return source.resolve(name, requirement)
    except SourceError as exc:
        dependency_graph.add_problem(current.key(), name, str(exc))
        return None
