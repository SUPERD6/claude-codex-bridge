- PyPI page ready (P1-6): `pyproject.toml` gains classifiers (Python 3.11–3.13, as CI runs), keywords and project
  URLs; the license is the SPDX string `MIT` with `license-files` (the table form is deprecated in setuptools, which
  now needs >= 77 to build); the data-only folders `ccx.data`, `ccx.ui_static` and `ccx._hubseed.mcp` are listed as
  packages, so the build no longer warns (the wheel's file list is unchanged). README.md, the long description, uses
  absolute links and images, since PyPI resolves no relative path; `tests/test_packaging.py` keeps it that way. CI's
  package job also builds the sdist and runs `twine check --strict`. docs/maintenance.md: how to upload to TestPyPI
  and PyPI, and where the token goes.
