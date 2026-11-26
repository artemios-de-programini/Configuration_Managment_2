"""Entry point of the npm dependency graph visualizer.

Stage 2 adds the data collection: the program reads the manifest of the
requested package version from the registry and prints every direct
dependency.  Test repositories are supported starting with stage 3."""

import argparse
import sys
from config import ConfigError, build_config
from registry import RegistryClient, RegistryError


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
