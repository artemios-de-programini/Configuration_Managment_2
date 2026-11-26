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
from graph import build_full_graph, build_graph, reachable, reverse_edges


PROGRAM_NAME = "depgraph"

DESCRIPTION = "Визуализатор графа зависимостей пакетов npm."

EXIT_OK = 0

EXIT_CONFIG = 2

EXIT_SOURCE = 3

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
