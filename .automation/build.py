# !/usr/bin/env python3
"""
Automatically generate source code ,descriptive files Dockerfiles and documentation
"""
# pylint: disable=import-error
import json
import logging
import os
import re
import sys
from shutil import copyfile
from typing import Any
from urllib import parse as parse_urllib

import jsonschema
import markdown
import megalinter
import terminaltables
import yaml
from bs4 import BeautifulSoup
from giturlparse import parse
from webpreview import web_preview

BRANCH = "master"
URL_ROOT = "https://github.com/nvuillam/mega-linter/tree/" + BRANCH
MKDOCS_URL_ROOT = "https://nvuillam.github.io/mega-linter"
URL_RAW_ROOT = "https://github.com/nvuillam/mega-linter/raw/" + BRANCH
TEMPLATES_URL_ROOT = URL_ROOT + "/TEMPLATES"
DOCS_URL_ROOT = URL_ROOT + "/docs"
DOCS_URL_DESCRIPTORS_ROOT = DOCS_URL_ROOT + "/descriptors"
DOCS_URL_FLAVORS_ROOT = DOCS_URL_ROOT + "/flavors"
DOCS_URL_RAW_ROOT = URL_RAW_ROOT + "/docs"
REPO_HOME = os.path.dirname(os.path.abspath(__file__)) + os.path.sep + ".."
REPO_ICONS = REPO_HOME + "/docs/assets/icons"
REPO_IMAGES = REPO_HOME + "/docs/assets/images"

VERSIONS_FILE = REPO_HOME + "/.automation/generated/linter-versions.json"
HELPS_FILE = REPO_HOME + "/.automation/generated/linter-helps.json"
LINKS_PREVIEW_FILE = REPO_HOME + "/.automation/generated/linter-links-previews.json"
FLAVORS_DIR = REPO_HOME + "/flavors"
GLOBAL_FLAVORS_FILE = REPO_HOME + "/megalinter/descriptors/all_flavors.json"

BASE_SHIELD_IMAGE_LINK = "https://img.shields.io/docker/image-size"
BASE_SHIELD_COUNT_LINK = "https://img.shields.io/docker/pulls"

DESCRIPTOR_JSON_SCHEMA = (
    f"{REPO_HOME}/megalinter/descriptors/schemas/megalinter-descriptor.jsonschema.json"
)
CONFIG_JSON_SCHEMA = f"{REPO_HOME}/megalinter/descriptors/schemas/megalinter-configuration.jsonschema.json"
OWN_MEGALINTER_CONFIG_FILE = f"{REPO_HOME}/.mega-linter.yml"

IDE_LIST = {
    "atom": {"label": "Atom", "url": "https://atom.io/"},
    "brackets": {"label": "Brackets", "url": "http://brackets.io/"},
    "eclipse": {"label": "Eclipse", "url": "https://www.eclipse.org/"},
    "emacs": {"label": "Emacs", "url": "https://www.gnu.org/software/emacs/"},
    "idea": {
        "label": "IDEA",
        "url": "https://www.jetbrains.com/products.html#type=ide",
    },
    "sublime": {"label": "Sublime Text", "url": "https://www.sublimetext.com/"},
    "vim": {"label": "vim", "url": "https://www.vim.org/"},
    "vscode": {"label": "Visual Studio Code", "url": "https://code.visualstudio.com/"},
}

DESCRIPTORS_FOR_BUILD_CACHE = None


# Generate one Dockerfile by Mega-Linter flavor
def generate_all_flavors():
    flavors = megalinter.flavor_factory.list_megalinter_flavors()

    for flavor, flavor_info in flavors.items():
        generate_flavor(flavor, flavor_info)
    update_mkdocs_and_workflow_yml_with_flavors()


# Automatically generate Dockerfile , action.yml and upgrade all_flavors.json
def generate_flavor(flavor, flavor_info):
    descriptor_and_linters = []
    flavor_descriptors = []
    flavor_linters = []
    # Get install instructions at descriptor level
    descriptor_files = megalinter.linter_factory.list_descriptor_files()
    for descriptor_file in descriptor_files:
        with open(descriptor_file, "r", encoding="utf-8") as f:
            descriptor = yaml.load(f, Loader=yaml.FullLoader)
            if match_flavor(descriptor, flavor) is True and "install" in descriptor:
                descriptor_and_linters += [descriptor]
                flavor_descriptors += [descriptor["descriptor_id"]]
    # Get install instructions at linter level
    linters = megalinter.linter_factory.list_all_linters()
    requires_docker = False
    for linter in linters:
        if match_flavor(vars(linter), flavor) is True:
            descriptor_and_linters += [vars(linter)]
            flavor_linters += [linter.name]
            if linter.cli_docker_image is not None:
                requires_docker = True
    # Initialize Dockerfile
    if flavor == "all":
        dockerfile = f"{REPO_HOME}/Dockerfile"
    else:
        # Flavor json
        flavor_file = f"{FLAVORS_DIR}/{flavor}/flavor.json"
        if os.path.isfile(flavor_file):
            with open(flavor_file, "r", encoding="utf-8") as json_file:
                flavor_info = json.load(json_file)
        flavor_info["descriptors"] = flavor_descriptors
        flavor_info["linters"] = flavor_linters
        os.makedirs(os.path.dirname(flavor_file), exist_ok=True)
        with open(flavor_file, "w", encoding="utf-8") as outfile:
            json.dump(flavor_info, outfile, indent=4, sort_keys=True)
            outfile.write("\n")
        # Write in global flavors files
        with open(GLOBAL_FLAVORS_FILE, "r", encoding="utf-8") as json_file:
            global_flavors = json.load(json_file)
            global_flavors[flavor] = flavor_info
        with open(GLOBAL_FLAVORS_FILE, "w", encoding="utf-8") as outfile:
            json.dump(global_flavors, outfile, indent=4, sort_keys=True)
            outfile.write("\n")
        # Flavored dockerfile
        dockerfile = f"{FLAVORS_DIR}/{flavor}/Dockerfile"
        if not os.path.isdir(os.path.dirname(dockerfile)):
            os.makedirs(os.path.dirname(dockerfile), exist_ok=True)
        copyfile(f"{REPO_HOME}/Dockerfile", dockerfile)
        flavor_label = flavor_info["label"]
        comment = f"# MEGA-LINTER FLAVOR [{flavor}]: {flavor_label}"
        with open(dockerfile, "r+", encoding="utf-8") as f:
            content = f.read()
            f.seek(0)
            f.truncate()
            f.write(f"{comment}\n{content}")
        # Generate action.yml
        image_release = "v4"
        flavor_x = f"[{flavor} flavor]"
        action_yml = f""" # Automatically generated by build.py
name: "Mega-Linter"
author: "Nicolas Vuillamy"
description: "{flavor_x} Combine all available linters to automatically validate your sources without configuration !"
outputs:
  has_updated_sources:
    description: "0 if no source file has been updated, 1 if source files has been updated"
runs:
  using: "docker"
  image: "docker://nvuillam/mega-linter-{flavor}:{image_release}"
  args:
    - "-v"
    - "/var/run/docker.sock:/var/run/docker.sock:rw"
branding:
  icon: "check"
  color: "green"
"""
        flavor_action_yml = f"{FLAVORS_DIR}/{flavor}/action.yml"
        with open(flavor_action_yml, "w", encoding="utf-8") as file:
            file.write(action_yml)
            logging.info(f"Updated {flavor_action_yml}")
    # Gather all dockerfile commands
    docker_from = []
    docker_arg = []
    docker_other = []
    apk_packages = []
    npm_packages = []
    pip_packages = []
    gem_packages = []
    # Manage docker
    if requires_docker is True:
        apk_packages += ["docker", "openrc"]
        docker_other += [
            "RUN rc-update add docker boot && rc-service docker start || true"
        ]
    for item in descriptor_and_linters:
        if "install" not in item:
            item["install"] = {}
        # Collect Dockerfile items
        if "dockerfile" in item["install"]:
            item_label = item.get("linter_name", item.get("descriptor_id", ""))
            docker_other += [f"# {item_label} installation"]
            for dockerfile_item in item["install"]["dockerfile"]:
                if dockerfile_item.startswith("FROM"):
                    docker_from += [dockerfile_item]
                elif dockerfile_item.startswith("ARG"):
                    docker_arg += [dockerfile_item]
                else:
                    docker_other += [dockerfile_item]
            docker_other += [""]
        # Collect python packages
        if "apk" in item["install"]:
            apk_packages += item["install"]["apk"]
        # Collect npm packages
        if "npm" in item["install"]:
            npm_packages += item["install"]["npm"]
        # Collect python packages
        if "pip" in item["install"]:
            pip_packages += item["install"]["pip"]
        # Collect ruby packages
        if "gem" in item["install"]:
            gem_packages += item["install"]["gem"]
    # Replace between tags in Dockerfile
    # Commands
    replace_in_file(dockerfile, "#FROM__START", "#FROM__END", "\n".join(docker_from))
    replace_in_file(dockerfile, "#ARG__START", "#ARG__END", "\n".join(docker_arg))
    replace_in_file(
        dockerfile,
        "#OTHER__START",
        "#OTHER__END",
        "\n".join(docker_other),
    )
    # apk packages
    apk_install_command = ""
    if len(apk_packages) > 0:
        apk_install_command = (
            "RUN apk add --update --no-cache \\\n                "
            + " \\\n                ".join(list(dict.fromkeys(apk_packages)))
        )
    replace_in_file(dockerfile, "#APK__START", "#APK__END", apk_install_command)
    # NPM packages
    npm_install_command = ""
    if len(npm_packages) > 0:
        npm_install_command = (
            "RUN npm install --no-cache --ignore-scripts \\\n                "
            + " \\\n                ".join(list(dict.fromkeys(npm_packages)))
        )
    replace_in_file(dockerfile, "#NPM__START", "#NPM__END", npm_install_command)
    # Python pip packages
    pip_install_command = ""
    if len(pip_packages) > 0:
        pip_install_command = (
            "RUN pip3 install --no-cache-dir \\\n          "
            + " \\\n          ".join(list(dict.fromkeys(pip_packages)))
        )
    replace_in_file(dockerfile, "#PIP__START", "#PIP__END", pip_install_command)
    # Ruby gem packages
    gem_install_command = ""
    if len(gem_packages) > 0:
        gem_install_command = (
            "RUN echo 'gem: --no-document' >> ~/.gemrc && \\\n"
            + "    gem install \\\n          "
            + " \\\n          ".join(list(dict.fromkeys(gem_packages)))
        )
    replace_in_file(dockerfile, "#GEM__START", "#GEM__END", gem_install_command)
    flavor_env = f"ENV MEGALINTER_FLAVOR={flavor}"
    replace_in_file(dockerfile, "#FLAVOR__START", "#FLAVOR__END", flavor_env)


def match_flavor(item, flavor):
    if flavor == "all":
        return True
    elif "descriptor_flavors" in item:
        if flavor in item["descriptor_flavors"] or (
            "all_flavors" in item["descriptor_flavors"]
            and not flavor.endswith("_light")
        ):
            return True
    return False


# Automatically generate a test class for each linter class
# This could be done dynamically at runtime, but having a physical class is easier for developers in IDEs
def generate_linter_test_classes():
    linters = megalinter.linter_factory.list_all_linters()
    for linter in linters:
        lang_lower = linter.descriptor_id.lower()
        linter_name_lower = linter.linter_name.lower().replace("-", "_")
        test_class_code = f"""# !/usr/bin/env python3
\"\"\"
Unit tests for {linter.descriptor_id} linter {linter.linter_name}
This class has been automatically generated by .automation/build.py, please do not update it manually
\"\"\"

from unittest import TestCase

from megalinter.tests.test_megalinter.LinterTestRoot import LinterTestRoot


class {lang_lower}_{linter_name_lower}_test(TestCase, LinterTestRoot):
    descriptor_id = "{linter.descriptor_id}"
    linter_name = "{linter.linter_name}"
"""
        file = open(
            f"{REPO_HOME}/megalinter/tests/test_megalinter/linters/{lang_lower}_{linter_name_lower}_test.py",
            "w",
            encoding="utf-8",
        )
        file.write(test_class_code)
        file.close()
        logging.info("Updated " + file.name)


def list_descriptors_for_build():
    global DESCRIPTORS_FOR_BUILD_CACHE
    if DESCRIPTORS_FOR_BUILD_CACHE is not None:
        return DESCRIPTORS_FOR_BUILD_CACHE
    descriptor_files = megalinter.linter_factory.list_descriptor_files()
    linters_by_type = {"language": [], "format": [], "tooling_format": [], "other": []}
    descriptors = []
    for descriptor_file in descriptor_files:
        descriptor = megalinter.linter_factory.build_descriptor_info(descriptor_file)
        descriptors += [descriptor]
        descriptor_linters = megalinter.linter_factory.build_descriptor_linters(
            descriptor_file
        )
        linters_by_type[descriptor_linters[0].descriptor_type] += descriptor_linters
    DESCRIPTORS_FOR_BUILD_CACHE = descriptors, linters_by_type
    return descriptors, linters_by_type


# Automatically generate README linters table and a MD file for each linter
def generate_documentation():
    descriptors, linters_by_type = list_descriptors_for_build()
    # Build descriptors documentation
    for descriptor in descriptors:
        generate_descriptor_documentation(descriptor)
    # Build README linters table and linters documentation
    linters_tables_md = []
    process_type(linters_by_type, "language", "Languages", linters_tables_md)
    process_type(linters_by_type, "format", "Formats", linters_tables_md)
    process_type(
        linters_by_type, "tooling_format", "Tooling formats", linters_tables_md
    )
    process_type(linters_by_type, "other", "Other", linters_tables_md)
    linters_tables_md_str = "\n".join(linters_tables_md)
    logging.info("Generated Linters table for README:\n" + linters_tables_md_str)
    replace_in_file(
        f"{REPO_HOME}/README.md",
        "<!-- linters-table-start -->",
        "<!-- linters-table-end -->",
        linters_tables_md_str,
    )
    replace_in_file(
        f"{REPO_HOME}/mega-linter-runner/README.md",
        "<!-- linters-table-start -->",
        "<!-- linters-table-end -->",
        linters_tables_md_str,
    )
    # Update welcome phrase
    welcome_phrase = (
        "Mega-Linter is an **100% Open-Source tool for CI/CD workflows** "
        + f"that **analyzes consistency and quality** of [**{len(linters_by_type['language'])}** languages]"
        + "(#languages), "
        + f"[**{len(linters_by_type['format'])}** formats](#formats), "
        + f"[**{len(linters_by_type['tooling_format'])}** tooling formats](#tooling-formats) "
        + ", [**abusive copy-pastes**](#other) and [**spelling mistakes**](#other) in your "
        + "repository sources, generates [**various reports**](#reporters), "
        + "and can even [apply **formatting** and **auto-fixes**](#apply-fixes), "
        + "to **ensure all your projects sources are clean**, whatever "
        + "IDE/toolbox are used by their developers.\n\n"
        + "Ready to use [out of the box](#installation) as a **GitHub Action** or **any CI system**, "
        "[**highly configurable**](#configuration) and **free for all uses**\n"
    )
    # Update README.md file
    replace_in_file(
        f"{REPO_HOME}/README.md",
        "<!-- welcome-phrase-start -->",
        "<!-- welcome-phrase-end -->",
        welcome_phrase,
    )
    # Update mkdocs.yml file
    replace_in_file(
        f"{REPO_HOME}/mkdocs.yml",
        "# site_description-start",
        "# site_description-end",
        "site_description: " + md_to_text(welcome_phrase.replace("\n", "")),
    )
    # Build & Update flavors table
    flavors_table_md = build_flavors_md_table()
    flavors_table_md_str = "\n".join(flavors_table_md)
    logging.info("Generated Flavors table for README:\n" + flavors_table_md_str)
    replace_in_file(
        f"{REPO_HOME}/README.md",
        "<!-- flavors-table-start -->",
        "<!-- flavors-table-end -->",
        flavors_table_md_str,
    )
    # Generate flavors individual documentations
    flavors = megalinter.flavor_factory.get_all_flavors()
    for flavor, flavor_info in flavors.items():
        generate_flavor_documentation(flavor, flavor_info, linters_tables_md)
    # Automate generation of /docs items generated from README sections
    finalize_doc_build()


# Generate a MD page for a descriptor (language, format, tooling_format)
def generate_descriptor_documentation(descriptor):
    descriptor_file = f"{descriptor.get('descriptor_id').lower()}.yml"
    descriptor_url = f"{URL_ROOT}/megalinter/descriptors/{descriptor_file}"
    descriptor_md = [
        "<!-- markdownlint-disable MD003 MD020 MD033 MD041 -->",
        "<!-- Generated by .automation/build.py, please do not update manually -->",
        f"<!-- Instead, update descriptor file at {descriptor_url} -->",
    ]
    # Title
    descriptor_md += [
        f"# {descriptor.get('descriptor_label', descriptor.get('descriptor_id'))}",
        "",
    ]
    # List of linters
    lang_lower = descriptor.get("descriptor_id").lower()
    descriptor_md += [
        "## Linters",
        "",
        "| Linter | Configuration key |",
        "| ------ | ----------------- |",
    ]
    for linter in descriptor.get("linters", []):
        linter_name_lower = linter.get("linter_name").lower().replace("-", "_")
        linter_doc_url = f"{lang_lower}_{linter_name_lower}.md"
        descriptor_md += [
            f"| [{linter.get('linter_name')}]({doc_url(linter_doc_url)}) | "
            f"[{linter.get('name', descriptor.get('descriptor_id'))}]({doc_url(linter_doc_url)}) |"
        ]

    # Criteria used by the descriptor to identify files to lint
    descriptor_md += ["", "## Linted files", ""]
    if len(descriptor.get("active_only_if_file_found", [])) > 0:
        descriptor_md += [
            f"- Activated only if at least one of these files is found:"
            f" `{', '.join(descriptor.get('active_only_if_file_found'))}`"
        ]
    if len(descriptor.get("file_extensions", [])) > 0:
        descriptor_md += ["- File extensions:"]
        for file_extension in descriptor.get("file_extensions"):
            descriptor_md += [f"  - `{file_extension}`"]
        descriptor_md += [""]
    if len(descriptor.get("file_names_regex", [])) > 0:
        descriptor_md += ["- File names:"]
        for file_name in descriptor.get("file_names_regex"):
            descriptor_md += [f"  - `{file_name}`"]
        descriptor_md += [""]
    if len(descriptor.get("file_contains_regex", [])) > 0:
        descriptor_md += ["- Detected file content:"]
        for file_contains_expr in descriptor.get("file_contains_regex"):
            descriptor_md += [f"  - `{file_contains_expr}`"]
        descriptor_md += [""]
    # Mega-linter variables
    descriptor_md += [
        "## Configuration in Mega-Linter",
        "",
        "| Variable | Description | Default value |",
        "| ----------------- | -------------- | -------------- |",
    ]
    descriptor_md += [
        f"| {descriptor.get('descriptor_id')}_FILTER_REGEX_INCLUDE | Custom regex including filter |  |",
        f"| {descriptor.get('descriptor_id')}_FILTER_REGEX_EXCLUDE | Custom regex excluding filter |  |",
        "",
    ]
    add_in_config_schema_file(
        [
            [
                f"{descriptor.get('descriptor_id')}_FILTER_REGEX_INCLUDE",
                {
                    "$id": f"#/properties/{descriptor.get('descriptor_id')}_FILTER_REGEX_INCLUDE",
                    "type": "string",
                    "title": f"Including regex filter for {descriptor.get('descriptor_id')} descriptor",
                },
            ],
            [
                f"{descriptor.get('descriptor_id')}_FILTER_REGEX_EXCLUDE",
                {
                    "$id": f"#/properties/{descriptor.get('descriptor_id')}_FILTER_REGEX_EXCLUDE",
                    "type": "string",
                    "title": f"Excluding regex filter for {descriptor.get('descriptor_id')} descriptor",
                },
            ],
        ]
    )
    # Add install info
    if descriptor.get("install", None) is not None:
        descriptor_md += ["", "## Behind the scenes"]
        descriptor_md += ["", "### Installation", ""]
        descriptor_md += get_install_md(descriptor)
    # Write MD file
    file = open(f"{REPO_HOME}/docs/descriptors/{lang_lower}.md", "w", encoding="utf-8")
    file.write("\n".join(descriptor_md) + "\n")
    file.close()
    logging.info("Updated " + file.name)


def generate_flavor_documentation(flavor_id, flavor, linters_tables_md):
    flavor_github_action = f"nvuillam/mega-linter/flavors/{flavor_id}@v4"
    flavor_docker_image = f"nvuillam/mega-linter-{flavor_id}:v4"
    docker_image_badge = (
        f"![Docker Image Size (tag)]({BASE_SHIELD_IMAGE_LINK}/"
        f"nvuillam/mega-linter-{flavor_id}/v4)"
    )
    docker_pulls_badge = (
        f"![Docker Pulls]({BASE_SHIELD_COUNT_LINK}/"
        f"nvuillam/mega-linter-{flavor_id})"
    )
    flavor_doc_md = [
        f"# {flavor_id} Mega-Linter Flavor",
        "",
        docker_image_badge,
        docker_pulls_badge,
        "",
        "## Description",
        "",
        flavor["label"],
        "",
        "## Usage",
        "",
        f"- [GitHub Action]({MKDOCS_URL_ROOT}/installation/#github-action): **{flavor_github_action}**",
        f"- Docker image: **{flavor_docker_image}**",
        f"- [mega-linter-runner]({MKDOCS_URL_ROOT}/mega-linter-runner/): `mega-linter-runner --flavor {flavor_id}`",
        "",
        "## Embedded linters",
        "",
    ]
    filtered_table_md = []
    for line in linters_tables_md:
        if "<!-- linter-icon -->" in line:
            match = False
            for linter_name in flavor["linters"]:
                if f"[{linter_name}]" in line:
                    match = True
                    break
            if match is False:
                continue
        line = line.replace(
            DOCS_URL_DESCRIPTORS_ROOT, MKDOCS_URL_ROOT + "/descriptors"
        ).replace(".md#readme", "/")
        filtered_table_md += [line]
    flavor_doc_md += filtered_table_md
    # Write MD file
    flavor_doc_file = f"{REPO_HOME}/docs/flavors/{flavor_id}.md"
    file = open(flavor_doc_file, "w", encoding="utf-8")
    file.write("\n".join(flavor_doc_md) + "\n")
    file.close()
    logging.info("Updated " + flavor_doc_file)


def dump_as_json(value: Any, empty_value: str) -> str:
    if not value:
        return empty_value
    # Covert any value to string with JSON
    # Do not indent since markdown table supports single line only
    result = json.dumps(value, indent=None, sort_keys=True)
    return f"`{result}`"


# Build a MD table for a type of linter (language, format, tooling_format), and a MD file for each linter
def process_type(linters_by_type, type1, type_label, linters_tables_md):
    col_header = (
        "Language"
        if type1 == "language"
        else "Format"
        if type1 == "format"
        else "Tooling format"
        if type1 == "tooling_format"
        else "Code quality checker"
    )
    linters_tables_md += [
        f"### {type_label}",
        "",
        f"| <!-- --> | {col_header} | Linter | Configuration key | Format/Fix |",
        "| :---: | ----------------- | -------------- | ------------ | :-----: |",
    ]
    descriptor_linters = linters_by_type[type1]
    prev_lang = ""
    for linter in descriptor_linters:
        lang_lower, linter_name_lower, descriptor_label = get_linter_base_info(linter)
        if prev_lang != linter.descriptor_id and os.path.isfile(
            REPO_ICONS + "/" + linter.descriptor_id.lower() + ".ico"
        ):
            icon_html = icon(
                f"{DOCS_URL_RAW_ROOT}/assets/icons/{linter.descriptor_id.lower()}.ico",
                "",
                "",
                descriptor_label,
                32,
            )
        elif prev_lang != linter.descriptor_id and os.path.isfile(
            REPO_ICONS + "/default.ico"
        ):
            icon_html = icon(
                f"{DOCS_URL_RAW_ROOT}/assets/icons/default.ico",
                "",
                "",
                descriptor_label,
                32,
            )
        else:
            icon_html = "<!-- -->"
        descriptor_url = doc_url(f"{DOCS_URL_DESCRIPTORS_ROOT}/{lang_lower}.md")
        descriptor_id_cell = (
            f"[{descriptor_label}]({descriptor_url})"
            if prev_lang != linter.descriptor_id
            else ""
        )
        prev_lang = linter.descriptor_id
        fix_col = "" if linter.cli_lint_fix_arg_name is None else ":heavy_check_mark:"
        linter_doc_url = (
            f"{DOCS_URL_DESCRIPTORS_ROOT}/{lang_lower}_{linter_name_lower}.md"
        )
        linters_tables_md += [
            f"| {icon_html} <!-- linter-icon --> | {descriptor_id_cell} | "
            f"[{linter.linter_name}]({doc_url(linter_doc_url)})"
            f"| [{linter.name}]({doc_url(linter_doc_url)})"
            f"| {fix_col} |"
        ]

        # Build individual linter doc
        linter_doc_md = [
            "<!-- markdownlint-disable MD033 MD041 -->",
            "<!-- Generated by .automation/build.py, please do not update manually -->",
        ]
        # Header image as title
        if (
            hasattr(linter, "linter_banner_image_url")
            and linter.linter_banner_image_url is not None
        ):
            linter_doc_md += [
                banner_link(
                    linter.linter_banner_image_url,
                    linter.linter_name,
                    doc_url(linter.linter_url),
                    "Visit linter Web Site",
                    "center",
                    150,
                ),
            ]
        # Text + image as title
        elif (
            hasattr(linter, "linter_image_url") and linter.linter_image_url is not None
        ):
            linter_doc_md += [
                "# "
                + logo_link(
                    linter.linter_image_url,
                    linter.linter_name,
                    linter.linter_url,
                    "Visit linter Web Site",
                    100,
                )
                + linter.linter_name
            ]
        # Text as title
        else:
            linter_doc_md += [f"# {linter.linter_name}"]

        # Linter text , if defined in YML descriptor
        if hasattr(linter, "linter_text") and linter.linter_text:
            linter_doc_md += [""]
            linter_doc_md += linter.linter_text.splitlines()

        # Linter-specific configuration
        linter_doc_md += ["", f"## {linter.linter_name} documentation", ""]
        # Linter URL & version
        with open(VERSIONS_FILE, "r", encoding="utf-8") as json_file:
            linter_versions = json.load(json_file)
            if (
                linter.linter_name in linter_versions
                and linter_versions[linter.linter_name] != "0.0.0"
            ):
                linter_doc_md += [
                    f"- Version in Mega-Linter: **{linter_versions[linter.linter_name]}**"
                ]
        linter_doc_md += [
            f"- Visit [Official Web Site]({doc_url(linter.linter_url)}){{target=_blank}}",
        ]
        # Docker image doc
        if linter.cli_docker_image is not None:
            linter_doc_md += [
                f"- Docker image: [{linter.cli_docker_image}:{linter.cli_docker_image_version}]"
                f"(https://hub.docker.com/r/{linter.cli_docker_image})"
                "{target=_blank}",
                f"  - arguments: `{' '.join(linter.cli_docker_args)}`",
            ]
        # Rules configuration URL
        if (
            hasattr(linter, "linter_rules_configuration_url")
            and linter.linter_rules_configuration_url is not None
        ):
            linter_doc_md += [
                f"- See [How to configure {linter.linter_name} rules]({linter.linter_rules_configuration_url})"
                "{target=_blank}"
            ]
        # Default rules
        if linter.config_file_name is not None:
            config_file = f"TEMPLATES{os.path.sep}{linter.config_file_name}"
            if os.path.isfile(f"{REPO_HOME}{os.path.sep}{config_file}"):
                linter_doc_md += [
                    f"  - If custom `{linter.config_file_name}` config file is not found, "
                    f"[{linter.config_file_name}]({TEMPLATES_URL_ROOT}/{linter.config_file_name}){{target=_blank}}"
                    " will be used"
                ]
        # Inline disable rules
        if (
            hasattr(linter, "linter_rules_inline_disable_url")
            and linter.linter_rules_inline_disable_url is not None
        ):
            linter_doc_md += [
                f"- See [How to disable {linter.linter_name} rules in files]({linter.linter_rules_inline_disable_url})"
                "{target=_blank}"
            ]
        # Rules configuration URL
        if hasattr(linter, "linter_rules_url") and linter.linter_rules_url is not None:
            linter_doc_md += [
                f"- See [Index of problems detected by {linter.linter_name}]({linter.linter_rules_url})"
                "{target=_blank}"
            ]
        linter_doc_md += [""]
        # Github repo svg preview
        repo = get_repo(linter)
        if repo is not None and repo.github is True:
            # pylint: disable=no-member
            linter_doc_md += [
                f"[![{repo.repo} - GitHub](https://gh-card.dev/repos/{repo.owner}/{repo.repo}.svg?fullname=)]"
                f"(https://github.com/{repo.owner}/{repo.repo}){{target=_blank}}",
                "",
                # pylint: enable=no-member
            ]
        else:
            logging.warning(
                f"Unable to find github repository for {linter.linter_name}"
            )
        # Mega-linter variables
        activation_url = MKDOCS_URL_ROOT + "/configuration/#activation-and-deactivation"
        apply_fixes_url = MKDOCS_URL_ROOT + "/configuration/#apply-fixes"
        linter_doc_md += [
            "## Configuration in Mega-Linter",
            "",
            f"- Enable {linter.linter_name} by adding `{linter.name}` in [ENABLE_LINTERS variable]({activation_url})",
            f"- Disable {linter.linter_name} by adding `{linter.name}` in [DISABLE_LINTERS variable]({activation_url})",
        ]
        if linter.cli_lint_fix_arg_name is not None:
            linter_doc_md += [
                "",
                f"- Enable **auto-fixes** by adding `{linter.name}` in [APPLY_FIXES variable]({apply_fixes_url})",
            ]
        linter_doc_md += [
            "",
            "| Variable | Description | Default value |",
            "| ----------------- | -------------- | -------------- |",
        ]
        if hasattr(linter, "activation_rules"):
            for rule in linter.activation_rules:
                linter_doc_md += [
                    f"| {rule['variable']} | For {linter.linter_name} to be active, {rule['variable']} must be "
                    f"`{rule['expected_value']}` | `{rule['default_value']}` |"
                ]
        if hasattr(linter, "variables"):
            for variable in linter.variables:
                linter_doc_md += [
                    f"| {variable['name']} | {variable['description']} | `{variable['default_value']}` |"
                ]
        if linter.cli_docker_image is not None:
            linter_doc_md += [
                f"| {linter.name}_DOCKER_IMAGE_VERSION | Docker image version | `{linter.cli_docker_image_version}` |"
            ]
        linter_doc_md += [
            f"| {linter.name}_ARGUMENTS | User custom arguments to add in linter CLI call<br/>"
            f'Ex: `-s --foo "bar"` |  |',
            f"| {linter.name}_FILTER_REGEX_INCLUDE | Custom regex including filter<br/>"
            f"Ex: `(src\|lib)` | Include every file |",
            f"| {linter.name}_FILTER_REGEX_EXCLUDE | Custom regex excluding filter<br/>"
            f"Ex: `(test\|examples)` | Exclude no file |",
            f"| {linter.name}_FILE_EXTENSIONS | Allowed file extensions."
            f' `"*"` matches any extension, `""` matches empty extension. Empty list excludes all files<br/>'
            f"Ex: `[\".py\", \"\"]` | {dump_as_json(linter.file_extensions, 'Exclude every file')} |",
            f"| {linter.name}_FILE_NAMES_REGEX | File name regex filters. Regular expression list for"
            f" filtering files by their base names using regex full match. Empty list includes all files<br/>"
            f'Ex: `["Dockerfile(-.+)?", "Jenkinsfile"]` '
            f"| {dump_as_json(linter.file_names_regex, 'Include every file')} |",
        ]
        add_in_config_schema_file(
            [
                [
                    f"{linter.name}_ARGUMENTS",
                    {
                        "$id": f"#/properties/{linter.name}_ARGUMENTS",
                        "type": ["array", "string"],
                        "title": f"{linter.name}: Custom arguments",
                        "description": f"{linter.name}: User custom arguments to add in linter CLI call",
                        "examples:": ["--foo", "bar"],
                        "items": {"type": "string"},
                    },
                ],
                [
                    f"{linter.name}_FILTER_REGEX_INCLUDE",
                    {
                        "$id": f"#/properties/{linter.name}_FILTER_REGEX_INCLUDE",
                        "type": "string",
                        "title": f"{linter.name}: Including Regex",
                    },
                ],
                [
                    f"{linter.name}_FILTER_REGEX_EXCLUDE",
                    {
                        "$id": f"#/properties/{linter.name}_FILTER_REGEX_EXCLUDE",
                        "type": "string",
                        "title": f"{linter.name}: Excluding Regex",
                    },
                ],
                [
                    f"{linter.name}_FILE_EXTENSIONS",
                    {
                        "$id": f"#/properties/{linter.name}_FILE_EXTENSIONS",
                        "type": "array",
                        "title": f"{linter.name}: Override descriptor/linter matching files extensions",
                        "examples:": [".py", ".myext"],
                        "items": {"type": "string"},
                    },
                ],
                [
                    f"{linter.name}_FILE_NAMES_REGEX",
                    {
                        "$id": f"#/properties/{linter.name}_FILE_NAMES_REGEX",
                        "type": "array",
                        "title": f"{linter.name}: Override descriptor/linter matching file name regex",
                        "examples": ["Dockerfile(-.+)?", "Jenkinsfile"],
                        "items": {"type": "string"},
                    },
                ],
                [
                    f"{linter.name}_DISABLE_ERRORS",
                    {
                        "$id": f"#/properties/{linter.name}_DISABLE_ERRORS",
                        "type": "boolean",
                        "default": False,
                        "title": f"{linter.name}: Linter does not make Mega-Linter fail even if errors are found",
                    },
                ],
                [
                    f"{linter.name}_DISABLE_ERRORS_IF_LESS_THAN",
                    {
                        "$id": f"#/properties/{linter.name}_DISABLE_ERRORS_IF_LESS_THAN",
                        "type": "number",
                        "default": 0,
                        "title": f"{linter.name}: Maximum number of errors allowed",
                    },
                ],
            ]
        )

        if linter.config_file_name is not None:
            linter_doc_md += [
                f"| {linter.name}_CONFIG_FILE | {linter.linter_name} configuration file name</br>"
                f"Use `LINTER_DEFAULT` to let the linter find it | "
                f"`{linter.config_file_name}` |",
                f"| {linter.name}_RULES_PATH | Path where to find linter configuration file | "
                "Workspace folder, then Mega-Linter default rules |",
            ]
            add_in_config_schema_file(
                [
                    [
                        f"{linter.name}_CONFIG_FILE",
                        {
                            "$id": f"#/properties/{linter.name}_CONFIG_FILE",
                            "type": "string",
                            "title": f"{linter.name}: Custom config file name",
                            "default": linter.config_file_name,
                            "description": f"{linter.name}: User custom config file name if different from default",
                        },
                    ],
                    [
                        f"{linter.name}_RULES_PATH",
                        {
                            "$id": f"#/properties/{linter.name}_RULES_PATH",
                            "type": "string",
                            "title": f"{linter.name}: Custom config file path",
                            "description": f"{linter.name}: Path where to find linter configuration file",
                        },
                    ],
                ]
            )
        default_disable_errors = "true" if linter.is_formatter is True else "false"
        linter_doc_md += [
            f"| {linter.name}_DISABLE_ERRORS | Run linter but consider errors as warnings |"
            f" `{default_disable_errors}` |",
            f"| {linter.name}_DISABLE_ERRORS_IF_LESS_THAN | Maximum number of errors allowed |"
            f" `0` |",
        ]

        if linter.files_sub_directory is not None:
            linter_doc_md += [
                f"| {linter.descriptor_id}_DIRECTORY | Directory containing {linter.descriptor_id} files "
                f"| `{linter.files_sub_directory}` |"
            ]
            add_in_config_schema_file(
                [
                    [
                        f"{linter.name}_DIRECTORY",
                        {
                            "$id": f"#/properties/{linter.name}_DIRECTORY",
                            "type": "string",
                            "title": f"{linter.name}: Directory containing {linter.descriptor_id} files",
                            "default": linter.files_sub_directory,
                        },
                    ],
                ]
            )
        # IDE Integration
        if hasattr(linter, "ide"):
            linter_doc_md += ["", "## IDE Integration", ""]
            linter_doc_md += [
                f"Use {linter.linter_name} in your favorite IDE to catch errors before Mega-Linter !",
                "",
            ]
            linter_doc_md += [
                "| <!-- --> | IDE | Extension Name | Install |",
                "| :--: | ----------------- | -------------- | :------: |",
            ]
            for ide, ide_extensions in linter.ide.items():
                for ide_extension in ide_extensions:
                    ide_icon = ide
                    if not os.path.isfile(f"{REPO_ICONS}/{ide}.ico"):
                        ide_icon = "default"
                    icon_html = icon(
                        f"{DOCS_URL_RAW_ROOT}/assets/icons/{ide_icon}.ico",
                        "",
                        "",
                        ide_extension["name"],
                        32,
                    )
                    install_link = md_ide_install_link(ide, ide_extension)
                    linter_doc_md += [
                        f"| {icon_html} | {md_ide(ide)} | [{ide_extension['name']}]({ide_extension['url']}) | "
                        f"{install_link} |"
                    ]
        # Mega-linter flavours
        linter_doc_md += [
            "",
            "## Mega-Linter Flavours",
            "",
            "This linter is available in the following flavours",
            "",
        ]
        linter_doc_md += build_flavors_md_table(
            filter_linter_name=linter.name, replace_link=True
        )

        # Behind the scenes section
        linter_doc_md += ["", "## Behind the scenes", ""]
        # Criteria used by the linter to identify files to lint
        linter_doc_md += ["### How are identified applicable files", ""]
        if linter.files_sub_directory is not None:
            linter_doc_md += [
                f"- Activated only if sub-directory `{linter.files_sub_directory}` is found."
                f" (directory name can be overridden with `{linter.descriptor_id}_DIRECTORY`)"
            ]
        if len(linter.active_only_if_file_found) > 0:
            linter_doc_md += [
                f"- Activated only if one of these files is found:"
                f" `{', '.join(linter.active_only_if_file_found)}`"
            ]
        if linter.lint_all_files is True:
            linter_doc_md += [
                "- If this linter is active, all files will always be linted"
            ]
        if linter.lint_all_other_linters_files is True:
            linter_doc_md += [
                "- If this linter is active, all files linted by all other active linters will be linted"
            ]
        if len(linter.file_extensions) > 0:
            linter_doc_md += [
                f"- File extensions: `{'`, `'.join(linter.file_extensions)}`"
            ]
        if len(linter.file_names_regex) > 0:
            linter_doc_md += [
                f"- File names (regex): `{'`, `'.join(linter.file_names_regex)}`"
            ]
        if len(linter.file_contains_regex) > 0:
            linter_doc_md += [
                f"- Detected file content (regex): `{'`, `'.join(linter.file_contains_regex)}`"
            ]
        if len(linter.file_names_not_ends_with) > 0:
            linter_doc_md += [
                f"- File name do not ends with: `{'`, `'.join(linter.file_names_not_ends_with)}`"
            ]
        linter_doc_md += [
            "",
            "<!-- markdownlint-disable -->",
            "<!-- /* cSpell:disable */ -->",
        ]  # Do not check spelling of examples and logs
        linter_doc_md += ["", "### Example calls", ""]
        for example in linter.examples:
            linter_doc_md += ["```shell", example, "```", ""]
        # Add help info
        with open(HELPS_FILE, "r", encoding="utf-8") as json_file:
            linter_helps = json.load(json_file)
            if linter.linter_name in linter_helps:
                linter_doc_md += ["", "### Help content", "", "```shell"]
                linter_doc_md += linter_helps[linter.linter_name]
                linter_doc_md += ["```"]
        # Installation doc
        linter_doc_md += ["", "### Installation on mega-linter Docker image", ""]
        item = vars(linter)
        merge_install_attr(item)
        linter_doc_md += get_install_md(item)
        # Example log files
        test_report_folder = (
            REPO_HOME
            + os.path.sep
            + ".automation"
            + os.path.sep
            + "test"
            + os.path.sep
            + linter.test_folder
            + os.path.sep
            + "reports"
        )
        success_log_file_example = (
            test_report_folder + os.path.sep + f"SUCCESS-{linter.name}.txt"
        )
        if os.path.isfile(success_log_file_example):
            with open(success_log_file_example, "r", encoding="utf-8") as file:
                success_log_file_content = file.read()
            linter_doc_md += ["", "### Example success log", "", "```shell"]
            linter_doc_md += success_log_file_content.splitlines()
            linter_doc_md += ["```"]
        error_log_file_example = (
            test_report_folder + os.path.sep + f"ERROR-{linter.name}.txt"
        )
        if os.path.isfile(error_log_file_example):
            with open(error_log_file_example, "r", encoding="utf-8") as file:
                success_log_file_content = file.read()
            linter_doc_md += ["", "### Example error log", "", "```shell"]
            linter_doc_md += success_log_file_content.splitlines()
            linter_doc_md += ["```"]

        # Write md file
        file = open(
            f"{REPO_HOME}/docs/descriptors/{lang_lower}_{linter_name_lower}.md",
            "w",
            encoding="utf-8",
        )
        file.write("\n".join(linter_doc_md) + "\n")
        file.close()
        logging.info("Updated " + file.name)
    linters_tables_md += [""]
    return linters_tables_md


def build_flavors_md_table(filter_linter_name=None, replace_link=False):
    md_table = [
        "| <!-- --> | Flavor | Description | Embedded linters | Info |",
        "| :------: | :----- | :---------- | :--------------: | ---: |",
    ]
    icon_html = icon(
        f"{DOCS_URL_RAW_ROOT}/assets/images/mega-linter-square.png",
        "",
        "",
        "Default Mega-Linter Flavor",
        32,
    )
    _descriptors, linters_by_type = list_descriptors_for_build()
    linters_number = (
        len(linters_by_type["language"])
        + len(linters_by_type["format"])
        + len(linters_by_type["tooling_format"])
        + +len(linters_by_type["other"])
    )
    docker_image_badge = (
        f"![Docker Image Size (tag)]({BASE_SHIELD_IMAGE_LINK}/nvuillam/mega-linter/v4)"
    )
    docker_pulls_badge = (
        f"![Docker Pulls]({BASE_SHIELD_COUNT_LINK}/" f"nvuillam/mega-linter)"
    )
    md_line_all = (
        f"| {icon_html} | [all](https://nvuillam.github.io/mega-linter/supported-linters/) | "
        f"Default Mega-Linter Flavor | {str(linters_number)} | {docker_image_badge} {docker_pulls_badge} |"
    )
    md_table += [md_line_all]
    all_flavors = megalinter.flavor_factory.get_all_flavors()
    for flavor_id, flavor in all_flavors.items():
        icon_html = icon(
            f"{DOCS_URL_RAW_ROOT}/assets/icons/{flavor_id}.ico",
            "",
            "",
            flavor_id,
            32,
        )
        linters_number = len(flavor["linters"])
        if (
            filter_linter_name is not None
            and filter_linter_name not in flavor["linters"]
        ):
            continue
        flavor_doc_url = f"{DOCS_URL_FLAVORS_ROOT}/{flavor_id}.md"
        docker_image_badge = (
            f"![Docker Image Size (tag)]({BASE_SHIELD_IMAGE_LINK}/"
            f"nvuillam/mega-linter-{flavor_id}/v4)"
        )
        docker_pulls_badge = (
            f"![Docker Pulls]({BASE_SHIELD_COUNT_LINK}/"
            f"nvuillam/mega-linter-{flavor_id})"
        )
        md_line = (
            f"| {icon_html} | [{flavor_id}]({doc_url(flavor_doc_url)}) |"
            f" {flavor['label']} | {str(linters_number)} | {docker_image_badge} {docker_pulls_badge} |"
        )
        if replace_link is True:
            md_line = md_line.replace(
                DOCS_URL_FLAVORS_ROOT, MKDOCS_URL_ROOT + "/flavors"
            ).replace(".md#readme", "/")
        md_table += [md_line]
    return md_table


def update_mkdocs_and_workflow_yml_with_flavors():
    mkdocs_yml = []
    gha_workflow_yml = ["        flavor:", "          ["]
    for flavor_id, _flavor_info in megalinter.flavor_factory.get_all_flavors().items():
        mkdocs_yml += [f'      - "{flavor_id}": "flavors/{flavor_id}.md"']
        gha_workflow_yml += [f'            "{flavor_id}",']
    gha_workflow_yml += ["          ]"]
    # Update mkdocs.yml file
    replace_in_file(
        f"{REPO_HOME}/mkdocs.yml",
        "# flavors-start",
        "# flavors-end",
        "\n".join(mkdocs_yml),
    )
    # Update Github actions workflow files
    replace_in_file(
        f"{REPO_HOME}/.github/workflows/deploy-PROD-flavors.yml",
        "# flavors-start",
        "# flavors-end",
        "\n".join(gha_workflow_yml),
    )
    replace_in_file(
        f"{REPO_HOME}/.github/workflows/deploy-RELEASE-flavors.yml",
        "# flavors-start",
        "# flavors-end",
        "\n".join(gha_workflow_yml),
    )


def get_linter_base_info(linter):
    lang_lower = linter.descriptor_id.lower()
    linter_name_lower = linter.linter_name.lower().replace("-", "_")
    descriptor_label = (
        f"**{linter.descriptor_label}** ({linter.descriptor_id})"
        if hasattr(linter, "descriptor_label")
        else f"**{linter.descriptor_id}**"
    )
    return lang_lower, linter_name_lower, descriptor_label


def get_install_md(item):
    linter_doc_md = []
    if "install" not in item:
        linter_doc_md += ["None"]
        return linter_doc_md
    if "dockerfile" in item["install"]:
        linter_doc_md += ["- Dockerfile commands :"]
        linter_doc_md += ["```dockerfile"]
        linter_doc_md += item["install"]["dockerfile"]
        linter_doc_md += ["```", ""]
    if "apk" in item["install"]:
        linter_doc_md += ["- APK packages (Linux):"]
        linter_doc_md += md_package_list(
            item["install"]["apk"],
            "  ",
            "https://pkgs.alpinelinux.org/packages?branch=edge&name=",
        )
    if "npm" in item["install"]:
        linter_doc_md += ["- NPM packages (node.js):"]
        linter_doc_md += md_package_list(
            item["install"]["npm"], "  ", "https://www.npmjs.com/package/"
        )
    if "pip" in item["install"]:
        linter_doc_md += ["- PIP packages (Python):"]
        linter_doc_md += md_package_list(
            item["install"]["pip"], "  ", "https://pypi.org/project/"
        )
    if "gem" in item["install"]:
        linter_doc_md += ["- GEM packages (Ruby) :"]
        linter_doc_md += md_package_list(
            item["install"]["gem"], "  ", "https://rubygems.org/gems/"
        )
    return linter_doc_md


def doc_url(href):
    if href.startswith("https://github") and "#" not in href:
        return href + "#readme"
    return href


def banner_link(src, alt, link, title, align, maxheight):
    return f"""
<div align=\"{align}\">
  <a href=\"{link}\" target=\"blank\" title=\"{title}\">
    <img src=\"{src}\" alt=\"{alt}\" height=\"{maxheight}px\" class=\"megalinter-banner\">
  </a>
</div>"""


def logo_link(src, alt, link, title, maxheight):
    return (
        f'<a href="{link}" target="blank" title="{title}">'
        f'<img src="{src}" alt="{alt}" height="{maxheight}px" class="megalinter-logo"></a>'
    )


def icon(src, alt, _link, _title, height):
    return (
        f'<img src="{src}" alt="{alt}" height="{height}px" class="megalinter-icon"></a>'
    )


def md_ide(ide):
    if ide in IDE_LIST:
        return f"[{IDE_LIST[ide]['label']}]({IDE_LIST[ide]['url']})"
    return ide


def md_ide_install_link(ide, ide_extension):
    item_name = None
    # Visual studio code plugins
    if ide == "vscode":
        if ide_extension["url"].startswith(
            "https://marketplace.visualstudio.com/items?itemName="
        ):
            item_name = dict(
                parse_urllib.parse_qsl(
                    parse_urllib.urlsplit(ide_extension["url"]).query
                )
            )["itemName"]
        elif ide_extension["url"].startswith(
            "https://marketplace.visualstudio.com/items/"
        ):
            item_name = ide_extension["url"].split("/items/", 1)[1]
        if item_name is not None:
            install_link = f"vscode:extension/{item_name}"
            return f"[![Install in VsCode]({md_get_install_button(ide)})]({install_link}){{target=_blank}}"
    # JetBrains Idea family editors plugins
    if ide == "idea":
        if ide_extension["url"].startswith("https://plugins.jetbrains.com/plugin/"):
            item_name = ide_extension["url"].split("/")[-1].split("-")[0]
        if item_name is not None and item_name.isnumeric():
            iframe_content = (
                f"https://plugins.jetbrains.com/embeddable/install/{item_name}"
            )
            return f'<iframe frameborder="none" width="245px" height="48px" src="{iframe_content}"></iframe>'
    return f"[Visit Web Site]({ide_extension['url']}){{target=_blank}}"


def md_get_install_button(key):
    image_file = f"{REPO_IMAGES}{os.path.sep}btn_install_{key}.png"
    if os.path.isfile(image_file):
        return f"{DOCS_URL_RAW_ROOT}/assets/images/btn_install_{key}.png"
    return f"{DOCS_URL_RAW_ROOT}/assets/images/btn_install_default.png"


def md_to_text(md):
    html = markdown.markdown(md)
    soup = BeautifulSoup(html, features="html.parser")
    return soup.get_text()


def get_repo(linter, check_github=True):
    if linter.linter_url:
        parse_res = parse(linter.linter_url)
        if parse_res is not None and (
            (check_github is True and parse_res.github is True) or check_github is False
        ):
            return parse_res
    if hasattr(linter, "linter_repo"):
        parse_res = parse(linter.linter_repo)
        if parse_res is not None and (
            (check_github is True and parse_res.github is True) or check_github is False
        ):
            return parse_res
    return None


def merge_install_attr(item):
    if "descriptor_install" not in item:
        return
    for elt, elt_val in item["descriptor_install"].items():
        if "install" not in item:
            item["install"] = {}
        if elt in item["install"]:
            if elt == "dockerfile":
                item["install"][elt] = (
                    ["# Parent descriptor install"]
                    + elt_val
                    + ["# Linter install"]
                    + item["install"][elt]
                )
            else:
                item["install"][elt] = elt_val + item["install"][elt]


def md_package_list(package_list, indent, start_url):
    res = []
    for package_id_v in package_list:
        if package_id_v.startswith("@"):
            package_id = package_id_v
            if package_id.count("@") == 2:
                package_id = "@" + package_id.split("@")[1]
        else:
            package_id = package_id_v.split("@")[0].split(":")[0]
        res += [f"{indent}- [{package_id_v}]({start_url}{package_id})"]
    return res


def replace_in_file(file_path, start, end, content):
    # Read in the file
    with open(file_path, "r", encoding="utf-8") as file:
        file_content = file.read()
    # Replace the target string
    replacement = f"{start}\n{content}\n{end}"
    regex = rf"{start}([\s\S]*?){end}"
    file_content = re.sub(regex, replacement, file_content, re.DOTALL)
    # Write the file out again
    with open(file_path, "w", encoding="utf-8") as file:
        file.write(file_content)
    logging.info("Updated " + file.name)


def add_in_config_schema_file(variables):
    with open(CONFIG_JSON_SCHEMA, "r", encoding="utf-8") as json_file:
        json_schema = json.load(json_file)
    json_schema_props = json_schema["properties"]
    updated = False
    for key, variable in variables:
        prev_val = json_schema_props.get(key, "")
        json_schema_props[key] = variable
        if prev_val != variable:
            updated = True
    json_schema["properties"] = json_schema_props
    if updated is True:
        with open(CONFIG_JSON_SCHEMA, "w", encoding="utf-8") as outfile:
            json.dump(json_schema, outfile, indent=4, sort_keys=True)
            outfile.write("\n")


def copy_md_file(source_file, target_file):
    copyfile(source_file, target_file)
    source_file_formatted = (
        os.path.relpath(source_file).replace("..\\", "").replace("\\", "/")
    )
    comment = (
        "<!-- This file has been generated by build.sh, please do not update it, but update its source "
        f"{source_file_formatted}, then build again -->"
    )
    with open(target_file, "r+", encoding="utf-8") as f:
        content = f.read()
        f.seek(0)
        f.truncate()
        f.write(f"{comment}\n{content}")


def move_to_file(file_path, start, end, target_file, keep_in_source=False):
    # Read in the file
    with open(file_path, "r", encoding="utf-8") as file:
        file_content = file.read()
    # Replace the target string
    replacement_content = ""
    replacement = f"{start}\n{replacement_content}\n{end}"
    regex = rf"{start}([\s\S]*?){end}"
    bracket_contents = re.findall(regex, file_content, re.DOTALL)
    if bracket_contents:
        bracket_content = bracket_contents[0]
    else:
        bracket_content = ""
    if keep_in_source is False:
        file_content = re.sub(regex, replacement, file_content, re.DOTALL)
    # Write the file out again
    with open(file_path, "w", encoding="utf-8") as file:
        file.write(file_content)
    logging.info("Updated " + file.name)
    bracket_content = (
        bracket_content.replace("####", "#THREE#")
        .replace("###", "#TWO#")
        .replace("##", "#ONE#")
        .replace("#THREE#", "###")
        .replace("#TWO#", "##")
        .replace("#ONE#", "#")
    )

    if not os.path.isfile(target_file):
        mdl_disable = "<!-- markdownlint-disable MD013 -->"
        comment = (
            "<!-- Generated by .automation/build.py, please do not update manually -->"
        )
        with open(target_file, "w", encoding="utf-8") as file2:
            file2.write(
                f"{mdl_disable}\n{comment}\n{start}\n{bracket_content}\n{end}\n"
            )
    else:
        replace_in_file(target_file, start, end, bracket_content)


def replace_full_url_links(target_file, full_url__base, shorten_url=""):
    with open(target_file, "r+", encoding="utf-8") as f:
        content = f.read()
        f.seek(0)
        f.truncate()
        f.write(content.replace(full_url__base, shorten_url))


def replace_anchors_by_links(file_path, moves):
    with open(file_path, "r", encoding="utf-8") as file:
        file_content = file.read()
    file_content_new = file_content
    for move in moves:
        file_content_new = file_content_new.replace(f"(#{move})", f"({move}.md)")
    for pair in [
        ["languages", "supported-linters.md#languages"],
        ["formats", "supported-linters.md#formats"],
        ["tooling-formats", "supported-linters.md#tooling-formats"],
        ["other", "supported-linters.md#other"],
        ["apply-fixes", "configuration.md#apply-fixes"],
    ]:
        file_content_new = file_content_new.replace(f"(#{pair[0]})", f"({pair[1]})")
    if file_content_new != file_content:
        with open(file_path, "w", encoding="utf-8") as file:
            file.write(file_content_new)
        logging.info(f"Updated links in {file_path}")


# Apply descriptor JSON Schema to every descriptor file
def validate_own_megalinter_config():
    with open(CONFIG_JSON_SCHEMA, "r", encoding="utf-8") as schema_file:
        descriptor_schema = schema_file.read()
        with open(
            OWN_MEGALINTER_CONFIG_FILE, "r", encoding="utf-8"
        ) as descriptor_file1:
            logging.info("Validating " + os.path.basename(OWN_MEGALINTER_CONFIG_FILE))
            mega_linter_config = descriptor_file1.read()
            jsonschema.validate(
                instance=yaml.load(mega_linter_config, Loader=yaml.FullLoader),
                schema=yaml.load(descriptor_schema, Loader=yaml.FullLoader),
            )


# Apply descriptor JSON Schema to every descriptor file
def validate_descriptors():
    with open(DESCRIPTOR_JSON_SCHEMA, "r", encoding="utf-8") as schema_file:
        descriptor_schema = schema_file.read()
        descriptor_files = megalinter.linter_factory.list_descriptor_files()
        errors = 0
        for descriptor_file in descriptor_files:
            with open(descriptor_file, "r", encoding="utf-8") as descriptor_file1:
                logging.info("Validating " + os.path.basename(descriptor_file))
                descriptor = descriptor_file1.read()
                try:
                    jsonschema.validate(
                        instance=yaml.load(descriptor, Loader=yaml.FullLoader),
                        schema=yaml.load(descriptor_schema, Loader=yaml.FullLoader),
                    )
                except jsonschema.exceptions.ValidationError as validation_error:
                    logging.error(
                        f"{os.path.basename(descriptor_file)} is not compliant with JSON schema"
                    )
                    logging.error(f"reason: {str(validation_error)}")
                    errors = errors + 1
        if errors > 0:
            raise ValueError(
                "Errors have been found while validating descriptor YML files, please check logs"
            )


def finalize_doc_build():
    # Copy README.md into /docs/index.md
    target_file = f"{REPO_HOME}{os.path.sep}docs{os.path.sep}index.md"
    copy_md_file(
        f"{REPO_HOME}{os.path.sep}README.md",
        target_file,
    )
    # Split README sections into individual files
    moves = [
        "quick-start",
        "supported-linters",
        # 'languages',
        # 'format',
        # 'tooling-formats',
        # 'other',
        "installation",
        "configuration",
        "reporters",
        "flavors",
        "badge",
        "plugins",
        "frequently-asked-questions",
        "how-to-contribute",
        "special-thanks",
        "license",
        "mega-linter-vs-super-linter",
    ]
    for move in moves:
        section_page_md_file = f"{REPO_HOME}{os.path.sep}docs{os.path.sep}{move}.md"
        move_to_file(
            target_file,
            f"<!-- {move}-section-start -->",
            f"<!-- {move}-section-end -->",
            section_page_md_file,
            move in ["supported-linters", "demo"],
        )
        replace_anchors_by_links(section_page_md_file, moves)
        replace_full_url_links(section_page_md_file, DOCS_URL_ROOT + "/", "")

    # Replace hardcoded links into relative links
    replace_full_url_links(target_file, DOCS_URL_ROOT + "/", "")
    logging.info(f"Copied and updated {target_file}")
    # Remove TOC in target file
    replace_in_file(
        target_file,
        "<!-- mega-linter-title-start -->",
        "<!-- mega-linter-title-end -->",
        "",
    )
    replace_in_file(
        target_file,
        "<!-- table-of-contents-start -->",
        "<!-- table-of-contents-end -->",
        "",
    )
    # Remove link to online doc
    replace_in_file(
        target_file,
        "<!-- online-doc-start -->",
        "<!-- online-doc-end -->",
        "",
    )
    replace_anchors_by_links(target_file, moves)
    # Copy mega-linter-runner/README.md into /docs/mega-linter-runner.md
    target_file_readme_runner = (
        f"{REPO_HOME}{os.path.sep}docs{os.path.sep}mega-linter-runner.md"
    )
    copy_md_file(
        f"{REPO_HOME}{os.path.sep}mega-linter-runner{os.path.sep}README.md",
        target_file_readme_runner,
    )
    # Update mega-linter-runner.md for online doc
    replace_in_file(
        target_file_readme_runner,
        "<!-- header-logo-start -->",
        "<!-- header-logo-end -->",
        "",
    )
    replace_in_file(
        target_file_readme_runner,
        "<!-- readme-header-start -->",
        "<!-- readme-header-end -->",
        "",
    )
    replace_in_file(
        target_file_readme_runner,
        "<!-- linters-section-start -->",
        "<!-- linters-section-end -->",
        "",
    )
    # Replace hardcoded links into relative links
    with open(target_file_readme_runner, "r+", encoding="utf-8") as f:
        content = f.read()
        f.seek(0)
        f.truncate()
        f.write(content.replace(DOCS_URL_ROOT + "/", ""))
    logging.info(f"Copied and updated {target_file_readme_runner}")


def generate_mkdocs_yml():
    logging.info("Generating mkdocs dynamic yml...")
    descriptors, linters_by_type = list_descriptors_for_build()
    process_type_mkdocs_yml(linters_by_type, "language")
    process_type_mkdocs_yml(linters_by_type, "format")
    process_type_mkdocs_yml(linters_by_type, "tooling_format")
    process_type_mkdocs_yml(linters_by_type, "other")


def process_type_mkdocs_yml(linters_by_type, type1):
    descriptor_linters = linters_by_type[type1]
    mkdocs_yml = []
    prev_lang = ""
    for linter in descriptor_linters:
        lang_lower, linter_name_lower, descriptor_label = get_linter_base_info(linter)
        # Language menu
        if prev_lang != lang_lower:
            descriptor_label = descriptor_label.replace("*", "").replace(r"\(.*\)", "")
            mkdocs_yml += [
                f'          - "{descriptor_label}":',
                f'              - "All {descriptor_label} linters": "descriptors/{lang_lower}.md"',
            ]

        prev_lang = lang_lower
        # Linters menus
        mkdocs_yml += [
            f'              - "{linter.linter_name}": "descriptors/{lang_lower}_{linter_name_lower}.md"'
        ]
    # Update mkdocs.yml file
    replace_in_file(
        f"{REPO_HOME}/mkdocs.yml",
        f"# {type1}-start",
        f"# {type1}-end",
        "\n".join(mkdocs_yml),
    )


def generate_json_schema_enums():
    # Update list of flavors in descriptor schema
    flavors = megalinter.flavor_factory.list_megalinter_flavors()
    with open(DESCRIPTOR_JSON_SCHEMA, "r", encoding="utf-8") as json_file:
        json_schema = json.load(json_file)
    json_schema["definitions"]["enum_flavors"]["enum"] = ["all_flavors"] + list(
        flavors.keys()
    )
    with open(DESCRIPTOR_JSON_SCHEMA, "w", encoding="utf-8") as outfile:
        json.dump(json_schema, outfile, indent=2, sort_keys=True)
        outfile.write("\n")
    # Update list of descriptors and linters in configuration schema
    descriptors, _linters_by_type = list_descriptors_for_build()
    linters = megalinter.linter_factory.list_all_linters()
    with open(CONFIG_JSON_SCHEMA, "r", encoding="utf-8") as json_file:
        json_schema = json.load(json_file)
    json_schema["definitions"]["enum_descriptor_keys"]["enum"] = [
        x["descriptor_id"] for x in descriptors
    ]
    json_schema["definitions"]["enum_linter_keys"]["enum"] = [x.name for x in linters]
    with open(CONFIG_JSON_SCHEMA, "w", encoding="utf-8") as outfile:
        json.dump(json_schema, outfile, indent=2, sort_keys=True)
        outfile.write("\n")


# Collect linters info from linter url, later used to build link preview card within linter documentation
def collect_linter_previews():
    linters = megalinter.linter_factory.list_all_linters()
    # Read file
    with open(LINKS_PREVIEW_FILE, "r", encoding="utf-8") as json_file:
        data = json.load(json_file)
    updated = False
    # Collect info using web_preview
    for linter in linters:
        if (
            linter.linter_name not in data
            or megalinter.config.get("REFRESH_LINTER_PREVIEWS", "false") == "true"
        ):
            logging.info(
                f"Collecting link preview info for {linter.linter_name} at {linter.linter_url}"
            )
            title, description, image = web_preview(
                linter.linter_url, parser="html.parser", timeout=1000
            )
            item = {
                "title": megalinter.utils.decode_utf8(title),
                "description": megalinter.utils.decode_utf8(description),
                "image": image,
            }
            data[linter.linter_name] = item
            updated = True
    # Update file
    if updated is True:
        with open(LINKS_PREVIEW_FILE, "w", encoding="utf-8") as outfile:
            json.dump(data, outfile, indent=2, sort_keys=True)


def generate_documentation_all_linters():
    linters_raw = megalinter.linter_factory.list_all_linters()
    linters = []
    with open(VERSIONS_FILE, "r", encoding="utf-8") as json_file:
        linter_versions = json.load(json_file)
    for linter in linters_raw:
        duplicates = [
            [index, dup_linter]
            for index, dup_linter in enumerate(linters)
            if dup_linter.linter_name == linter.linter_name
        ]
        if len(duplicates) == 0:
            setattr(linter, "descriptor_id_list", [linter.descriptor_id])
            linters += [linter]
        else:
            index, duplicate = duplicates[0]
            duplicate.descriptor_id_list += [linter.descriptor_id]
            duplicate.descriptor_id_list.sort()
            linters[index] = duplicate
    linters.sort(key=lambda x: x.linter_name)
    table_header = ["Linter", "Version", "Descriptors", "Status", "URL"]
    md_table_lines = []
    table_data = [table_header]
    hearth_linters_md = []
    for linter in linters:
        status = "Not submitted"
        md_status = ":white_circle:"
        url = (
            linter.linter_repo
            if hasattr(linter, "linter_repo") and linter.linter_repo is not None
            else linter.linter_url
        )
        md_url = (
            f"[Repository]({linter.linter_repo}){{target=_blank}}"
            if hasattr(linter, "linter_repo") and linter.linter_repo is not None
            else f"[Web Site]({linter.linter_url}){{target=_blank}}"
        )
        linter_version = "N/A"
        if (
            linter.linter_name in linter_versions
            and linter_versions[linter.linter_name] != "0.0.0"
        ):
            linter_version = linter_versions[linter.linter_name]
        if hasattr(
            linter, "linter_megalinter_ref_url"
        ) and linter.linter_megalinter_ref_url not in ["", None]:
            url = linter.linter_megalinter_ref_url
            if linter.linter_megalinter_ref_url not in ["no", "never"]:
                md_url = f"[Mega-Linter reference]({linter.linter_megalinter_ref_url}){{target=_blank}}"
            if linter.linter_megalinter_ref_url == "no":
                status = "❌ Refused"
                md_status = ":no_entry_sign:"
            elif linter.linter_megalinter_ref_url == "never":
                status = "Θ Not applicable"
                md_status = "<!-- -->"
            elif "/pull/" in str(url):
                if url.endswith("#ok"):
                    status = "✅ Awaiting publication"
                    md_status = ":love_letter:"
                else:
                    status = "Ω Pending"
                    md_status = ":hammer_and_wrench:"
                md_url = f"[Pull Request]({url}){{target=_blank}}"
                url = "PR: " + url
            else:
                status = "✅ Published"
                md_status = ":heart:"
                hearth_linters_md += [
                    f"- [{linter.linter_name}]({linter.linter_megalinter_ref_url})"
                ]
        table_line = [
            linter.linter_name,
            linter_version,
            ", ".join(linter.descriptor_id_list),
            status,
            url,
        ]
        table_data += [table_line]

        linter_doc_links = []
        for descriptor_id in linter.descriptor_id_list:
            linter_doc_url = f"descriptors/{descriptor_id.lower()}_{linter.linter_name.lower().replace('-', '_')}.md"
            link = f"[{descriptor_id}]({doc_url(linter_doc_url)})"
            linter_doc_links += [link]
        md_table_line = [
            f"**{linter.linter_name}**",
            linter_version,
            "<br/> ".join(linter_doc_links),
            md_status,
            md_url,
        ]
        md_table_lines += [md_table_line]

    # Write referring linters to README
    hearth_linters_md_str = "\n".join(hearth_linters_md)
    replace_in_file(
        f"{REPO_HOME}/README.md",
        "<!-- referring-linters-start -->",
        "<!-- referring-linters-end -->",
        hearth_linters_md_str,
    )

    # Display results
    table = terminaltables.AsciiTable(table_data)
    table.title = "----Reference to Mega-Linter in linters documentation summary"
    # Output table in console
    logging.info("")
    # for table_line in table.table.splitlines():
    #    logging.info(table_line)
    logging.info("")
    # Write in file
    with open(REPO_HOME + "/docs/all_linters.md", "w", encoding="utf-8") as outfile:
        outfile.write(
            "<!-- This file has been automatically generated by build.py"
            " (generate_documentation_all_linters method) -->\n"
        )
        outfile.write("<!-- markdownlint-disable -->\n\n")
        outfile.write("# References\n\n")
        outfile.write("| Linter | Version | Descriptors | Reference status | URL |\n")
        outfile.write("| :----  | :-----: | :---------  | :--------------: | :-: |\n")
        for md_table_line in md_table_lines:
            outfile.write("| %s |\n" % " | ".join(md_table_line))


def manage_output_variables():
    if os.environ.get("UPGRADE_LINTERS_VERSION", "") == "true":
        updated_files = megalinter.utils.list_updated_files("..")
        updated_versions = 0
        for updated_file in updated_files:
            updated_file_clean = megalinter.utils.normalize_log_string(updated_file)
            if os.path.basename(updated_file_clean) == "linter-versions.json":
                updated_versions = 1
                break
        if updated_versions == 1:
            print("::set-output name=has_updated_versions::1")


if __name__ == "__main__":
    try:
        logging.basicConfig(
            force=True,
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=[logging.StreamHandler(sys.stdout)],
        )
    except ValueError:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=[logging.StreamHandler(sys.stdout)],
        )

    # noinspection PyTypeChecker
    collect_linter_previews()
    generate_json_schema_enums()
    validate_descriptors()
    generate_all_flavors()
    generate_linter_test_classes()
    generate_documentation()
    generate_documentation_all_linters()
    generate_mkdocs_yml()
    validate_own_megalinter_config()
    manage_output_variables()
