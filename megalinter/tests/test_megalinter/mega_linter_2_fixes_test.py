#!/usr/bin/env python3
"""
Unit tests for Megalinter class

"""
import os
import time
import unittest

from megalinter.tests.test_megalinter.helpers import utilstest


class mega_linter_2_fixes(unittest.TestCase):
    def setUp(self):
        utilstest.linter_test_setup(
            {
                "sub_lint_root": f"{os.path.sep}.automation{os.path.sep}test{os.path.sep}sample_project_fixes"
            }
        )

    def test_1_apply_fixes_on_one_linter(self):
        mega_linter, output = utilstest.call_mega_linter(
            {
                "APPLY_FIXES": "JAVASCRIPT_STANDARD",
                "LOG_LEVEL": "DEBUG",
                "MULTI_STATUS": "false",
            }
        )
        self.assertTrue(
            len(mega_linter.linters) > 0, "Linters have been created and run"
        )
        self.assertIn("### Processed [JAVASCRIPT] files", output)
        time.sleep(5)
        utilstest.assert_file_has_been_updated("javascript_for_fixes_1.js", True, self)
        utilstest.assert_file_has_been_updated("env_for_fixes_1.env", False, self)

    def test_2_apply_fixes_on_all_linters(self):
        mega_linter, output = utilstest.call_mega_linter(
            {"APPLY_FIXES": "all", "LOG_LEVEL": "DEBUG", "MULTI_STATUS": "false"}
        )
        self.assertTrue(
            len(mega_linter.linters) > 0, "Linters have been created and run"
        )
        self.assertIn("### Processed [JAVASCRIPT] files", output)
        time.sleep(5)
        # Check fixable files has been updated
        fixable_files = [
            "bash_for_fixes_1.sh",
            "csharp_for_fixes_1.cs",
            "env_for_fixes_1.env",
            "groovy_for_fixes_1.groovy",
            "javascript_for_fixes_1.js",
            "kotlin_for_fixes_1.kt",
            "markdown_for_fixes_1.md",
            "python_for_fixes_1.py",
            "rst_for_fixes_1.rst",
            "ruby_for_fixes_1.rb",
            "spell_for_fixes_1.js",
            # "scala_for_fixes_1.scala",
            "snakemake_for_fixes_1.smk",
            "vbdotnet_for_fixes_1.vb",
            "yaml_for_fixes_1.yml",
        ]
        # updated_dir = config.get("UPDATED_SOURCES_REPORTER_DIR", "updated_sources")
        # updated_sources_dir = f"{mega_linter.report_folder}{os.path.sep}{updated_dir}"
        for fixable_file in fixable_files:
            # Check linters applied updates
            utilstest.assert_file_has_been_updated(fixable_file, True, self)
            # Check UpdatedSourcesReporter result
            # file_name = (
            #     updated_sources_dir
            #    + os.path.sep
            #    + fixable_file.replace(utils.get_sources_folder(), "")
            # )
            # self.assertTrue(
            #    os.path.isfile(file_name),
            #    f"File {file_name} not found in UpdatedSources report",
            # )
