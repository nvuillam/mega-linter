#!/usr/bin/env python3
"""
Output results in RDJSONL format for later processing by Reviewdog
"""
import json
import logging
import os
import re

from megalinter import Reporter, config, utils


class Location(dict):
    def __init__(self, line, column) -> None:
        super().__init__(line=line, column=column)


class Suggestion(dict):
    def __init__(self, suggestion_text, start, end) -> None:
        super().__init__(text=suggestion_text, range={"start": start, "end": end})


class Rdjsonl(dict):
    def __init__(self, file, message, start, end=None, severity="ERROR", suggestions=None) -> None:
        if suggestions is None:
            suggestions = []
        location = {"range": {"start": start, "end": end}, "path": file}
        super().__init__(message=message, location=location, severity=severity, suggestions=suggestions)


display_name = "Reviewdog Linter Reporter"


class ReviewdogLinterReporter(Reporter):
    name = "REVIEWDOG"
    report_type = "detailed"
    scope = "linter"

    def __init__(self, params=None):
        super().__init__(params)
        self.processor_config = None
        if hasattr(self.master, "reviewdog_processor"):
            self.processor_config = self.master.reviewdog_processor

    def manage_activation(self):
        # Super-Linter legacy variables
        output_format = config.get("OUTPUT_FORMAT", "")
        if output_format.startswith("reviewdog"):
            self.is_active = True
        # Mega-Linter vars (false by default)
        elif config.get("REVIEWDOG_REPORTER", "true") != "true":
            self.is_active = False
        else:
            self.is_active = True

    def produce_report(self):
        if not self.processor_config:
            logging.warning(
                f"[{display_name}] Cannot generate Reviewdog report for {self.master.linter_name} as no processor is defined."
            )
            return

        report_lines = []
        # Linter has run file by file
        if self.master.cli_lint_mode == "file":
            for file_result in self.master.files_lint_results:
                file_nm = file_result["file"]
                report_lines += file_result["stdout"].splitlines()
        # Bulk output as linter has run all project or files in one call
        elif self.master.cli_lint_mode in ["project", "list_of_files"]:
            report_lines += self.master.stdout.splitlines()
        # Complete lines
        report_lines += self.master.complete_text_reporter_report(self)

        # Convert to RDJsonl
        processor = getattr(self, self.processor_config["class_name"])(self.processor_config["init_params"])
        rdjsonl = processor.convert(report_lines)

        # Write to file
        report_sub_folder = config.get("REVIEWDOG_REPORTER_SUB_FOLDER", "reviewdog")
        file_name = (
            f"{self.report_folder}{os.path.sep}"
            f"{report_sub_folder}{os.path.sep}"
            f"{self.master.status.upper()}-{self.master.name}.log"
        )
        if not os.path.isdir(os.path.dirname(file_name)):
            os.makedirs(os.path.dirname(file_name), exist_ok=True)
        with open(file_name, "w", encoding="utf-8") as text_file:
            text_file_content = "\n".join([json.dumps(line) for line in rdjsonl]) + "\n"
            text_file.write(text_file_content)
            logging.info(
                f"[{display_name}] Generated {self.name} report: {file_name}"
            )

    class RdjsonlConvertor:
        def convert(self, outputlines):
            return []

    class Regex(RdjsonlConvertor):
        def __init__(self, init_params) -> None:
            self.regex = re.compile(init_params['regex'])
            self.ignored_line_regexes = [re.compile(r) for r in init_params['ignored_line_regexes']] \
                if 'ignored_line_regexes' in init_params else []
            super().__init__()

        def convert_line(self, line):
            match = re.match(self.regex, line)
            if match:
                return Rdjsonl(utils.normalize_log_string(match.group("path")), match.group("message"),
                               start=Location(line=int(match.group("line")), column=int(match.group("column"))))
            for ignored_pattern in self.ignored_line_regexes:
                if ignored_pattern.match(line):
                    return
            logging.warning(f"[{display_name}] Failed to process non ignored line: {line}")
            return

        def convert(self, outputlines):
            return [rdjson for rdjson in (self.convert_line(line) for line in outputlines) if rdjson]

    class UnifiedDiffs(RdjsonlConvertor):
        def __init__(self, init_params) -> None:
            self.file_header_regex = re.compile(init_params['file_header_regex'])
            self.message_include_file_header = init_params['message_include_file_header'] \
                if "message_include_file_header" in init_params else False
            self.diff_start_regex = re.compile(r"^--- \S+\s+\d{4}-\d{2}-\d{2}")
            self.ignored_line_regexes = [re.compile(r) for r in init_params['ignored_line_regexes']] \
                if 'ignored_line_regexes' in init_params else []
            super().__init__()

        def suggestion(self, hunk):
            target_lines = hunk.target
            end_column = len(target_lines[-1])
            text = "\n".join(target_lines)
            return Suggestion(text, start=Location(hunk.source_start, 0), end=Location(hunk.source_start + hunk.source_length, end_column))

        def process_udiff(self, udiff, path, message):
            from unidiff import PatchSet
            patches = PatchSet(udiff)
            suggestions = [self.suggestion(hunk) for patch in patches for hunk in patch]
            return [Rdjsonl(file=path, message=message,
                            start=suggestion["range"]["start"], end=suggestion["range"]["end"],
                            suggestions=suggestions)
                    for suggestion in suggestions]

        def convert(self, outputlines):
            diffs = {}
            current_file = None
            found_diff_header = False
            message = {}
            for line in outputlines:
                header_match = self.file_header_regex.match(line)
                if header_match:
                    current_file = header_match.group("path")
                    diffs[current_file] = []
                    message[current_file] = [line] if self.message_include_file_header else []
                    found_diff_header = False
                    continue
                if self.diff_start_regex.match(line):
                    found_diff_header = True
                if not current_file:
                    continue #if we have not yet found a file header, just skip the lines.

                if not found_diff_header:
                    for ignored_pattern in self.ignored_line_regexes:
                        if ignored_pattern.match(line):
                            break
                    else:
                        message[current_file] += [line]
                else:
                    diffs[current_file] += [line]
            results = []
            for file, udiff in diffs.items():
                if udiff:
                    results += self.process_udiff(udiff="\n".join(udiff),
                                                  path=utils.normalize_log_string(file),
                                                  message="\n".join(message[file]))
            return results
