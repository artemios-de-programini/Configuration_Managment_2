"""Визуализатор графа зависимостей пакетов npm (единый модуль).

Модуль собран из исходных файлов проекта: проверка параметров,
модель пакета, работа с реестром, семантические версии, граф
зависимостей, тестовый репозиторий, отрисовка и точка входа CLI.
"""

import argparse
import os
import re
import sys
from dataclasses import dataclass
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
# main.py
# ======================================================================
# Entry point of the npm dependency graph visualizer.
#
# Stage 1 implements the configuration part of the tool: the program reads
# all parameters from the command line, validates every value, prints the
# resulting configuration as ``key: value`` lines and stops.  The following
# stages add the data collection, the graph traversal and the rendering.

PROGRAM_NAME = "depgraph"

DESCRIPTION = "Визуализатор графа зависимостей пакетов npm."

EXIT_OK = 0

EXIT_CONFIG = 2

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

def main(argv=None):
    """Validate the configuration and print it."""
    args = parse_args(argv)
    try:
        tool_config = build_config(args)
    except ConfigError as exc:
        for message in exc.messages:
            print(message, file=sys.stderr)
        return EXIT_CONFIG
    show_config(tool_config)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
