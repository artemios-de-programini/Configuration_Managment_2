"""Entry point of the npm dependency graph visualizer.

Stage 3 adds the graph itself: the dependencies are collected with a
breadth first search without recursion, cyclic dependencies are kept in
the graph and reported, and the test mode reads the graph from a local
text file instead of the network."""

import argparse
import sys
from config import ConfigError, build_config
from models import SourceError
from registry import RegistryClient
from testrep import TestRepository
from graph import build_graph


PROGRAM_NAME = "depgraph"

DESCRIPTION = "Визуализатор графа зависимостей пакетов npm."

EXIT_OK = 0

EXIT_CONFIG = 2

EXIT_SOURCE = 3

DEFAULT_REPO = "https://registry.npmjs.org"

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

def create_source(tool_config):
    """Create the data source for the selected mode."""
    if tool_config.test_mode:
        return TestRepository(tool_config.repo)
    return RegistryClient(tool_config.repo)

def show_graph(dependency_graph):
    """Print the graph summary and the packages in BFS order."""
    print(f"Граф зависимостей {dependency_graph.root()}:")
    print(f"  всего пакетов: {len(dependency_graph.order)}")
    print(f"  всего связей: {len(dependency_graph.edges)}")
    cycle = dependency_graph.cycle()
    if cycle:
        print("  цикл: " + " -> ".join(cycle))
    else:
        print("  циклов нет")
    print("Пакеты в порядке обхода BFS:")
    for key in dependency_graph.order:
        count = len(dependency_graph.children(key))
        print(f"  {key} ({count})")

def show_problems(dependency_graph):
    """Print dependencies that could not be resolved."""
    for source_key, name, message in dependency_graph.problems:
        print(f"  пропущено: {name} из {source_key}: {message}",
              file=sys.stderr)

def run(tool_config):
    """Build the dependency graph and print it."""
    try:
        source = create_source(tool_config)
        root_package = source.resolve(tool_config.package,
                                      tool_config.version)
        dependency_graph = build_graph(source, root_package)
    except SourceError as exc:
        print(f"Ошибка источника: {exc}", file=sys.stderr)
        return EXIT_SOURCE
    show_graph(dependency_graph)
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
