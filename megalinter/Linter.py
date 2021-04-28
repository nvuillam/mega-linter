#!/usr/bin/env python3
"""
Template class for custom linters: any linter class in /linters folder must inherit from this class
The following list of items can/must be overridden on custom linter local class:
- field descriptor_id (required) ex: "JAVASCRIPT"
- field name (optional) ex: "JAVASCRIPT_ES". If not set, language value is used
- field linter_name (required) ex: "eslint"
- field linter_url (required) ex: "https://eslint.org/"
- field test_folder (optional) ex: "docker". If not set, language.lowercase() value is used
- field config_file_name (optional) ex: ".eslintrc.yml". If not set, no default config file will be searched
- field file_extensions (optional) ex: [".js"]. At least file_extension or file_names_regex must be set
- field file_names_regex (optional) ex: ["Dockerfile(-.+)?"]. At least file_extension or file_names_regex must be set
- method build_lint_command (optional) : Return CLI command to lint a file with the related linter
                                         Default: linter_name + (if config_file(-c + config_file)) + config_file
- method build_version_command (optional): Returns CLI command to get the related linter version.
                                           Default: linter_name --version
- method build_extract_version_regex (optional): Returns RegEx to extract version from version command output
                                                 Default: "\\d+(\\.\\d+)+"

"""
import errno
import logging
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from time import perf_counter

from megalinter import config, utils


class Linter:
    # Constructor: Initialize Linter instance with name and config variables
    def __init__(self, params=None, linter_config=None):
        self.linter_version_cache = None
        self.linter_help_cache = None
        self.processing_order = 0
        # Definition fields & default values: can be overridden at custom linter class level or in YML descriptors
        # Ex: JAVASCRIPT
        self.descriptor_id = (
            "Field 'descriptor_id' must be overridden at custom linter class level"
        )
        # If you have several linters for the same language,override with a different name.Ex: JAVASCRIPT_ES
        self.name = None
        self.is_formatter = False
        self.linter_name = "Field 'linter_name' must be overridden at custom linter class level"  # Ex: eslint
        # ex: https://eslint.org/
        self.linter_url = (
            "Field 'linter_url' must be overridden at custom linter class level"
        )
        self.test_folder = None  # Override only if different from language.lowercase()
        self.activation_rules = []
        self.test_variables = {}
        # Array of strings defining file extensions. Ex: ['.js','.cjs', '']
        self.file_extensions = []
        # Array of file name regular expressions. Ex: [Dockerfile(-.+)?]
        self.file_names_regex = []
        # Default name of the configuration file to use with the linter. Ex: '.eslintrc.js'
        self.config_file_name = None
        self.files_sub_directory = None
        self.file_contains_regex = []
        self.file_names_not_ends_with = []
        self.active_only_if_file_found = []
        self.lint_all_files = False
        self.lint_all_other_linters_files = False

        self.cli_lint_mode = "file"
        self.cli_docker_image = None
        self.cli_docker_image_version = "latest"
        self.cli_docker_args = []
        self.cli_executable = None
        self.cli_executable_fix = None
        self.cli_executable_version = None
        self.cli_executable_help = None
        # Default arg name for configurations to use in linter CLI call
        self.cli_config_arg_name = "-c"
        self.cli_config_extra_args = (
            []
        )  # Extra arguments to send to cli when a config file is used
        self.no_config_if_fix = False
        self.cli_lint_extra_args = []  # Extra arguments to send to cli everytime
        self.cli_lint_fix_arg_name = None  # Name of the cli argument to send in case of APPLY_FIXES required by user
        self.cli_lint_fix_remove_args = (
            []
        )  # Arguments to remove in case fix argument is sent
        self.cli_lint_user_args = (
            []
        )  # Arguments from config, defined in <LINTER_KEY>_ARGUMENTS variable
        # Extra arguments to send to cli everytime, just before file argument
        self.cli_lint_extra_args_after = []
        self.cli_lint_errors_count = None
        self.cli_lint_errors_regex = None
        # Default arg name for configurations to use in linter version call
        self.cli_version_arg_name = "--version"
        self.cli_version_extra_args = []  # Extra arguments to send to cli everytime
        self.cli_help_arg_name = "-h"
        self.cli_help_extra_args = []  # Extra arguments to send to cli everytime
        self.cli_help_extra_commands = []
        # If linter --help does not return 0 when it is in success, override. ex: 1
        self.help_command_return_code = 0
        self.version_extract_regex = r"\d+(\.\d+)+"
        # If linter --version does not return 0 when it is in success, override. ex: 1
        self.version_command_return_code = 0

        self.report_folder = ""
        self.reporters = []

        # Initialize with configuration data
        for key, value in linter_config.items():
            self.__setattr__(key, value)

        # Initialize parameters
        if params is None:
            params = {
                "default_linter_activation": False,
                "enable_descriptors": [],
                "enable_linters": [],
                "disable_descriptors": [],
                "disable_linters": [],
                "post_linter_status": True,
            }

        self.is_active = params["default_linter_activation"]
        self.disable_errors_if_less_than = None
        self.disable_errors = (
            True
            if self.is_formatter is True
            and not config.get("FORMATTERS_DISABLE_ERRORS", "true") == "false"
            else False
        )
        if self.name is None:
            self.name = (
                self.descriptor_id + "_" + self.linter_name.upper().replace("-", "_")
            )
        if self.cli_executable is None:
            self.cli_executable = self.linter_name
        if self.cli_executable_fix is None:
            self.cli_executable_fix = self.cli_executable
        if self.cli_executable_version is None:
            self.cli_executable_version = self.cli_executable
        if self.cli_executable_help is None:
            self.cli_executable_help = self.cli_executable
        if self.test_folder is None:
            self.test_folder = self.descriptor_id.lower()

        # Apply linter customization via config settings:
        self.file_extensions = config.get_list(
            self.name + "_FILE_EXTENSIONS", self.file_extensions
        )
        self.file_names_regex = config.get_list(
            self.name + "_FILE_NAMES_REGEX", self.file_names_regex
        )

        self.manage_activation(params)

        if self.is_active is True:
            self.show_elapsed_time = params.get("show_elapsed_time", False)
            # Manage apply fixes flag on linter
            param_apply_fixes = params.get("apply_fixes", "none")
            if self.cli_lint_fix_arg_name is None:
                self.apply_fixes = False
            elif param_apply_fixes == "all" or (
                isinstance(param_apply_fixes, bool) and param_apply_fixes is True
            ):
                self.apply_fixes = True
            elif (
                param_apply_fixes != "none"
                and isinstance(param_apply_fixes, str)
                and self.name in param_apply_fixes.split(",")
            ):
                self.apply_fixes = True
            elif (
                param_apply_fixes != "none"
                and isinstance(param_apply_fixes, list)
                and (self.name in param_apply_fixes or param_apply_fixes[0] == "all")
            ):
                self.apply_fixes = True
            else:
                self.apply_fixes = False

            # Config items
            self.linter_rules_path = (
                params["linter_rules_path"] if "linter_rules_path" in params else "."
            )
            self.default_rules_location = (
                params["default_rules_location"]
                if "default_rules_location" in params
                else "."
            )
            self.workspace = params["workspace"] if "workspace" in params else "."
            self.github_workspace = (
                params["github_workspace"] if "github_workspace" in params else "."
            )
            self.config_file = None
            self.config_file_label = None
            self.config_file_error = None
            self.filter_regex_include = None
            self.filter_regex_exclude = None
            self.post_linter_status = (
                params["post_linter_status"]
                if "post_linter_status" in params
                else False
            )
            self.github_api_url = (
                params["github_api_url"] if "github_api_url" in params else None
            )

            self.report_types = (
                params["report_types"] if "report_types" in params else []
            )
            self.report_folder = (
                params["report_folder"] if "report_folder" in params else ""
            )

            self.load_config_vars()

            # Manage sub-directory filter if defined
            if self.files_sub_directory is not None:
                self.files_sub_directory = config.get(
                    f"{self.descriptor_id}_DIRECTORY", self.files_sub_directory
                )
                if not os.path.isdir(
                    self.workspace + os.path.sep + self.files_sub_directory
                ):
                    self.is_active = False
                    logging.debug(
                        f"[Activation] {self.name} has been set inactive, as subdirectory has not been found:"
                        f" {self.files_sub_directory}"
                    )

            # Some linters require a file to be existing, else they are deactivated ( ex: .editorconfig )
            if len(self.active_only_if_file_found) > 0:
                is_found = False
                for file_to_check in self.active_only_if_file_found:
                    if os.path.isfile(f"{self.workspace}{os.path.sep}{file_to_check}"):
                        is_found = True
                        break
                    if os.path.isfile(f"{self.workspace}{os.path.sep}{self.linter_rules_path}{os.path.sep}{file_to_check}"):
                        is_found = True
                        break
                if is_found is False:
                    self.is_active = False
                    logging.info(
                        f"[Activation] {self.name} has been set inactive, as none of these files has been found:"
                        f" {str(self.active_only_if_file_found)}"
                    )

            # Load Mega-Linter reporters
            self.load_reporters()

            # Runtime items
            self.files = []
            self.try_fix = False
            self.status = "success"
            self.stdout = None
            self.return_code = 0
            self.number_errors = 0
            self.total_number_errors = 0
            self.number_fixed = 0
            self.files_lint_results = []
            self.start_perf = None
            self.elapsed_time_s = 0
            self.remote_config_file_to_delete = None

    # Enable or disable linter
    def manage_activation(self, params):
        # Default value is false in case ENABLE variables are used
        if len(params["enable_descriptors"]) > 0 or len(params["enable_linters"]) > 0:
            self.is_active = False
        # Activate or not the linter
        if self.name in params["enable_linters"]:
            self.is_active = True
        elif self.name in params["disable_linters"]:
            self.is_active = False
        elif (
            self.descriptor_id in params["disable_descriptors"]
            or self.name in params["disable_linters"]
        ):
            self.is_active = False
        elif self.descriptor_id in params["enable_descriptors"]:
            self.is_active = True
        elif (
            config.exists("VALIDATE_" + self.name)
            and config.get("VALIDATE_" + self.name) == "false"
        ):
            self.is_active = False
        elif (
            config.exists("VALIDATE_" + self.descriptor_id)
            and config.get("VALIDATE_" + self.descriptor_id) == "false"
        ):
            self.is_active = False
        elif (
            config.exists("VALIDATE_" + self.name)
            and config.get("VALIDATE_" + self.name) == "true"
        ):
            self.is_active = True
        elif (
            config.exists("VALIDATE_" + self.descriptor_id)
            and config.get("VALIDATE_" + self.descriptor_id) == "true"
        ):
            self.is_active = True
        # check activation rules
        if self.is_active is True and len(self.activation_rules) > 0:
            self.is_active = utils.check_activation_rules(self.activation_rules, self)

    # Manage configuration variables
    def load_config_vars(self):
        # Configuration file name: try first NAME + _FILE_NAME, then LANGUAGE + _FILE_NAME
        # _CONFIG_FILE = _FILE_NAME (config renaming but keeping config ascending compatibility)
        if config.exists(self.name + "_CONFIG_FILE"):
            self.config_file_name = config.get(self.name + "_CONFIG_FILE")
        elif config.exists(self.descriptor_id + "_CONFIG_FILE"):
            self.config_file_name = config.get(self.descriptor_id + "_CONFIG_FILE")
        elif config.exists(self.name + "_FILE_NAME"):
            self.config_file_name = config.get(self.name + "_FILE_NAME")
        elif config.exists(self.descriptor_id + "_FILE_NAME"):
            self.config_file_name = config.get(self.descriptor_id + "_FILE_NAME")
        # Linter rules path: try first NAME + _RULE_PATH, then LANGUAGE + _RULE_PATH
        if config.exists(self.name + "_RULES_PATH"):
            self.linter_rules_path = config.get(self.name + "_RULES_PATH")
        elif config.exists(self.descriptor_id + "_RULES_PATH"):
            self.linter_rules_path = config.get(self.descriptor_id + "_RULES_PATH")
        # Linter config file:
        # 0: LINTER_DEFAULT set in user config: let the linter find it, do not reference it in cli arguments
        # 1: http rules path: fetch remove file and copy it locally (then delete it after linting)
        # 2: repo + config_file_name
        # 3: linter_rules_path + config_file_name
        # 4: mega-linter default rules path + config_file_name
        if (
            self.config_file_name is not None
            and self.config_file_name != "LINTER_DEFAULT"
        ):
            if self.linter_rules_path.startswith("http"):
                if not self.linter_rules_path.endswith("/"):
                    self.linter_rules_path += "/"
                remote_config_file = self.linter_rules_path + self.config_file_name
                local_config_file = self.workspace + os.path.sep + self.config_file_name
                existing_before = os.path.isfile(local_config_file)
                try:
                    with urllib.request.urlopen(remote_config_file) as response, open(
                        local_config_file, "wb"
                    ) as out_file:
                        shutil.copyfileobj(response, out_file)
                        self.config_file_label = remote_config_file
                        if existing_before is False:
                            self.remote_config_file_to_delete = local_config_file
                except urllib.error.HTTPError as e:
                    self.config_file_error = (
                        f"Unable to fetch {remote_config_file}\n{str(e)}\n"
                        f" fallback to repository config or Mega-Linter default config"
                    )
                except Exception as e:
                    self.config_file_error = (
                        f"Unable to fetch {remote_config_file}\n{str(e)}\n"
                        f" fallback to repository config or Mega-Linter default config"
                    )
            # in repo root (already here or fetched by code above)
            if os.path.isfile(self.workspace + os.path.sep + self.config_file_name):
                self.config_file = self.workspace + os.path.sep + self.config_file_name
            # in user repo ./github/linters folder
            elif os.path.isfile(
                self.workspace + os.path.sep + self.linter_rules_path + os.path.sep + self.config_file_name
            ):
                self.config_file = (
                    self.workspace + os.path.sep + self.linter_rules_path + os.path.sep + self.config_file_name
                )
            # in user repo directory provided in <Linter>RULES_PATH or LINTER_RULES_PATH
            elif os.path.isfile(
                self.default_rules_location + os.path.sep + self.config_file_name
            ):
                self.config_file = (
                    self.default_rules_location + os.path.sep + self.config_file_name
                )
            # Set config file label if not set by remote rule
            if self.config_file is not None and self.config_file_label is None:
                self.config_file_label = self.config_file.replace(
                    "/tmp/lint", ""
                ).replace("/action/lib/.automation/", "")
        # Include regex :try first NAME + _FILTER_REGEX_INCLUDE, then LANGUAGE + _FILTER_REGEX_INCLUDE
        if config.exists(self.name + "_FILTER_REGEX_INCLUDE"):
            self.filter_regex_include = config.get(self.name + "_FILTER_REGEX_INCLUDE")
        elif config.exists(self.descriptor_id + "_FILTER_REGEX_INCLUDE"):
            self.filter_regex_include = config.get(
                self.descriptor_id + "_FILTER_REGEX_INCLUDE"
            )
        # User arguments from config
        if config.get(self.name + "_ARGUMENTS", "") != "":
            self.cli_lint_user_args = config.get_list_args(self.name + "_ARGUMENTS")

        # Disable errors for this linter NAME + _DISABLE_ERRORS, then LANGUAGE + _DISABLE_ERRORS
        if config.get(self.name + "_DISABLE_ERRORS_IF_LESS_THAN"):
            self.disable_errors_if_less_than = int(
                config.get(self.name + "_DISABLE_ERRORS_IF_LESS_THAN")
            )
        if self.disable_errors_if_less_than is not None:
            self.disable_errors = False
        elif config.get(self.name + "_DISABLE_ERRORS", "") == "false":
            self.disable_errors = False
        elif config.get(self.name + "_DISABLE_ERRORS", "") == "true":
            self.disable_errors = True
        elif config.get(self.descriptor_id + "_DISABLE_ERRORS", "") == "false":
            self.disable_errors = False
        elif config.get(self.descriptor_id + "_DISABLE_ERRORS", "") == "true":
            self.disable_errors = True
        # Exclude regex: try first NAME + _FILTER_REGEX_EXCLUDE, then LANGUAGE + _FILTER_REGEX_EXCLUDE
        if config.exists(self.name + "_FILTER_REGEX_EXCLUDE"):
            self.filter_regex_exclude = config.get(self.name + "_FILTER_REGEX_EXCLUDE")
        elif config.exists(self.descriptor_id + "_FILTER_REGEX_EXCLUDE"):
            self.filter_regex_exclude = config.get(
                self.descriptor_id + "_FILTER_REGEX_EXCLUDE"
            )
        # Override default docker image version
        if config.exists(self.name + "_DOCKER_IMAGE_VERSION"):
            self.cli_docker_image_version = config.get(
                self.name + "_DOCKER_IMAGE_VERSION"
            )

    # Processes the linter
    def run(self):
        self.start_perf = perf_counter()
        # Apply actions defined on Linter class if defined
        self.before_lint_files()

        # Initialize linter reports
        for reporter in self.reporters:
            reporter.initialize()

        # Lint each file one by one
        if self.cli_lint_mode == "file":
            index = 0
            for file in self.files:
                file_status = "success"
                index = index + 1
                return_code, stdout = self.process_linter(file)
                file_errors_number = 0
                if return_code > 0:
                    file_status = "error"
                    self.status = "error"
                    self.return_code = 1
                    self.number_errors += 1
                    file_errors_number = self.get_total_number_errors(stdout)
                    self.total_number_errors += file_errors_number
                self.update_files_lint_results(
                    [file], return_code, file_status, stdout, file_errors_number
                )
        else:
            # Lint all workspace in one command
            return_code, stdout = self.process_linter()
            self.stdout = stdout
            if return_code != 0:
                self.status = "error"
                self.return_code = 1
                self.number_errors += 1
                self.total_number_errors += self.get_total_number_errors(stdout)
            # Build result for list of files
            if self.cli_lint_mode == "list_of_files":
                self.update_files_lint_results(self.files, None, None, None, None)
        # Set return code to 0 if failures in this linter must not make the Mega-Linter run fail
        if self.return_code != 0:
            # Disable errors: no failure, just warning
            if self.disable_errors is True:
                self.return_code = 0
            elif (
                self.disable_errors_if_less_than is not None
                and self.total_number_errors < self.disable_errors_if_less_than
            ):
                self.return_code = 0
        # Delete locally copied remote config file if necessary
        if self.remote_config_file_to_delete is not None:
            os.remove(self.remote_config_file_to_delete)
        # Generate linter reports
        self.elapsed_time_s = perf_counter() - self.start_perf
        for reporter in self.reporters:
            reporter.produce_report()
        return self

    def update_files_lint_results(
        self, linted_files, return_code, file_status, stdout, file_errors_number
    ):
        updated_files = utils.list_updated_files(self.github_workspace)
        for file in linted_files:
            if self.try_fix is True:
                fixed = utils.check_updated_file(
                    file, self.github_workspace, updated_files
                )
            else:
                fixed = False
            if fixed is True:
                self.number_fixed = self.number_fixed + 1
            # store result
            self.files_lint_results += [
                {
                    "file": file,
                    "status_code": return_code,
                    "status": file_status,
                    "stdout": stdout,
                    "fixed": fixed,
                    "errors_number": file_errors_number,
                }
            ]

    # List all reporters, then instantiate each of them
    def load_reporters(self):
        reporter_init_params = {"master": self, "report_folder": self.report_folder}
        self.reporters = utils.list_active_reporters_for_scope(
            "linter", reporter_init_params
        )

    def log_file_filters(self):
        log_object = {
            "name": self.name,
            "filter_regex_include": self.filter_regex_include,
            "filter_regex_exclude": self.filter_regex_exclude,
            "files_sub_directory": self.files_sub_directory,
            "lint_all_files": self.lint_all_files,
            "lint_all_other_linters_files": self.lint_all_other_linters_files,
            "file_extensions": self.file_extensions,
            "file_names_regex": self.file_names_regex,
            "file_names_not_ends_with": self.file_names_not_ends_with,
            "file_contains_regex": self.file_contains_regex,
        }
        logging.debug("[Filters] " + str(log_object))

    # Collect all files that will be analyzed by the current linter
    def collect_files(self, all_files):
        self.log_file_filters()
        # Filter all files to keep only the ones matching with the current linter
        self.files = utils.filter_files(
            all_files=all_files,
            filter_regex_include=self.filter_regex_include,
            filter_regex_exclude=self.filter_regex_exclude,
            file_names_regex=self.file_names_regex,
            file_extensions=self.file_extensions,
            file_names_not_ends_with=self.file_names_not_ends_with,
            file_contains_regex=self.file_contains_regex,
            files_sub_directory=self.files_sub_directory,
            lint_all_other_linters_files=self.lint_all_other_linters_files,
        )
        logging.debug(
            "%s linter files after applying linter filters:\n- %s",
            self.name,
            "\n- ".join(self.files),
        )

    # lint a single file or whole project
    def process_linter(self, file=None):
        # Build command using method locally defined on Linter class
        command = self.build_lint_command(file)
        logging.debug(f"[{self.linter_name}] command: {str(command)}")
        return_code, return_output = self.execute_lint_command(command)
        logging.debug(
            f"[{self.linter_name}] result: {str(return_code)} {return_output}"
        )
        return return_code, return_output

    # Execute a linting command . Can be overridden for special cases, like use of PowerShell script
    # noinspection PyMethodMayBeStatic
    def execute_lint_command(self, command):
        cwd = (
            os.getcwd()
            if self.cli_lint_mode in ["file", "list_of_files"]
            else self.workspace
        )
        cwd = os.path.abspath(cwd)
        logging.debug(f"[{self.linter_name}] CWD: {cwd}")
        subprocess_env = {**os.environ, "FORCE_COLOR": "0"}
        if type(command) == str:
            # Call linter with a sub-process
            process = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                shell=True,
                cwd=cwd,
                env=subprocess_env,
                executable=shutil.which("bash")
                if sys.platform == "win32"
                else "/bin/bash",
            )
        else:
            # Use full executable path if we are on Windows
            if sys.platform == "win32":
                cli_absolute = shutil.which(command[0])
                if cli_absolute is not None:
                    command[0] = cli_absolute
                else:
                    msg = "Unable to find command: " + command[0]
                    logging.error(msg)
                    return errno.ESRCH, msg

            # Call linter with a sub-process (RECOMMENDED: with a list of strings corresponding to the command)
            process = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=subprocess_env,
                cwd=cwd,
            )
        return_code = process.returncode
        return_stdout = utils.decode_utf8(process.stdout)
        # Return linter result
        return return_code, return_stdout

    # Returns linter version (can be overridden in special cases, like version has special format)
    def get_linter_version(self):
        if self.linter_version_cache is not None:
            return self.linter_version_cache
        version_output = self.get_linter_version_output()
        reg = self.version_extract_regex
        if type(reg) == str:
            reg = re.compile(reg)
        m = reg.search(version_output)
        if m:
            self.linter_version_cache = ".".join(m.group().split())
        else:
            logging.error(
                f"Unable to extract version with regex {str(reg)} from {version_output}"
            )
            self.linter_version_cache = "ERROR"
        return self.linter_version_cache

    # Returns the version of the associated linter (can be overridden in special cases, like version has special format)
    def get_linter_version_output(self):
        command = self.build_version_command()
        if sys.platform == "win32":
            cli_absolute = shutil.which(command[0])
            if cli_absolute is not None:
                command[0] = cli_absolute
        logging.debug("Linter version command: " + str(command))
        try:
            process = subprocess.run(
                command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
            )
            return_code = process.returncode
            output = utils.decode_utf8(process.stdout)
            logging.debug("Linter version result: " + str(return_code) + " " + output)
        except FileNotFoundError:
            logging.warning("Unable to call command [" + " ".join(command) + "]")
            return_code = 666
            output = "ERROR"

        if return_code != self.version_command_return_code:
            logging.warning(
                "Unable to get version for linter [" + self.linter_name + "]"
            )
            logging.warning(
                " ".join(command) + f" returned output: ({str(return_code)}) " + output
            )
            return "ERROR"
        else:
            return output

    # Returns linter help (can be overridden in special cases, like version has special format)
    def get_linter_help(self):
        if self.linter_help_cache is not None:
            return self.linter_help_cache
        help_command = self.build_help_command()
        return_code = 666
        output = ""
        command = ""
        for command in [help_command] + self.cli_help_extra_commands:
            try:
                if isinstance(command, str):
                    command = command.split(" ")
                if sys.platform == "win32":
                    cli_absolute = shutil.which(command[0])
                    if cli_absolute is not None:
                        command[0] = cli_absolute
                logging.debug("Linter help command: " + str(command))
                process = subprocess.run(
                    command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
                )
                return_code = process.returncode
                output += utils.decode_utf8(process.stdout)
                logging.debug("Linter help result: " + str(return_code) + " " + output)
            except FileNotFoundError:
                logging.warning("Unable to call command [" + " ".join(command) + "]")
                return_code = 666
                output += "ERROR"
                break

        if return_code != self.help_command_return_code or output.strip() == "":
            logging.warning("Unable to get help for linter [" + self.linter_name + "]")
            logging.warning(f"{str(command)} returned output: ({return_code}) {output}")
            return "ERROR"
        else:
            return output

    # noinspection PyMethodMayBeStatic
    def get_regex(self, reg):
        if reg is None:
            raise Exception("You must define a regex !")
        if type(reg) == str:
            reg = re.compile(reg)
        return reg

    def manage_docker_command(self, command):
        if self.cli_docker_image is None:
            return command
        docker_command = ["docker", "run"]
        if hasattr(self, "workspace"):
            volume_root = config.get("MEGALINTER_VOLUME_ROOT", "")
            if volume_root != "":
                workspace_value = (
                    volume_root + "/" + self.workspace.replace("/tmp/lint", "")
                )
            else:
                workspace_value = self.workspace
        else:
            workspace_value = "/tmp/lint"
        docker_command += map(
            lambda arg, w=workspace_value: arg.replace("{{WORKSPACE}}", w),
            self.cli_docker_args,
        )
        docker_command += [f"{self.cli_docker_image}:{self.cli_docker_image_version}"]
        if type(command) == str:
            command = " ".join(docker_command) + " " + command
        else:
            command = docker_command + command  # ["ls", "-A", "/tmp/lint"]
        return command

    ########################################
    # Methods that can be overridden below #
    ########################################

    def before_lint_files(self):
        pass

    # Build the CLI command to call to lint a file (can be overridden)
    def build_lint_command(self, file=None):
        cmd = [self.cli_executable]
        # Add other lint cli arguments if defined
        cmd += self.cli_lint_extra_args
        # Add fix argument if defined
        if self.apply_fixes is True and (
            self.cli_lint_fix_arg_name is not None
            or self.cli_executable_fix != self.cli_executable
        ):
            cmd[0] = self.cli_executable_fix
            cmd += [self.cli_lint_fix_arg_name]
            self.try_fix = True
        # Add user-defined extra arguments if defined
        cmd += self.cli_lint_user_args
        # Add config arguments if defined (except for case when no_config_if_fix is True)
        if self.config_file is not None:
            final_config_file = self.config_file
            if self.cli_docker_image is not None:
                final_config_file = final_config_file.replace(
                    self.workspace, "/tmp/lint"
                )
            if self.cli_config_arg_name.endswith("="):
                cmd += [self.cli_config_arg_name + final_config_file]
            elif self.cli_config_arg_name != "":
                cmd += [self.cli_config_arg_name, final_config_file]
            cmd += self.cli_config_extra_args
        # Add other lint cli arguments after other arguments if defined
        cmd += self.cli_lint_extra_args_after
        # Some linters/formatters update files by default.
        # To avoid that, declare -megalinter-fix-flag as cli_lint_fix_arg_name
        if self.try_fix is True:
            for arg in self.cli_lint_fix_remove_args:
                cmd.remove(arg)
            if "--megalinter-fix-flag" in cmd:
                cmd.remove("--megalinter-fix-flag")
        # Append file in command arguments
        if file is not None:
            cmd += [file]
        # If mode is "list of files", append all files as cli arguments
        elif self.cli_lint_mode == "list_of_files":
            cmd += self.files
        return self.manage_docker_command(cmd)

    # Find number of errors in linter stdout log
    def get_total_number_errors(self, stdout):
        total_errors = 0
        # Get number with a single regex.
        if self.cli_lint_errors_count == "regex_number":
            reg = self.get_regex(self.cli_lint_errors_regex)
            m = re.search(reg, stdout)
            if m:
                total_errors = int(m.group(1))
        # Count the number of occurrences of a regex corresponding to an error in linter log
        elif self.cli_lint_errors_count == "regex_count":
            reg = self.get_regex(self.cli_lint_errors_regex)
            total_errors = len(re.findall(reg, stdout))
        # Sum of all numbers found in linter logs with a regex
        elif self.cli_lint_errors_count == "regex_sum":
            reg = self.get_regex(self.cli_lint_errors_regex)
            matches = re.findall(reg, stdout)
            total_errors = sum(int(m) for m in matches)
        # Count all lines of the linter log
        elif self.cli_lint_errors_count == "total_lines":
            total_errors = sum(
                not line.isspace() and line != "" for line in stdout.splitlines()
            )
        # Return result if found, else default value according to status
        if total_errors > 0:
            return total_errors
        if self.cli_lint_errors_count is not None:
            logging.warning(
                f"Unable to get number of errors with {self.cli_lint_errors_count} "
                f"and {str(self.cli_lint_errors_regex)}"
            )
        if self.status == "success":
            return 0
        elif self.status == "error":
            return 1

    # Build the CLI command to get linter version (can be overridden if --version is not the way to get the version)
    def build_version_command(self):
        cmd = [self.cli_executable_version]
        cmd += self.cli_version_extra_args
        if self.cli_version_arg_name != "":
            cmd += [self.cli_version_arg_name]
        return self.manage_docker_command(cmd)

    # Build the CLI command to get linter version (can be overridden if --version is not the way to get the version)
    def build_help_command(self):
        cmd = [self.cli_executable_help]
        cmd += self.cli_help_extra_args
        cmd += [self.cli_help_arg_name]
        return self.manage_docker_command(cmd)

    # Provide additional details in text reporter logs
    # noinspection PyMethodMayBeStatic
    def complete_text_reporter_report(self, _reporter_self):
        return []
