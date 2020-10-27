#!/usr/bin/env python3
"""
Main Mega-Linter class, encapsulating all linters process and reporting

"""

import collections
import logging
import os
import re
import sys

import git
import terminaltables

from megalinter import utils


class Megalinter:

    # Constructor: Load global config, linters & compute file extensions
    def __init__(self, params=None):
        if params is None:
            params = {}
        self.workspace = self.get_workspace()
        self.github_workspace = os.environ.get(
            'GITHUB_WORKSPACE', self.workspace)
        self.initialize_logger()
        self.display_header()
        # Mega-Linter default rules location
        self.default_rules_location = '/action/lib/.automation' if os.path.exists('/action/lib/.automation') \
            else os.path.relpath(os.path.relpath(os.path.dirname(os.path.abspath(__file__)) + '/../TEMPLATES'))
        # User-defined rules location
        self.linter_rules_path = self.github_workspace + os.path.sep + '.github/linters'

        self.validate_all_code_base = True
        self.filter_regex_include = None
        self.filter_regex_exclude = None
        self.cli = params['cli'] if "cli" in params else False
        self.default_linter_activation = True

        # Get enable / disable vars
        self.enable_descriptors = utils.get_dict_string_list(
            os.environ, 'ENABLE', [])
        self.enable_linters = utils.get_dict_string_list(
            os.environ, 'ENABLE_LINTERS', [])
        self.disable_descriptors = utils.get_dict_string_list(
            os.environ, 'DISABLE', [])
        self.disable_linters = utils.get_dict_string_list(
            os.environ, 'DISABLE_LINTERS', [])
        self.manage_default_linter_activation()

        # Report vars
        self.report_folder = os.environ.get(
            'REPORT_OUTPUT_FOLDER', self.github_workspace + os.path.sep + 'report')
        # Load optional configuration
        self.load_config_vars()
        # Runtime properties
        self.reporters = []
        self.linters = []
        self.file_extensions = []
        self.file_names = []
        self.status = "success"
        self.return_code = 0
        # Initialize linters and gather criteria to browse files
        self.load_linters()
        self.compute_file_extensions()
        # Load Mega-Linter reporters
        self.load_reporters()

    # Collect files, run linters on them and write reports
    def run(self):

        # Collect files for each identified linter
        self.collect_files()

        # Display collection summary in log
        table_data = [["Descriptor", "Linter", "Criteria", "Matching files"]]
        for linter in self.linters:
            if len(linter.files) > 0:
                all_criteria = linter.file_extensions + linter.file_names
                table_data += [[linter.descriptor_id,
                                linter.linter_name,
                                '|'.join(all_criteria),
                                str(len(linter.files))]]
        table = terminaltables.AsciiTable(table_data)
        table.title = "----MATCHING LINTERS"
        logging.info("")
        for table_line in table.table.splitlines():
            logging.info(table_line)
        logging.info(" ")

        # Run linters
        for linter in self.linters:
            if linter.is_active is True:
                linter.run()
                if linter.status != 'success':
                    self.status = 'error'
                if linter.return_code != 0:
                    self.return_code = linter.return_code
        # Generate reports
        for reporter in self.reporters:
            reporter.produce_report()
        # Manage return code
        self.check_results()

    # noinspection PyMethodMayBeStatic
    def get_workspace(self):
        default_workspace = os.environ.get('DEFAULT_WORKSPACE', '')
        github_workspace = os.environ.get('GITHUB_WORKSPACE', '')
        # Github action run without override of DEFAULT_WORKSPACE and using /tmp/lint
        if default_workspace == '' and github_workspace != '' and os.path.exists(github_workspace + '/tmp/lint'):
            logging.debug('Context: Github action run without override of DEFAULT_WORKSPACE and using /tmp/lint')
            return github_workspace + '/tmp/lint'
        # Docker run without override of DEFAULT_WORKSPACE
        elif default_workspace != '' and os.path.exists('/tmp/lint' + os.path.sep + default_workspace):
            logging.debug('Context: Docker run without override of DEFAULT_WORKSPACE')
            return default_workspace + '/tmp/lint' + os.path.sep + default_workspace
        # Docker run with override of DEFAULT_WORKSPACE for test cases
        elif default_workspace != '' and os.path.exists(default_workspace):
            logging.debug('Context: Docker run with override of DEFAULT_WORKSPACE for test cases')
            return default_workspace
        # Docker run test classes without override of DEFAULT_WORKSPACE
        elif os.path.exists('/tmp/lint'):
            logging.debug('Context: Docker run test classes without override of DEFAULT_WORKSPACE')
            return '/tmp/lint'
        # Github action with override of DEFAULT_WORKSPACE
        elif default_workspace != '' and github_workspace != '' \
                and os.path.exists(github_workspace + os.path.sep + default_workspace):
            logging.debug('Context: Github action with override of DEFAULT_WORKSPACE')
            return github_workspace + os.path.sep + default_workspace
        # Github action without override of DEFAULT_WORKSPACE and NOT using /tmp/lint
        elif default_workspace == '' and github_workspace != '' \
                and github_workspace != '/' and os.path.exists(github_workspace):
            logging.debug('Context: Github action without override of DEFAULT_WORKSPACE and NOT using /tmp/lint')
            return github_workspace
        # Unable to identify workspace
        else:
            raise FileNotFoundError(f"Unable to find a workspace to lint \n"
                                    f"DEFAULT_WORKSPACE: {default_workspace}\n"
                                    f"GITHUB_WORKSPACE: {github_workspace}")

    # Manage configuration variables
    def load_config_vars(self):
        # Linter rules root path
        if "LINTER_RULES_PATH" in os.environ:
            self.linter_rules_path = self.github_workspace + \
                                     os.path.sep + os.environ["LINTER_RULES_PATH"]
        # Filtering regex (inclusion)
        if "FILTER_REGEX_INCLUDE" in os.environ:
            self.filter_regex_include = os.environ["FILTER_REGEX_INCLUDE"]
        # Filtering regex (exclusion)
        if "FILTER_REGEX_EXCLUDE" in os.environ:
            self.filter_regex_exclude = os.environ["FILTER_REGEX_EXCLUDE"]

        # Disable all fields validation if VALIDATE_ALL_CODEBASE is 'false'
        if "VALIDATE_ALL_CODEBASE" in os.environ and os.environ["VALIDATE_ALL_CODEBASE"] == 'false':
            self.validate_all_code_base = False

    # Calculate default linter activation according to env variables
    def manage_default_linter_activation(self):
        # If at least one language/linter is activated with VALIDATE_XXX , all others are deactivated by default
        if len(self.enable_descriptors) > 0 or len(self.enable_linters) > 0:
            self.default_linter_activation = False
        # V3 legacy variables
        for env_var in os.environ:
            if env_var.startswith('VALIDATE_') and env_var != 'VALIDATE_ALL_CODEBASE':
                if os.environ[env_var] == 'true':
                    self.default_linter_activation = False

    # Load and initialize all linters
    def load_linters(self):
        # Linters init params
        linter_init_params = {'linter_rules_path': self.linter_rules_path,
                              'default_rules_location': self.default_rules_location,
                              'default_linter_activation': self.default_linter_activation,
                              'enable_descriptors': self.enable_descriptors,
                              'enable_linters': self.enable_linters,
                              'disable_descriptors': self.disable_descriptors,
                              'disable_linters': self.disable_linters,
                              'workspace': self.workspace,
                              'github_workspace': self.github_workspace,
                              'report_folder': self.report_folder}

        # Build linters from descriptor files
        all_linters = utils.list_all_linters(linter_init_params)
        skipped_linters = []
        for linter in all_linters:
            if linter.is_active is False:
                skipped_linters += [linter.name]
                continue
            self.linters += [linter]
        # Display skipped linters in log
        if len(skipped_linters) > 0:
            skipped_linters.sort()
            logging.info('Skipped linters: ' + ', '.join(skipped_linters))
        # Sort linters by language and linter_name
        self.linters.sort(key=lambda x: (x.descriptor_id, x.linter_name))

    # List all reporters, then instantiate each of them
    def load_reporters(self):
        reporter_init_params = {'master': self,
                                'report_folder': self.report_folder}
        self.reporters = utils.list_active_reporters_for_scope('mega-linter', reporter_init_params)

    # Define all file extensions to browse
    def compute_file_extensions(self):
        for linter in self.linters:
            self.file_extensions += linter.file_extensions
            self.file_names += linter.file_names
        # Remove duplicates
        self.file_extensions = list(
            collections.OrderedDict.fromkeys(self.file_extensions))
        self.file_names = list(
            collections.OrderedDict.fromkeys(self.file_names))

    # Collect list of files matching extensions and regex
    def collect_files(self):
        all_files = list()
        if self.validate_all_code_base is False:
            # List all updated files from git
            logging.info(
                'Listing updated files in [' + self.github_workspace + '] using git diff, then filter with:')
            repo = git.Repo(os.path.realpath(self.github_workspace))
            default_branch = os.environ.get('DEFAULT_BRANCH', 'master')
            current_branch = os.environ.get('GITHUB_SHA', '')
            if current_branch == '':
                current_branch = repo.active_branch.commit.hexsha
            try:
                repo.git.pull()
            except git.GitCommandError:
                try:
                    repo.git.checkout(current_branch)
                    repo.git.pull()
                except git.GitCommandError:
                    logging.error(f"Unable to pull current branch {current_branch}")
            repo.git.checkout(default_branch)
            diff = repo.git.diff(
                f"{default_branch}...{current_branch}", name_only=True)
            repo.git.checkout(current_branch)
            logging.info(f"Git diff :\n{diff}")
            for diff_line in diff.splitlines():
                if os.path.exists(self.workspace + os.path.sep + diff_line):
                    all_files += [self.workspace + os.path.sep + diff_line]
        else:
            # List all files under workspace root directory
            logging.info(
                'Listing all files in directory [' + self.workspace + '], then filter with:')
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                logging.debug(', '.join(os.listdir(self.workspace)))
            excluded_directories = utils.list_excluded_directories()
            for (dirpath, dirnames, filenames) in os.walk(self.workspace):
                exclude = False
                for dir1 in dirnames:
                    if dir1 in excluded_directories:
                        exclude = True
                if exclude is False:
                    all_files += [os.path.join(dirpath, file)
                                  for file in sorted(filenames)]

        # Filter files according to fileExtensions, fileNames , filterRegexInclude and filterRegexExclude
        if len(self.file_extensions) > 0:
            logging.info('- File extensions: ' +
                         ', '.join(self.file_extensions))
        if len(self.file_names) > 0:
            logging.info('- File names: ' + ', '.join(self.file_names))
        if self.filter_regex_include is not None:
            logging.info('- Including regex: ' + self.filter_regex_include)
        if self.filter_regex_exclude is not None:
            logging.info('- Excluding regex: ' + self.filter_regex_exclude)
        filtered_files = []
        for file in all_files:
            base_file_name = os.path.basename(file)
            filename, file_extension = os.path.splitext(base_file_name)
            norm_file = file.replace(os.sep, '/')
            if self.filter_regex_include is not None and re.search(self.filter_regex_include, norm_file) is None:
                continue
            if self.filter_regex_exclude is not None and re.search(self.filter_regex_exclude, norm_file) is not None:
                continue
            elif file_extension in self.file_extensions:
                filtered_files += [file]
            elif filename in self.file_names:
                filtered_files += [file]
            elif "*" in self.file_extensions:
                filtered_files += [file]

        logging.info('Kept [' + str(len(filtered_files)) +
                     '] files on [' + str(len(all_files)) + '] found files')

        # Collect matching files for each linter
        for linter in self.linters:
            linter.collect_files(filtered_files)
            if len(linter.files) == 0 and linter.lint_all_files is False:
                linter.is_active = False

    def initialize_logger(self):
        logging_level_key = os.environ.get('LOG_LEVEL', 'INFO')
        logging_level_list = {'INFO': logging.INFO,
                              "DEBUG": logging.DEBUG,
                              "WARNING": logging.WARNING,
                              "ERROR": logging.ERROR,
                              # Previous values for v3 ascending compatibility
                              "TRACE": logging.WARNING,
                              "VERBOSE": logging.INFO
                              }
        logging_level = logging_level_list[
            logging_level_key] if logging_level_key in logging_level_list else logging.INFO
        log_file = self.github_workspace + os.path.sep + os.environ.get('LOG_FILE', 'mega-linter.log')
        logging.basicConfig(force=True,
                            level=logging_level,
                            format='%(asctime)s [%(levelname)s] %(message)s',
                            handlers=[
                                logging.FileHandler(log_file),
                                logging.StreamHandler(sys.stdout)
                            ])

    @staticmethod
    def display_header():
        # Header prints
        logging.info(utils.format_hyphens(""))
        logging.info(utils.format_hyphens(
            "GitHub Actions Multi Language Linter"))
        logging.info(utils.format_hyphens(""))
        logging.info(" - Image Creation Date: " +
                     os.environ.get('BUILD_DATE', 'No docker image'))
        logging.info(" - Image Revision: " +
                     os.environ.get('BUILD_REVISION', 'No docker image'))
        logging.info(" - Image Version: " +
                     os.environ.get('BUILD_VERSION', 'No docker image'))
        logging.info(utils.format_hyphens(""))
        logging.info("The Mega-Linter source code can be found at:")
        logging.info(" - https://github.com/nvuillam/mega-linter")
        logging.info(utils.format_hyphens(""))
        # Display env variables for debug mode
        for name, value in sorted(os.environ.items()):
            logging.debug("" + name + "=" + value)
        logging.debug(utils.format_hyphens(""))
        logging.info("")

    def check_results(self):
        if self.status == 'success':
            logging.info('Successfully linted all files without errors')
        else:
            logging.error('Error(s) has been found during linting')
            if self.cli is True:
                if os.environ.get('DISABLE_ERRORS', 'false') == 'true':
                    sys.exit(0)
                else:
                    sys.exit(self.return_code)
