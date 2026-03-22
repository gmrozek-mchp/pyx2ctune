"""Sphinx configuration for pymcaf documentation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

project = "pymcaf"
copyright = "2024-2026, Microchip Technology, Inc."
author = "Microchip Technology"
release = "0.1.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
html_baseurl = "https://gmrozek-mchp.github.io/pymcaf/"

autodoc_member_order = "bysource"
autodoc_typehints = "description"

napoleon_google_docstyle = True
napoleon_numpy_docstyle = True
napoleon_attr_annotations = True

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "pyx2cscope": ("https://x2cscope.github.io/pyx2cscope/", None),
}

suppress_warnings = ["intersphinx.external"]
