"""What PyPI shows (P1-6, 2026-10-31): README.md is the package's long description, and PyPI resolves no relative
link or image, so every one in README.md is an absolute URL, and the ones into this repository name files that
exist; the metadata a PyPI page lists is there. README.zh.md is not on PyPI and keeps its relative links."""
import re
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLOB = "https://github.com/SUPERD6/relayline/blob/main/"
RAW = "https://raw.githubusercontent.com/SUPERD6/relayline/main/"


def link_targets(text: str) -> list[str]:
    text = re.sub(r"^ {0,3}(```|~~~).*?^ {0,3}\1", "", text, flags=re.S | re.M)   # fenced code: no links there
    text = re.sub(r"`[^`\n]+`", "", text)
    out = re.findall(r"""\b(?:src|href)\s*=\s*["']([^"']+)["']""", text, flags=re.I)
    for srcset in re.findall(r"""\bsrcset\s*=\s*["']([^"']+)["']""", text, flags=re.I):
        out += [c.split()[0] for c in srcset.split(",") if c.strip()]
    out += re.findall(r"\]\(\s*<?([^)\s>]+)", text)                    # [x](target "title"), ![x](<target>)
    out += re.findall(r"^ {0,3}\[[^\]]+\]:\s*<?(\S+?)>?(?:\s|$)", text, flags=re.M)   # [x]: target
    return out


def relative_targets(text: str) -> list[str]:
    return [t for t in link_targets(text) if not re.match(r"^([a-z][a-z0-9+.-]*:|#)", t, flags=re.I)]


class TestPyPIPage(unittest.TestCase):
    def test_readme_links_and_images_are_absolute(self):
        self.assertEqual(relative_targets((ROOT / "README.md").read_text(encoding="utf-8")), [],
                         f"PyPI renders README.md without the repository: use {BLOB}<path> for links and "
                         f"{RAW}<path> for images")

    def test_readme_links_into_the_repository_name_real_files(self):
        missing = []
        for t in link_targets((ROOT / "README.md").read_text(encoding="utf-8")):
            for base in (BLOB, RAW):
                if t.startswith(base):
                    path = t[len(base):].split("#")[0].split("?")[0]
                    if path and not (ROOT / path).exists():
                        missing.append(t)
        self.assertEqual(missing, [])

    def test_finder_sees_relative_ones(self):
        md = ('<img src="docs/a.svg"> <IMG SRC=\'docs/c.svg\'> [x](docs/b.md "t") [y](#z) [w](https://e.x/) '
              '<source srcset="https://e.x/1.svg 1x, docs/d.svg 2x"> [m](mailto:a@example.com)\n'
              '[ref]: docs/e.md\n```\nd[0](x) <img src="docs/code.svg">\n```\n`a[i](j)`\n')
        self.assertEqual(sorted(relative_targets(md)), ["docs/a.svg", "docs/b.md", "docs/c.svg", "docs/d.svg",
                                                         "docs/e.md"])

    def test_metadata_for_the_project_page(self):
        with open(ROOT / "pyproject.toml", "rb") as f:
            project = tomllib.load(f)["project"]
        self.assertEqual((project["name"], project["scripts"]["ccx"], project["readme"]),
                         ("relayline", "ccx.cli:main", "README.md"))
        self.assertEqual(project["license"], "MIT")
        self.assertTrue({"Homepage", "Repository", "Issues"} <= set(project["urls"]))
        py = {c.rsplit(" :: ", 1)[-1] for c in project["classifiers"] if c.startswith("Programming Language :: Python :: 3.")}
        self.assertEqual(py, {"3.11", "3.12", "3.13"})          # what CI runs (.github/workflows/test.yml)


if __name__ == "__main__":
    unittest.main()
