"""What PyPI shows (P1-6, 2026-10-31): README.md is the package's long description, and PyPI resolves no relative
link or image, so every one in README.md is an absolute URL; the metadata a PyPI page lists is there."""
import re
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def relative_targets(text: str) -> list[str]:
    targets = re.findall(r'(?:src|srcset|href)="([^"]+)"', text)
    targets += re.findall(r'\]\(([^)\s]+)\)', text)
    return [t for t in targets if not re.match(r"^([a-z]+:|#)", t)]


class TestPyPIPage(unittest.TestCase):
    def test_readme_links_and_images_are_absolute(self):
        self.assertEqual(relative_targets((ROOT / "README.md").read_text(encoding="utf-8")), [],
                         "PyPI renders README.md without the repository: use https://github.com/SUPERD6/relayline/"
                         "blob/main/<path> for links and https://raw.githubusercontent.com/SUPERD6/relayline/main/"
                         "<path> for images")

    def test_finder_sees_relative_ones(self):
        self.assertEqual(relative_targets('<img src="docs/a.svg"> [x](docs/b.md) [y](#z) [w](https://e.x/)'),
                         ["docs/a.svg", "docs/b.md"])

    def test_metadata_for_the_project_page(self):
        with open(ROOT / "pyproject.toml", "rb") as f:
            project = tomllib.load(f)["project"]
        self.assertEqual((project["name"], project["scripts"]["ccx"], project["readme"]),
                         ("relayline", "ccx.cli:main", "README.md"))
        self.assertEqual(project["license"], "MIT")
        self.assertTrue({"Homepage", "Repository", "Issues"} <= set(project["urls"]))
        py = {c.rsplit(" :: ", 1)[-1] for c in project["classifiers"] if c.startswith("Programming Language :: Python :: 3.")}
        self.assertEqual(py, {"3.11", "3.12", "3.13"})          # what CI runs (tests.yml)


if __name__ == "__main__":
    unittest.main()
