#!/usr/bin/env python3
"""
Unit tests for Megalinter class

"""
import os
import unittest

from megalinter.tests.test_megalinter.helpers import utilstest


class MegalinterFixesTest(unittest.TestCase):
    def setUp(self):
        utilstest.linter_test_setup(
            {'sub_lint_root': f'{os.path.sep}.automation{os.path.sep}test{os.path.sep}sample_project_fixes'})

    def test_1_apply_fixes_on_one_linter(self):
        super_linter, output = utilstest.call_super_linter({
            'APPLY_FIXES': 'MARKDOWN_MARKDOWNLINT',
            'ENABLE': 'MARKDOWN',
            'LOG_LEVEL': 'DEBUG',
            'MULTI_STATUS': 'false'
        })
        self.assertTrue(len(super_linter.linters) > 0,
                        "Linters have been created and run")
        self.assertIn('Linting [MARKDOWN] files', output)
        utilstest.assert_file_has_been_updated('markdown_for_fixes_1.groovy', True, self)
        utilstest.assert_file_has_been_updated('groovy_for_fixes_1.groovy', False, self)
        utilstest.assert_file_has_been_updated('javascript_for_fixes_1.groovy', False, self)

    def test_2_apply_fixes_on_all_linters(self):
        super_linter, output = utilstest.call_super_linter({
            'APPLY_FIXES': 'all',
            'LOG_LEVEL': 'DEBUG',
            'MULTI_STATUS': 'false'
        })
        self.assertTrue(len(super_linter.linters) > 0,
                        "Linters have been created and run")
        self.assertIn('Linting [JAVASCRIPT] files', output)
        utilstest.assert_file_has_been_updated('markdown_for_fixes_1.groovy', True, self)
        utilstest.assert_file_has_been_updated('groovy_for_fixes_1.groovy', True, self)
        utilstest.assert_file_has_been_updated('javascript_for_fixes_1.groovy', True, self)