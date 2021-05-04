import contextlib
import difflib
import io
import json
import logging
import os
import re
import shutil
import tempfile
import unittest
import uuid
from datetime import datetime
from distutils.dir_util import copy_tree

from git import Repo
from megalinter import Megalinter, config, utils

REPO_HOME = (
    utils.get_sources_folder()
    if os.path.isdir(utils.get_sources_folder())
    else os.path.dirname(os.path.abspath(__file__))
    + os.path.sep
    + ".."
    + os.path.sep
    + ".."
    + os.path.sep
    + ".."
    + os.path.sep
    + ".."
)


# Define env variables before any test case
def linter_test_setup(params=None):
    for key in [
        "MEGALINTER_CONFIG",
        "EXTENDS",
        "FILTER_REGEX_INCLUDE",
        "FILTER_REGEX_EXCLUDE",
        "SHOW_ELAPSED_TIME",
    ]:
        if key in os.environ:
            del os.environ[key]
    config.delete()
    if params is None:
        params = {}
    # Root to lint
    sub_lint_root = (
        params["sub_lint_root"]
        if "sub_lint_root" in params
        else f"{os.path.sep}.automation{os.path.sep}test"
    )
    # Root path of default rules
    root_dir = (
        utils.get_sources_folder()
        if os.path.isdir(utils.get_sources_folder())
        else os.path.relpath(
            os.path.relpath(os.path.dirname(os.path.abspath(__file__))) + "/../../../.."
        )
    )
    workspace = None
    config_file_path = root_dir + sub_lint_root + os.path.sep + ".mega-linter.yml"
    if os.path.isfile(config_file_path):
        workspace = root_dir + sub_lint_root
    elif params.get("required_config_file", False) is True:
        raise Exception(
            f"[test] There should be a .mega-linter.yml file in test folder {config_file_path}"
        )
    config.init_config(workspace)
    # Ignore report folder
    config.set_value("FILTER_REGEX_EXCLUDE", r"\/report\/")
    # TAP Output deactivated by default
    config.set_value("OUTPUT_FORMAT", "text")
    config.set_value("OUTPUT_DETAIL", "detailed")
    config.set_value("PLUGINS", "")
    config.set_value("VALIDATE_ALL_CODEBASE", "true")
    # Root path of files to lint
    config.set_value(
        "DEFAULT_WORKSPACE",
        (
            config.get("DEFAULT_WORKSPACE") + sub_lint_root
            if config.exists("DEFAULT_WORKSPACE")
            and os.path.isdir(config.get("DEFAULT_WORKSPACE") + sub_lint_root)
            else root_dir + sub_lint_root
        ),
    )
    assert os.path.isdir(config.get("DEFAULT_WORKSPACE")), (
        "DEFAULT_WORKSPACE "
        + config.get("DEFAULT_WORKSPACE")
        + " is not a valid folder"
    )


def print_output(output):
    if config.exists("OUTPUT_DETAILS") and config.get("OUTPUT_DETAILS") == "detailed":
        for line in output.splitlines():
            print(line)


def call_mega_linter(env_vars):
    prev_environ = config.copy()
    usage_stdout = io.StringIO()
    with contextlib.redirect_stdout(usage_stdout):
        # Set env variables
        for env_var_key, env_var_value in env_vars.items():
            config.set_value(env_var_key, env_var_value)
        # Call linter
        mega_linter = Megalinter()
        mega_linter.run()
        # Set back env variable previous values
        for env_var_key, env_var_value in env_vars.items():
            if env_var_key in prev_environ:
                config.set_value(env_var_key, prev_environ[env_var_key])
            else:
                config.delete(env_var_key)
    output = usage_stdout.getvalue().strip()
    print_output(output)
    return mega_linter, output


def test_linter_success(linter, test_self):
    test_folder = linter.test_folder
    workspace = config.get("DEFAULT_WORKSPACE") + os.path.sep + test_folder
    # Special cases when files must be copied in a temp directory before being linted
    if os.path.isdir(workspace + os.path.sep + "good"):
        workspace = workspace + os.path.sep + "good"
        workspace = manage_copy_sources(workspace)
    tmp_report_folder = tempfile.gettempdir() + os.path.sep + str(uuid.uuid4())
    assert os.path.isdir(workspace), f"Test folder {workspace} is not existing"
    linter_name = linter.linter_name
    env_vars = {
        "DEFAULT_WORKSPACE": workspace,
        "FILTER_REGEX_INCLUDE": r"(good)",
        "TEXT_REPORTER": "true",
        "REPORT_OUTPUT_FOLDER": tmp_report_folder,
        "LOG_LEVEL": "DEBUG",
        "ENABLE_LINTERS": linter.name,
    }
    if linter.lint_all_other_linters_files is not False:
        env_vars["ENABLE_LINTERS"] += ",JAVASCRIPT_ES"
    env_vars.update(linter.test_variables)
    mega_linter, output = call_mega_linter(env_vars)
    test_self.assertTrue(
        len(mega_linter.linters) > 0, "Linters have been created and run"
    )
    # Check console output
    if linter.cli_lint_mode == "file":
        if len(linter.file_names_regex) > 0 and len(linter.file_extensions) == 0:
            test_self.assertRegex(
                output, rf"\[{linter_name}\] .*{linter.file_names_regex[0]}.* - SUCCESS"
            )
        else:
            test_self.assertRegex(output, rf"\[{linter_name}\] .*good.* - SUCCESS")
    else:
        test_self.assertRegex(
            output,
            rf"Linted \[{linter.descriptor_id}\] files with \[{linter_name}\] successfully",
        )
    # Check text reporter output log
    report_file_name = f"SUCCESS-{linter.name}.log"
    text_report_file = (
        f"{tmp_report_folder}{os.path.sep}linters_logs"
        f"{os.path.sep}{report_file_name}"
    )
    test_self.assertTrue(
        os.path.isfile(text_report_file),
        f"Unable to find text report {text_report_file}",
    )
    copy_logs_for_doc(text_report_file, test_folder, report_file_name)


def test_linter_failure(linter, test_self):
    test_folder = linter.test_folder
    workspace = config.get("DEFAULT_WORKSPACE") + os.path.sep + test_folder
    if os.path.isdir(workspace + os.path.sep + "bad"):
        workspace = workspace + os.path.sep + "bad"
        workspace = manage_copy_sources(workspace)
    tmp_report_folder = tempfile.gettempdir() + os.path.sep + str(uuid.uuid4())
    assert os.path.isdir(workspace), f"Test folder {workspace} is not existing"
    if os.path.isfile(workspace + os.path.sep + "no_test_failure"):
        raise unittest.SkipTest(
            f"Skip failure test for {linter}: no_test_failure found in test folder"
        )
    linter_name = linter.linter_name
    env_vars_failure = {
        "DEFAULT_WORKSPACE": workspace,
        "FILTER_REGEX_INCLUDE": r"(bad)",
        "OUTPUT_FORMAT": "text",
        "OUTPUT_DETAIL": "detailed",
        "REPORT_OUTPUT_FOLDER": tmp_report_folder,
        "LOG_LEVEL": "DEBUG",
        "ENABLE_LINTERS": linter.name,
    }
    if linter.lint_all_other_linters_files is not False:
        env_vars_failure["ENABLE_LINTERS"] += ",JAVASCRIPT_ES"
    env_vars_failure.update(linter.test_variables)
    mega_linter, output = call_mega_linter(env_vars_failure)
    # Check linter run
    test_self.assertTrue(
        len(mega_linter.linters) > 0, "Linters have been created and run"
    )
    # Check console output
    if linter.cli_lint_mode == "file":
        if len(linter.file_names_regex) > 0 and len(linter.file_extensions) == 0:
            test_self.assertRegex(
                output, rf"\[{linter_name}\] .*{linter.file_names_regex[0]}.* - ERROR"
            )
            test_self.assertNotRegex(
                output, rf"\[{linter_name}\] .*{linter.file_names_regex[0]}.* - SUCCESS"
            )
        else:
            test_self.assertRegex(output, rf"\[{linter_name}\] .*bad.* - ERROR")
            test_self.assertNotRegex(output, rf"\[{linter_name}\] .*bad.* - SUCCESS")
    else:
        test_self.assertRegex(
            output,
            rf"Linted \[{linter.descriptor_id}\] files with \[{linter_name}\]: Found",
        )
    # Check text reporter output log
    report_file_name = f"ERROR-{linter.name}.log"
    text_report_file = (
        f"{tmp_report_folder}{os.path.sep}linters_logs"
        f"{os.path.sep}{report_file_name}"
    )
    test_self.assertTrue(
        os.path.isfile(text_report_file),
        f"Unable to find text report {text_report_file}",
    )
    copy_logs_for_doc(text_report_file, test_folder, report_file_name)


def manage_copy_sources(workspace):
    if os.path.isfile(workspace + os.path.sep + "test_copy_in_tmp_folder"):
        tmp_sources_folder = tempfile.gettempdir() + os.path.sep + str(uuid.uuid4())
        copy_tree(workspace, tmp_sources_folder)
        workspace = tmp_sources_folder
    return workspace


# Copy logs for documentation
def copy_logs_for_doc(text_report_file, test_folder, report_file_name):
    updated_sources_dir = (
        f"{REPO_HOME}{os.path.sep}report{os.path.sep}updated_dev_sources{os.path.sep}"
        f".automation{os.path.sep}test{os.path.sep}{test_folder}{os.path.sep}reports"
    )
    target_file = f"{updated_sources_dir}{os.path.sep}{report_file_name}".replace(
        ".log", ".txt"
    )
    os.makedirs(os.path.dirname(target_file), exist_ok=True)
    shutil.copy(text_report_file, target_file)


def test_get_linter_version(linter, test_self):
    # Check linter version
    version = linter.get_linter_version()
    print("[" + linter.linter_name + "] version: " + version)
    test_self.assertFalse(
        version == "ERROR", "Returned version invalid: [" + version + "]"
    )
    # Check linter version cache
    version_cache = linter.get_linter_version()
    test_self.assertTrue(
        version == version_cache, "Version not found in linter instance cache"
    )
    # Write in linter-versions.json
    root_dir = (
        utils.get_sources_folder()
        if os.path.isdir(utils.get_sources_folder())
        else os.path.relpath(
            os.path.relpath(os.path.dirname(os.path.abspath(__file__))) + "/../../../.."
        )
    )
    versions_file = (
        root_dir + os.path.sep + "/.automation/generated/linter-versions.json"
    )
    data = {}
    if os.path.isfile(versions_file):
        with open(versions_file, "r", encoding="utf-8") as json_file:
            data = json.load(json_file)
    if (
        linter.linter_name in data and data[linter.linter_name] != version
    ) or linter.linter_name not in data:
        prev_version = None
        if linter.linter_name in data and data[linter.linter_name] != version:
            prev_version = data[linter.linter_name]
        data[linter.linter_name] = version
        with open(versions_file, "w", encoding="utf-8") as outfile:
            json.dump(data, outfile, indent=4, sort_keys=True)
        # Upgrade version in changelog
        if prev_version is not None:
            changelog_file = root_dir + os.path.sep + "/CHANGELOG.md"
            with open(changelog_file, "r", encoding="utf-8") as md_file:
                changelog_content = md_file.read()
            start = "- Linter versions upgrades"
            end = "<!-- linter-versions-end -->"
            regex = rf"{start}([\s\S]*?){end}"
            existing_text_find = re.findall(regex, changelog_content, re.DOTALL)
            if existing_text_find is None:
                raise Exception(
                    f"CHANGELOG.md must contain a single block scoped by '{start}' and '{end}'"
                )
            versions_text = existing_text_find[0]
            versions_text += (
                f"  - [{linter.linter_name}]({linter.linter_url}) from {prev_version} to **{version}**"
                f" on {datetime.today().strftime('%Y-%m-%d')}\n"
            )
            versions_block = f"{start}{versions_text}{end}"
            changelog_content = re.sub(
                regex, versions_block, changelog_content, re.DOTALL
            )
            with open(changelog_file, "w", encoding="utf-8") as md_file:
                md_file.write(changelog_content)
            logging.info(f"Updated {linter.linter_name} in CHANGELOG.md")


def test_get_linter_help(linter, test_self):
    # Check linter help
    help_txt = linter.get_linter_help()
    print("[" + linter.linter_name + "] help: " + help_txt)
    test_self.assertFalse(
        help_txt == "ERROR", "Returned help invalid: [" + help_txt + "]"
    )
    # Write in linter-helps.json
    root_dir = (
        utils.get_sources_folder()
        if os.path.isdir(utils.get_sources_folder())
        else os.path.relpath(
            os.path.relpath(os.path.dirname(os.path.abspath(__file__))) + "/../../../.."
        )
    )
    helps_file = root_dir + os.path.sep + "/.automation/generated/linter-helps.json"
    data = {}
    help_lines = help_txt.splitlines()
    help_lines_clean = []
    for help_line in help_lines:
        line_clean = (
            help_line.replace("\\t", "  ")
            .replace("\t", "  ")
            .replace("\\r", "")
            .replace("\r", "")
            .replace(r"(\[..m)", "")
            .replace(r"(\[.m)", "")
            .rstrip()
        )
        help_lines_clean += [line_clean]
    if os.path.isfile(helps_file):
        with open(helps_file, "r", encoding="utf-8") as json_file:
            data = json.load(json_file)
    if (
        linter.linter_name in data and data[linter.linter_name] != help_lines_clean
    ) or linter.linter_name not in data:
        data[linter.linter_name] = help_lines_clean
        with open(helps_file, "w", encoding="utf-8") as outfile:
            json.dump(data, outfile, indent=4, sort_keys=True)


def test_linter_report_tap(linter, test_self):
    test_folder = linter.test_folder
    workspace = config.get("DEFAULT_WORKSPACE") + os.path.sep + test_folder
    assert os.path.isdir(workspace), f"Test folder {workspace} is not existing"
    expected_file_name = ""
    # Identify expected report if defined
    reports_with_extension = []
    for ext in linter.file_extensions:
        reports_with_extension += [f"expected-{ext.upper()[1:]}.tap"]
    possible_reports = [
        f"expected-{linter.name}.tap",
        f"expected-{linter.descriptor_id}.tap",
    ] + reports_with_extension
    for file_nm in list(dict.fromkeys(possible_reports)):
        if os.path.isfile(f"{workspace}{os.path.sep}reports{os.path.sep}{file_nm}"):
            expected_file_name = (
                f"{workspace}{os.path.sep}reports{os.path.sep}{file_nm}"
            )
    if expected_file_name == "":
        raise unittest.SkipTest(
            f"Expected report not defined in {workspace}{os.path.sep}reports"
        )
    # Call linter
    tmp_report_folder = tempfile.gettempdir()
    env_vars = {
        "DEFAULT_WORKSPACE": workspace,
        "OUTPUT_FORMAT": "tap",
        "OUTPUT_DETAIL": "detailed",
        "REPORT_OUTPUT_FOLDER": tmp_report_folder,
        "ENABLE_LINTERS": linter.name,
    }
    env_vars.update(linter.test_variables)
    mega_linter, _output = call_mega_linter(env_vars)
    test_self.assertTrue(
        len(mega_linter.linters) > 0, "Linters have been created and run"
    )
    # Check TAP file has been produced
    tmp_tap_file_name = (
        f"{tmp_report_folder}{os.path.sep}tap{os.path.sep}mega-linter-{linter.name}.tap"
    )
    test_self.assertTrue(
        os.path.isfile(tmp_tap_file_name), f"TAP report not found {tmp_tap_file_name}"
    )
    # Compare file content
    with open(tmp_tap_file_name, "r", encoding="utf-8") as f_produced:
        content_produced = f_produced.read()
        with open(expected_file_name, "r", encoding="utf-8") as f_expected:
            content_expected = f_expected.read()
            diffs = [
                li
                for li in difflib.ndiff(content_expected, content_produced)
                if li[0] != " " and li not in ["- \\n", "-  ", "+ \\n", "+  "]
            ]
            if len(diffs) > 0:
                # Compare just the lines not containing 'message'
                expected_lines = content_expected.splitlines()
                produced_lines = content_produced.splitlines()
                identical_nb = 0
                for expected_idx, expected_line in enumerate(expected_lines):
                    produced_line = (
                        produced_lines[expected_idx]
                        if expected_idx < len(produced_lines)
                        else ""
                    )
                    if produced_line.strip().startswith("message:"):
                        continue
                    if "ok " in produced_line:
                        test_self.assertEqual(
                            produced_line.split("-")[0],
                            utils.normalize_log_string(expected_line).split("-")[0],
                        )
                    else:
                        test_self.assertEqual(
                            produced_line, utils.normalize_log_string(expected_line)
                        )
                    identical_nb = identical_nb + 1
                logging.warning(
                    "Produced and expected TAP files are different "
                    "only inside the content of [message:] YAML lines."
                    f"{str(identical_nb)} TAP lines on the total {str(len(expected_lines))} "
                    f"remain perfectly identical :)"
                )


def assert_is_skipped(skipped_item, output, test_self):
    test_self.assertRegex(
        output,
        rf"(?<=Skipped linters:)*({skipped_item})(?=.*[\n])",
        "No trace of skipped item " + skipped_item + " in log",
    )


def assert_file_has_been_updated(file_name, bool_val, test_self):
    repo = Repo(REPO_HOME)
    changed_files = [item.a_path for item in repo.index.diff(None)]
    logging.info("Updated files (git):\n" + "\n".join(changed_files))
    updated = False
    for changed_file in changed_files:
        if file_name in changed_file:
            updated = True
    if bool_val is True:
        test_self.assertTrue(updated, f"{file_name} has been updated")
    else:
        test_self.assertFalse(updated, f"{file_name} has not been updated")
