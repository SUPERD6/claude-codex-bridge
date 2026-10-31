"""The fakes' shared call log stays whole when several fake CLIs append at once (`ccx batch` runs pieces in parallel;
#196 lost a line and read an empty one on Windows)."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

FAKES = Path(__file__).resolve().parent / "fakes"
WRITER = """import json, sys
sys.path.insert(0, sys.argv[1])
from fake_log import locked_append
for i in range(int(sys.argv[3])):
    with locked_append(sys.argv[2]) as f:
        f.write(json.dumps({"w": sys.argv[4], "i": i, "pad": "x" * 2000}) + "\\n")
"""


class TestLockedAppend(unittest.TestCase):
    def test_parallel_writers_lose_no_line(self):
        d = Path(tempfile.mkdtemp())
        (d / "w.py").write_text(WRITER, encoding="utf-8")
        log = d / "calls.jsonl"
        procs = [subprocess.Popen([sys.executable, str(d / "w.py"), str(FAKES), str(log), "40", str(k)])
                 for k in range(8)]
        for p in procs:
            self.assertEqual(p.wait(timeout=120), 0)
        rows = [json.loads(ln) for ln in log.read_text(encoding="utf-8").splitlines()]   # no empty or torn line
        self.assertEqual(len(rows), 8 * 40)
        self.assertEqual({(r["w"], r["i"]) for r in rows}, {(str(k), i) for k in range(8) for i in range(40)})


if __name__ == "__main__":
    unittest.main()
