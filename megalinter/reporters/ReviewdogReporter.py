#!/usr/bin/env python3
"""
Reviewdog reporter
See https://github.com/reviewdog/reviewdog/tree/master/proto/rdf#rd for details
"""
import logging
import os
import re
import shutil
import subprocess
import sys

from megalinter import Reporter, config

display_name = "Reviewdog Reporter"


class ReviewdogReporter(Reporter):
    name = "REVIEWDOG"
    report_type = "detailed"
    scope = "mega-linter"

    github_api_url = "https://api.github.com"

    def __init__(self, params=None):
        self.processing_order = -9
        super().__init__(params)

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
        if config.get("GITHUB_TOKEN", "") == "":
            logging.info(f"[{display_name}] No GitHub Token found, so skipped post of PR comment")
            return
        github_pr_ref = re.match(r"^refs/pull/(\d+)/merge$", config.get("GITHUB_REF", ""))
        if not github_pr_ref:
            logging.info(f"[{display_name}] Not a Github PR, so skipped post of PR comment")
            return

        report_sub_folder = (
            f"{self.report_folder}{os.path.sep}"
            f"{config.get('REVIEWDOG_REPORTER_SUB_FOLDER', 'reviewdog')}{os.path.sep}"
        )
        overall_rdjsonl = ""
        try:
            with os.scandir(report_sub_folder) as reports:
                for f in reports:
                    if not f.name.startswith("ERROR") or not f.is_file():
                        continue
                    with open(f.path, "r", encoding="utf-8") as linter_report:
                        overall_rdjsonl += "".join(linter_report.readlines())
        except FileNotFoundError as error:
            logging.warning(f"[{display_name}] Reviewdog reports directory does not exist: {error.filename}")
            return

        repository_owner, repository = config.get("GITHUB_REPOSITORY").split("/")

        process = subprocess.Popen(
            "reviewdog -f=rdjsonl -reporter=github-pr-review -filter-mode=nofilter",
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=True,
            env={
                **os.environ,
                "FORCE_COLOR": "0",
                "REVIEWDOG_GITHUB_API_TOKEN": config.get("GITHUB_TOKEN"),
                "GITHUB_API": config.get("GITHUB_API_URL", self.github_api_url),
                "CI_REPO_OWNER": repository_owner,
                "CI_REPO_NAME": repository,
                "CI_COMMIT": config.get("GITHUB_SHA"),
                "CI_PULL_REQUEST": github_pr_ref.group(1)
            },
            executable=shutil.which("bash")
            if sys.platform == "win32"
            else "/bin/bash",
        )
        reviewdog_stdout = process.communicate(input=overall_rdjsonl.encode())[0]
        if process.returncode != 0:
            logging.warning(f"[{display_name}] Error while generating Reviewdog report. "
                            f"Reviewdog exit code {process.returncode}: \n{str(reviewdog_stdout)}")
