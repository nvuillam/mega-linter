#!/usr/bin/env python3

import importlib
import logging
import os
import re
from typing import Optional, Pattern, Sequence

import git
from megalinter import config

REPO_HOME_DEFAULT = (
    get_sources_folder()
    if os.path.isdir(get_sources_folder())
    else os.environ.get("DEFAULT_WORKSPACE")
    if os.path.isdir(os.environ.get("DEFAULT_WORKSPACE", "null"))
    else os.path.dirname(os.path.abspath(__file__)) + os.path.sep + ".."
)

ANSI_ESCAPE_REGEX = re.compile(r"(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]")
LIST_OF_REPLACEMENTS = [
    # Mega-Linter image
    [get_sources_folder(), ""],
    [get_sources_folder()[1:], ""],
    # GitHub Actions
    ["/github/workspace/", ""],
    ["github/workspace/", ""],
]
# GitLab CI
CI_PROJECT_DIR = os.environ.get("CI_PROJECT_DIR", "")
if CI_PROJECT_DIR != "":
    LIST_OF_REPLACEMENTS += [[f"/{CI_PROJECT_DIR}/", ""], [f"{CI_PROJECT_DIR}/", ""]]
# Other
DEFAULT_WORKSPACE = os.environ.get("DEFAULT_WORKSPACE", "")
if DEFAULT_WORKSPACE != "":
    LIST_OF_REPLACEMENTS += [
        [f"/{DEFAULT_WORKSPACE}/", ""],
        [f"{DEFAULT_WORKSPACE}/", ""],
    ]


def get_excluded_directories():
    default_excluded_dirs = [
        "__pycache__",
        ".git",
        ".jekyll-cache",
        ".pytest_cache",
        ".rbenv",
        ".venv",
        ".terragrunt-cache",
        "node_modules",
        "report",
    ]
    excluded_dirs = config.get_list("EXCLUDED_DIRECTORIES", default_excluded_dirs)
    excluded_dirs += config.get_list("ADDITIONAL_EXCLUDED_DIRECTORIES", [])
    return set(excluded_dirs)


def filter_files(
    all_files: Sequence[str],
    filter_regex_include: Optional[str],
    filter_regex_exclude: Optional[str],
    file_names_regex: Sequence[str],
    file_extensions: Sequence[str],
    file_names_not_ends_with: Optional[Sequence[str]] = None,
    file_contains_regex: Optional[Sequence[str]] = None,
    files_sub_directory: Optional[str] = None,
    lint_all_other_linters_files: bool = False,
) -> Sequence[str]:
    file_extensions = set(file_extensions)
    filter_regex_include_object = (
        re.compile(filter_regex_include) if filter_regex_include else None
    )
    filter_regex_exclude_object = (
        re.compile(filter_regex_exclude) if filter_regex_exclude else None
    )
    file_names_regex_object = re.compile("|".join(file_names_regex))
    filtered_files = []
    file_contains_regex_object = (
        re.compile("|".join(file_contains_regex), flags=re.MULTILINE)
        if file_contains_regex
        else None
    )

    # Filter all files to keep only the ones matching with the current linter

    for file in all_files:
        base_file_name = os.path.basename(file)
        filename, file_extension = os.path.splitext(base_file_name)

        if filter_regex_include_object and not filter_regex_include_object.search(file):
            continue

        if filter_regex_exclude_object and filter_regex_exclude_object.search(file):
            continue

        if files_sub_directory and files_sub_directory not in file:
            continue

        if not lint_all_other_linters_files:
            if file_extension in file_extensions:
                pass
            elif "*" in file_extensions:
                pass
            elif file_names_regex_object.fullmatch(filename):
                pass
            else:
                continue

        if file_names_not_ends_with and file.endswith(tuple(file_names_not_ends_with)):
            continue

        if file_contains_regex and not file_contains(file, file_contains_regex_object):
            continue

        filtered_files.append(file)

    return filtered_files


# Center the string and complete blanks with hyphens (-)
def format_hyphens(str_in):
    if str_in != "":
        str_in = " " + str_in + " "
    return "{s:{c}^{n}}".format(s=str_in, n=100, c="-")


def list_active_reporters_for_scope(scope, reporter_init_params):
    reporters = []
    # List associated reporters
    reporters_dir = os.path.realpath(
        os.path.dirname(os.path.abspath(__file__)) + "/reporters"
    )
    scope_reporters = []
    for reporter_class_file in os.listdir(reporters_dir):
        if not reporter_class_file.endswith("Reporter.py"):
            continue
        reporter_class_nm = os.path.splitext(reporter_class_file)[0]
        reporter_module = importlib.import_module(
            ".reporters." + reporter_class_nm, package=__package__
        )
        reporter_class = getattr(reporter_module, reporter_class_nm)
        if reporter_class.scope == scope:
            reporter = reporter_class(reporter_init_params)
            scope_reporters += [reporter]
    # Keep only active reporters
    for reporter in scope_reporters:
        if reporter.is_active is False:
            continue
        reporters += [reporter]
    # Sort reporters by name
    reporters = sorted(reporters, key=lambda r: (r.processing_order, r.name))
    return reporters


def check_activation_rules(activation_rules, _linter):
    active = False
    for rule in activation_rules:
        if rule["type"] == "variable":
            value = config.get(rule["variable"], rule["default_value"])
            if value == rule["expected_value"]:
                active = True
            else:
                active = False
                break
    return active


def file_contains(file_name: str, regex_object: Optional[Pattern[str]]) -> bool:
    if not regex_object:
        return True

    with open(file_name, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    found_pattern = regex_object.search(content) is not None
    return found_pattern


def decode_utf8(stdout):
    # noinspection PyBroadException
    try:
        res = stdout.decode("utf-8")
    except Exception:
        res = str(stdout)
    return res


def list_updated_files(repo_home):
    try:
        repo = git.Repo(repo_home)
    except git.InvalidGitRepositoryError:
        try:
            repo = git.Repo(REPO_HOME_DEFAULT)
        except git.InvalidGitRepositoryError:
            logging.warning("Unable to find git repository to list updated files")
            return []
    changed_files = [item.a_path for item in repo.index.diff(None)]
    return changed_files


def check_updated_file(file, repo_home, changed_files=None):
    if changed_files is None:
        changed_files = list_updated_files(repo_home)
    file_absolute = os.path.abspath(file)
    for changed_file in changed_files:
        if changed_file in file_absolute:
            return True
    return False


def normalize_log_string(str_in):
    str_in = ANSI_ESCAPE_REGEX.sub("", str_in)
    for replacement in LIST_OF_REPLACEMENTS:
        str_in = str_in.replace(replacement[0], replacement[1])
    return str_in


def get_sources_folder():
    return "/srv/megalinter-workspace"
