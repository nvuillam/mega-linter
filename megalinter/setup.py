from setuptools import setup

setup(
    name="megalinter",
    version="0.1",
    description="Mega-Linter",
    url="http://github.com/nvuillam/mega-linter",
    author="Lukas Gravley and Nicolas Vuillamy",
    author_email="nicolas.vuillamy@gmail.com",
    license="MIT",
    packages=["megalinter", "megalinter.linters", "megalinter.reporters"],
    install_requires=[
        "gitpython",
        "jsonschema",
        "markdown",
        "pygithub",
        "pytablewriter",
        "pytest-cov",
        "pytest-timeout",
        "pyyaml",
        "requests",
        "terminaltables",
        "webpreview",
        "yq",
        "mkdocs-material",
        "mdx_truly_sane_lists",
        "beautifulsoup4",
        "giturlparse"
    ],
    zip_safe=False,
)
