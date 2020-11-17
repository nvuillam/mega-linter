#!/usr/bin/env python3
"""
Unit tests for Megalinter class

"""
import os
import time
import unittest

from megalinter.tests.test_megalinter.helpers import utilstest


class MegalinterFixesTest(unittest.TestCase):
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
        self.assertIn("Linting [JAVASCRIPT] files", output)
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
        self.assertIn("Linting [JAVASCRIPT] files", output)
        time.sleep(5)
        # Check fixable files has been updated
        fixable_files = [
            "csharp_for_fixes_1.cs"
            "env_for_fixes_1.env",
            "groovy_for_fixes_1.groovy"
            "javascript_for_fixes_1.js",
            "kotlin_for_fixes_1.kt",
            "markdown_for_fixes_1.md",
            "python_for_fixes_1.py",
            "ruby_for_fixes_1.rb",
            "vbdotnet_for_fixes_1.vb"
        ]
        updated_dir = os.environ.get("UPDATED_SOURCES_REPORTER_DIR", "updated_sources"),
        updated_sources_dir = f"{mega_linter.report_folder}{os.path.sep}{updated_dir}"
        for fixable_file in fixable_files:
            # Check linters applied updates
            utilstest.assert_file_has_been_updated(fixable_file, True, self)
            # Check UpdatedSourcesReporter result
            self.assertTrue(
                os.path.exists(updated_sources_dir+os.path.sep+fixable_file)
            )
