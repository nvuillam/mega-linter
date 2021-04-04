#!/usr/bin/env python3
"""
Template class for custom reporters: any linter class in /reporters folder must inherit from this class
"""


class Reporter:
    # Report definition
    name = None
    report_folder = None
    scope = None  # Can be mega-linter or linter

    # Constructor: Initialize Linter instance with name and config variables
    def __init__(self, params=None):
        self.processing_order = 0
        self.master = params["master"]
        self.report_folder = params["report_folder"]
        # Any reporter is inactive by default except if __init__ is overridden on sub class
        if not hasattr(self, "is_active"):
            self.is_active = False
        self.report_items = []
        self.manage_activation()

    # Method produce_report can be overridden at custom report class
    def manage_activation(self):
        pass

    # Method produce_report can be overridden at custom report class
    def initialize(self, **kwargs):
        pass

    # Method produce_report can be overridden at custom report class
    def add_report_item(self, **kwargs):
        pass

    # Method produce_report can be overridden at custom report class
    def produce_report(self):
        pass
