#!/usr/bin/env python3
"""
TAP reporter
https://testanything.org/
"""
import logging
import os

from megalinter import Reporter


class TapReporter(Reporter):
    name = "TAP"
    scope = "linter"

    def __init__(self, params=None):
        # report_type is tap by default
        self.report_type = "tap"
        super().__init__(params)

    def manage_activation(self):
        output_format = os.environ.get("OUTPUT_FORMAT", "")
        if output_format.startswith("tap"):
            self.is_active = True
            if os.environ.get("OUTPUT_DETAIL", "") == "detailed":
                self.report_type = "detailed"

    def add_report_item(self, file, status_code, stdout, index, fixed=False):
        if self.master.cli_lint_mode == "project":
            return
        file_nm = file.replace("/tmp/lint/", "")
        tap_status = "ok" if status_code == 0 else "not ok"
        file_tap_lines = [f"{tap_status} {str(index)} - {file_nm}"]
        if self.report_type == "detailed" and stdout != "" and status_code != 0:
            std_out_tap = stdout.rstrip(f" {os.linesep}") + os.linesep
            std_out_tap = "\\n".join(std_out_tap.split(os.linesep))
            std_out_tap = std_out_tap.replace(":", " ")
            detailed_lines = ["  ---", f"  message: {std_out_tap}", "  ..."]
            file_tap_lines += detailed_lines
        self.report_items += file_tap_lines

    def produce_report(self):
        if self.master.cli_lint_mode == "project":
            return
        tap_report_lines = ["TAP version 13", f"1..{str(len(self.master.files))}"]
        tap_report_lines += self.report_items
        tap_file_name = (
            f"{self.report_folder}{os.path.sep}mega-linter-{self.master.name}.tap"
        )
        if not os.path.isdir(os.path.dirname(tap_file_name)):
            os.makedirs(os.path.dirname(tap_file_name))
        with open(tap_file_name, "w", encoding="utf-8") as tap_file:
            tap_file_content = "\n".join(tap_report_lines) + "\n"
            tap_file.write(tap_file_content)
            logging.debug(f"Generated {self.name} report: {tap_file_name}")
