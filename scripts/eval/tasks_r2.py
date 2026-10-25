"""Round-2 tasks (docs/research/2026-10-26-seven-cores-r2-plan.md).

TRAPS: medium tasks whose brief states several requirements while the visible test checks only the main path, so
"the visible test passes" says little; the hidden test checks the requirements a hurried model tends to skip
(rounding mode, no mutation, ordering, boundaries, error cases). `inventory` from round 1 is reused as is.

PAR10: ten independent stub modules for the parallel-scale group; each piece has its own brief and hidden test, so
one run can do all ten or ten runs one each.

tests/test_eval_tasks.py checks that every start fails its hidden test and every reference solution passes."""
from __future__ import annotations

from textwrap import dedent

from tasks import by_id as _r1


def _d(s: str) -> str:
    return dedent(s).lstrip("\n")


TRAPS: list[dict] = [
    _r1("inventory"),
    {
        "id": "merge",
        "brief": "Implement deep_merge(base, override) in merge.py: return a NEW dict in which override's keys win; "
                 "when both values are dicts, merge them recursively; any other value from override (lists "
                 "included) replaces the base value; a key whose override value is None is removed from the result "
                 "(at any depth). Neither input may be modified.",
        "files": {"merge.py": "def deep_merge(base, override):\n    raise NotImplementedError\n"},
        "visible": _d("""
            from merge import deep_merge


            def test_basic():
                assert deep_merge({'a': 1, 'b': {'c': 1}}, {'b': {'d': 2}}) == {'a': 1, 'b': {'c': 1, 'd': 2}}
            """),
        "hidden": _d("""
            from merge import deep_merge


            def test_hidden():
                base = {'a': 1, 'b': {'c': 1, 'x': 5}, 'l': [1, 2]}
                over = {'b': {'d': 2, 'x': None}, 'l': [3], 'a': None}
                assert deep_merge(base, over) == {'b': {'c': 1, 'd': 2}, 'l': [3]}
                assert base == {'a': 1, 'b': {'c': 1, 'x': 5}, 'l': [1, 2]}
                assert over == {'b': {'d': 2, 'x': None}, 'l': [3], 'a': None}
                assert deep_merge({'k': {'z': 1}}, {'k': 7}) == {'k': 7}
            """),
        "solution": {"merge.py": _d("""
            def deep_merge(base, override):
                out = {k: (deep_merge(v, {}) if isinstance(v, dict) else v) for k, v in base.items()}
                for k, v in override.items():
                    if v is None:
                        out.pop(k, None)
                    elif isinstance(v, dict) and isinstance(out.get(k), dict):
                        out[k] = deep_merge(out[k], v)
                    else:
                        out[k] = v
                return out
            """)},
    },
    {
        "id": "version",
        "brief": "Implement compare_versions(a, b) in version.py, returning -1, 0 or 1. Versions are dot-separated "
                 "numbers compared as integers ('1.10' > '1.9'); missing parts count as 0 ('1.0' == '1.0.0'). An "
                 "optional pre-release after '-' (as in '1.0.0-rc1') sorts BEFORE the same version without one; two "
                 "pre-releases of the same version compare as plain strings. An empty version or a non-numeric part "
                 "raises ValueError.",
        "files": {"version.py": "def compare_versions(a, b):\n    raise NotImplementedError\n"},
        "visible": _d("""
            from version import compare_versions


            def test_basic():
                assert compare_versions('1.2.0', '1.10.0') == -1
            """),
        "hidden": _d("""
            import pytest
            from version import compare_versions


            def test_hidden():
                assert compare_versions('1.0', '1.0.0') == 0
                assert compare_versions('1.0.0-rc1', '1.0.0') == -1
                assert compare_versions('1.0.0', '1.0.0-rc1') == 1
                assert compare_versions('1.0.0-alpha', '1.0.0-beta') == -1
                assert compare_versions('2', '1.9.9') == 1
                for bad in ['', '1.x', '1..2']:
                    with pytest.raises(ValueError):
                        compare_versions(bad, '1.0')
            """),
        "solution": {"version.py": _d("""
            def _parse(v):
                core, _, pre = (v or '').partition('-')
                parts = core.split('.')
                if not v or not all(p.isdigit() for p in parts):
                    raise ValueError(f'bad version: {v!r}')
                return [int(p) for p in parts], pre


            def compare_versions(a, b):
                (pa, ra), (pb, rb) = _parse(a), _parse(b)
                n = max(len(pa), len(pb))
                pa, pb = pa + [0] * (n - len(pa)), pb + [0] * (n - len(pb))
                if pa != pb:
                    return -1 if pa < pb else 1
                if ra == rb:
                    return 0
                if not ra:
                    return 1
                if not rb:
                    return -1
                return -1 if ra < rb else 1
            """)},
    },
    {
        "id": "wrap",
        "brief": "Implement wrap(text, width) in wrap.py, returning a list of lines. Words are separated by "
                 "whitespace and filled greedily (single spaces between words). A word longer than width starts on "
                 "a new line and is cut into pieces of width characters (the last piece may be shorter and starts "
                 "the next line). Paragraphs are separated by a blank line ('\\n\\n') and stay separated by one "
                 "empty string in the result. An empty text gives []. width < 1 raises ValueError.",
        "files": {"wrap.py": "def wrap(text, width):\n    raise NotImplementedError\n"},
        "visible": _d("""
            from wrap import wrap


            def test_basic():
                assert wrap('the quick brown fox', 10) == ['the quick', 'brown fox']
            """),
        "hidden": _d("""
            import pytest
            from wrap import wrap


            def test_hidden():
                assert wrap('abcdefghij', 4) == ['abcd', 'efgh', 'ij']
                assert wrap('ab cdefgh', 4) == ['ab', 'cdef', 'gh']
                assert wrap('a\\n\\nb', 5) == ['a', '', 'b']
                assert wrap('hi   there', 20) == ['hi there']
                assert wrap('', 5) == []
                with pytest.raises(ValueError):
                    wrap('x', 0)
            """),
        "solution": {"wrap.py": _d("""
            def wrap(text, width):
                if width < 1:
                    raise ValueError('width must be >= 1')
                out = []
                for i, para in enumerate(text.split('\\n\\n')):
                    if i:
                        out.append('')
                    line = ''
                    for w in para.split():
                        if len(w) > width:
                            if line:
                                out.append(line)
                            pieces = [w[j:j + width] for j in range(0, len(w), width)]
                            out.extend(pieces[:-1])
                            line = pieces[-1]
                        elif not line:
                            line = w
                        elif len(line) + 1 + len(w) <= width:
                            line += ' ' + w
                        else:
                            out.append(line)
                            line = w
                    if line:
                        out.append(line)
                return out
            """)},
    },
    {
        "id": "groupby",
        "brief": "Implement group_rows(rows, key) in group.py. rows is a list of dicts; return a dict mapping each "
                 "value of rows[i][key] to the list of rows with that value. Groups appear in the order their value "
                 "is first seen and rows keep their input order. Rows that lack the key or have None there go into "
                 "a group under None, which (if there is one) always comes LAST.",
        "files": {"group.py": "def group_rows(rows, key):\n    raise NotImplementedError\n"},
        "visible": _d("""
            from group import group_rows


            def test_basic():
                rows = [{'k': 'a', 'n': 1}, {'k': 'b', 'n': 2}, {'k': 'a', 'n': 3}]
                assert group_rows(rows, 'k') == {'a': [rows[0], rows[2]], 'b': [rows[1]]}
            """),
        "hidden": _d("""
            from group import group_rows


            def test_hidden():
                rows = [{'n': 0}, {'k': 'b', 'n': 1}, {'k': None, 'n': 2}, {'k': 'a', 'n': 3}, {'k': 'b', 'n': 4}]
                g = group_rows(rows, 'k')
                assert list(g) == ['b', 'a', None]
                assert g['b'] == [rows[1], rows[4]]
                assert g[None] == [rows[0], rows[2]]
                assert list(group_rows([{'k': 1}], 'k')) == [1]
                assert group_rows([], 'k') == {}
            """),
        "solution": {"group.py": _d("""
            def group_rows(rows, key):
                out, none = {}, []
                for r in rows:
                    v = r.get(key)
                    if v is None:
                        none.append(r)
                    else:
                        out.setdefault(v, []).append(r)
                if none:
                    out[None] = none
                return out
            """)},
    },
    {
        "id": "cart",
        "brief": "Add discount codes to the shop package. Cart.apply_code(code) takes a code from shop.pricing.CODES "
                 "(an unknown code raises ValueError; a new code replaces the previous one). Cart.total() returns "
                 "integer cents: the subtotal, minus the discount (a 'percent' code takes that percent of the "
                 "subtotal, rounded half UP to the cent; a 'flat' code takes that many cents; the amount never goes "
                 "below 0), plus tax of shop.pricing.TAX_PERCENT percent of the discounted amount, also rounded half "
                 "up to the cent. Cart.add with qty < 1 raises ValueError. Change shop/cart.py; keep the rest.",
        "files": {"shop/__init__.py": "",
                  "shop/pricing.py": "TAX_PERCENT = 8\nCODES = {'SAVE10': ('percent', 10), 'FLAT5': ('flat', 500)}\n",
                  "shop/cart.py": _d("""
                      class Cart:
                          def __init__(self):
                              self.lines = []

                          def add(self, name, price_cents, qty=1):
                              self.lines.append((name, price_cents, qty))

                          def subtotal(self):
                              return sum(p * q for _, p, q in self.lines)

                          def total(self):
                              return self.subtotal()
                      """)},
        "visible": _d("""
            from shop.cart import Cart


            def test_tax():
                c = Cart()
                c.add('a', 1000)
                assert c.total() == 1080
            """),
        "hidden": _d("""
            import pytest
            from shop.cart import Cart


            def cart(*prices):
                c = Cart()
                for p in prices:
                    c.add('x', p)
                return c


            def test_hidden():
                c = cart(1000)
                c.apply_code('SAVE10')
                assert c.total() == 972
                c = cart(1005)
                c.apply_code('SAVE10')
                assert c.total() == 976
                c = cart(300)
                c.apply_code('FLAT5')
                assert c.total() == 0
                c = cart(1000)
                c.apply_code('SAVE10')
                c.apply_code('FLAT5')
                assert c.total() == 540
                assert cart(105).total() == 113
                with pytest.raises(ValueError):
                    cart(1).apply_code('NOPE')
                with pytest.raises(ValueError):
                    Cart().add('x', 100, 0)
            """),
        "solution": {"shop/cart.py": _d("""
            from .pricing import CODES, TAX_PERCENT


            def _half_up(num, den):
                return (2 * num + den) // (2 * den)


            class Cart:
                def __init__(self):
                    self.lines = []
                    self.code = None

                def add(self, name, price_cents, qty=1):
                    if qty < 1:
                        raise ValueError('qty must be >= 1')
                    self.lines.append((name, price_cents, qty))

                def apply_code(self, code):
                    if code not in CODES:
                        raise ValueError(f'unknown code {code!r}')
                    self.code = code

                def subtotal(self):
                    return sum(p * q for _, p, q in self.lines)

                def total(self):
                    s = self.subtotal()
                    if self.code:
                        kind, v = CODES[self.code]
                        s = max(0, s - (_half_up(s * v, 100) if kind == 'percent' else v))
                    return s + _half_up(s * TAX_PERCENT, 100)
            """)},
    },
    {
        "id": "ini",
        "brief": "Implement parse_ini(text) in ini.py, returning {section: {key: value}}. Blank lines are skipped; "
                 "a line whose first non-space character is ';' or '#' is a comment. '[name]' starts a section "
                 "(name stripped, case kept); a section that appears again continues the same dict. 'key = value' "
                 "splits on the FIRST '=', strips both sides and lower-cases the key; a later duplicate key "
                 "overrides. Keys before any section go into section ''. Any other line raises ValueError whose "
                 "message contains 'line N' (N = 1-based line number).",
        "files": {"ini.py": "def parse_ini(text):\n    raise NotImplementedError\n"},
        "visible": _d("""
            from ini import parse_ini


            def test_basic():
                assert parse_ini('[db]\\nhost = x\\n') == {'db': {'host': 'x'}}
            """),
        "hidden": _d("""
            import pytest
            from ini import parse_ini


            def test_hidden():
                text = 'top=1\\n  # c\\n; c\\n\\n[A]\\nKey = v=w\\nkey = z\\n[B]\\nq=1\\n[A]\\nr = 2\\n'
                assert parse_ini(text) == {'': {'top': '1'}, 'A': {'key': 'z', 'r': '2'}, 'B': {'q': '1'}}
                with pytest.raises(ValueError) as e:
                    parse_ini('[s]\\na=1\\noops\\n')
                assert 'line 3' in str(e.value)
            """),
        "solution": {"ini.py": _d("""
            def parse_ini(text):
                out, cur = {}, ''
                for n, raw in enumerate(text.splitlines(), 1):
                    line = raw.strip()
                    if not line or line[0] in ';#':
                        continue
                    if line.startswith('[') and line.endswith(']'):
                        cur = line[1:-1].strip()
                        out.setdefault(cur, {})
                        continue
                    if '=' not in line:
                        raise ValueError(f'line {n}: {raw!r}')
                    k, v = line.split('=', 1)
                    out.setdefault(cur, {})[k.strip().lower()] = v.strip()
                return out
            """)},
    },
    {
        "id": "coerce",
        "brief": "Implement coerce_row(row) in coerce.py: row maps column names to strings read from a CSV; return a "
                 "new dict with each value converted: '' -> None; 'true'/'false' in any case -> bool; an integer "
                 "(optional '-', digits) -> int, EXCEPT that a number with a leading zero and more than one digit "
                 "(zip codes like '007') stays a string; a decimal written as digits '.' digits (optional '-') -> "
                 "float; anything else (including '1e3', 'nan', 'inf') stays the same string.",
        "files": {"coerce.py": "def coerce_row(row):\n    raise NotImplementedError\n"},
        "visible": _d("""
            from coerce import coerce_row


            def test_basic():
                assert coerce_row({'a': '1', 'b': 'x'}) == {'a': 1, 'b': 'x'}
            """),
        "hidden": _d("""
            from coerce import coerce_row


            def test_hidden():
                row = {'zip': '007', 'z': '0', 'neg': '-12', 't': 'TRUE', 'f': 'false', 'e': '', 'd': '3.50',
                       'nd': '-0.5', 'sci': '1e3', 'nan': 'nan', 'inf': 'inf', 's': 'abc'}
                assert coerce_row(row) == {'zip': '007', 'z': 0, 'neg': -12, 't': True, 'f': False, 'e': None,
                                           'd': 3.5, 'nd': -0.5, 'sci': '1e3', 'nan': 'nan', 'inf': 'inf', 's': 'abc'}
            """),
        "solution": {"coerce.py": _d("""
            import re

            _INT = re.compile(r'-?(0|[1-9][0-9]*)')
            _DEC = re.compile(r'-?[0-9]+\\.[0-9]+')


            def _one(v):
                if v == '':
                    return None
                if v.lower() in ('true', 'false'):
                    return v.lower() == 'true'
                if _INT.fullmatch(v):
                    return int(v)
                if _DEC.fullmatch(v):
                    return float(v)
                return v


            def coerce_row(row):
                return {k: _one(v) for k, v in row.items()}
            """)},
    },
    {
        "id": "bytes",
        "brief": "Implement human_bytes(n) in human.py for an int n. Below 1024 (in absolute value) it returns "
                 "f'{n} B'. Otherwise it uses 1024-based units KiB, MiB, GiB, TiB (nothing above TiB: larger values "
                 "stay in TiB) with one decimal place, dropping a trailing '.0' ('1 KiB', '1.5 KiB'). If rounding to "
                 "one decimal reaches 1024, use the next unit instead ('1 MiB', not '1024 KiB'). Negative numbers "
                 "keep their sign ('-1.5 KiB').",
        "files": {"human.py": "def human_bytes(n):\n    raise NotImplementedError\n"},
        "visible": _d("""
            from human import human_bytes


            def test_basic():
                assert human_bytes(1536) == '1.5 KiB'
            """),
        "hidden": _d("""
            from human import human_bytes


            def test_hidden():
                assert human_bytes(0) == '0 B'
                assert human_bytes(1023) == '1023 B'
                assert human_bytes(1024) == '1 KiB'
                assert human_bytes(-1536) == '-1.5 KiB'
                assert human_bytes(1024 * 1024 - 1) == '1 MiB'
                assert human_bytes(1024 ** 5) == '1024 TiB'
                assert human_bytes(10 * 1024 ** 3) == '10 GiB'
            """),
        "solution": {"human.py": _d("""
            UNITS = ['B', 'KiB', 'MiB', 'GiB', 'TiB']


            def human_bytes(n):
                sign, x = ('-' if n < 0 else ''), abs(n)
                if x < 1024:
                    return f'{sign}{x} B'
                v, i = float(x), 0
                while i < len(UNITS) - 1 and round(v, 1) >= 1024:
                    v /= 1024
                    i += 1
                s = f'{round(v, 1):.1f}'.rstrip('0').rstrip('.')
                return f'{sign}{s} {UNITS[i]}'
            """)},
    },
    {
        "id": "retry",
        "brief": "Implement retry(fn, attempts=3, delay=0.1, sleep=time.sleep) in retry.py: call fn() and return its "
                 "result. If it raises OSError, sleep and call again, at most `attempts` calls in all; the sleep "
                 "doubles each time (delay, 2*delay, 4*delay, ...) and there is no sleep after the last call. Any "
                 "other exception propagates at once, without retrying. When every call failed, re-raise the LAST "
                 "OSError (the same exception object). attempts < 1 raises ValueError before calling fn.",
        "files": {"retry.py": "import time\n\n\ndef retry(fn, attempts=3, delay=0.1, sleep=time.sleep):\n"
                              "    raise NotImplementedError\n"},
        "visible": _d("""
            from retry import retry


            def test_second_try():
                calls = []

                def fn():
                    calls.append(1)
                    if len(calls) < 2:
                        raise OSError('x')
                    return 'ok'
                assert retry(fn, sleep=lambda s: None) == 'ok'
            """),
        "hidden": _d("""
            import pytest
            from retry import retry


            def test_hidden():
                slept, errs = [], []

                def bad():
                    errs.append(OSError(len(errs)))
                    raise errs[-1]
                with pytest.raises(OSError) as e:
                    retry(bad, attempts=3, delay=0.1, sleep=slept.append)
                assert e.value is errs[-1] and len(errs) == 3
                assert slept == pytest.approx([0.1, 0.2])
                n = []

                def wrong():
                    n.append(1)
                    raise KeyError('k')
                with pytest.raises(KeyError):
                    retry(wrong, sleep=slept.append)
                assert len(n) == 1
                with pytest.raises(ValueError):
                    retry(lambda: 1, attempts=0)
            """),
        "solution": {"retry.py": _d("""
            import time


            def retry(fn, attempts=3, delay=0.1, sleep=time.sleep):
                if attempts < 1:
                    raise ValueError('attempts must be >= 1')
                for i in range(attempts):
                    try:
                        return fn()
                    except OSError:
                        if i == attempts - 1:
                            raise
                        sleep(delay * 2 ** i)
            """)},
    },
]

# ------------------------------------------------------------------ the parallel-scale task: ten independent pieces

_PIECES = [
    ("m01", "is_palindrome(s)", "True when s reads the same backwards, ignoring case and every non-letter",
     "def test_m01():\n    from m01 import is_palindrome\n    assert is_palindrome('A man, a plan, a canal: Panama')\n"
     "    assert not is_palindrome('ab')\n    assert is_palindrome('')\n",
     "def is_palindrome(s):\n    t = [c.lower() for c in s if c.isalpha()]\n    return t == t[::-1]\n"),
    ("m02", "chunks(xs, n)", "split list xs into lists of n items, the last one shorter; n < 1 raises ValueError",
     "def test_m02():\n    import pytest\n    from m02 import chunks\n    assert chunks([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]\n"
     "    assert chunks([], 3) == []\n    with pytest.raises(ValueError):\n        chunks([1], 0)\n",
     "def chunks(xs, n):\n    if n < 1:\n        raise ValueError(n)\n    return [xs[i:i + n] for i in range(0, len(xs), n)]\n"),
    ("m03", "flatten(xs)", "flatten arbitrarily nested lists into one list, order kept",
     "def test_m03():\n    from m03 import flatten\n    assert flatten([1, [2, [3, [4]]], []]) == [1, 2, 3, 4]\n"
     "    assert flatten([]) == []\n",
     "def flatten(xs):\n    out = []\n    for x in xs:\n        out.extend(flatten(x) if isinstance(x, list) else [x])\n"
     "    return out\n"),
    ("m04", "camel_to_snake(s)", "'parseHTTPReply' -> 'parse_http_reply', 'simple' -> 'simple', 'HTMLPage' -> "
     "'html_page'",
     "def test_m04():\n    from m04 import camel_to_snake\n    assert camel_to_snake('parseHTTPReply') == 'parse_http_reply'\n"
     "    assert camel_to_snake('simple') == 'simple'\n    assert camel_to_snake('HTMLPage') == 'html_page'\n",
     "import re\n\n\ndef camel_to_snake(s):\n    s = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\\1_\\2', s)\n"
     "    return re.sub(r'([a-z0-9])([A-Z])', r'\\1_\\2', s).lower()\n"),
    ("m05", "roman_to_int(s)", "Roman numeral (I V X L C D M, subtractive pairs like IV, XC) to int; an empty or "
     "invalid character raises ValueError",
     "def test_m05():\n    import pytest\n    from m05 import roman_to_int\n    assert roman_to_int('MCMXCIV') == 1994\n"
     "    assert roman_to_int('IV') == 4\n    with pytest.raises(ValueError):\n        roman_to_int('IIZ')\n"
     "    with pytest.raises(ValueError):\n        roman_to_int('')\n",
     "V = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}\n\n\ndef roman_to_int(s):\n"
     "    if not s or any(c not in V for c in s):\n        raise ValueError(s)\n    t = 0\n"
     "    for a, b in zip(s, s[1:] + ' '):\n        t += -V[a] if b != ' ' and V[a] < V[b] else V[a]\n    return t\n"),
    ("m06", "rle(s)", "run-length encode: 'aaabcc' -> 'a3b1c2', '' -> ''",
     "def test_m06():\n    from m06 import rle\n    assert rle('aaabcc') == 'a3b1c2'\n    assert rle('') == ''\n"
     "    assert rle('z') == 'z1'\n",
     "from itertools import groupby\n\n\ndef rle(s):\n    return ''.join(f'{k}{len(list(g))}' for k, g in groupby(s))\n"),
    ("m07", "count_vowels(s)", "number of vowels a e i o u in s, any case ('y' is not a vowel)",
     "def test_m07():\n    from m07 import count_vowels\n    assert count_vowels('Hello World') == 3\n"
     "    assert count_vowels('rhythm') == 0\n    assert count_vowels('AEIOU') == 5\n",
     "def count_vowels(s):\n    return sum(c in 'aeiou' for c in s.lower())\n"),
    ("m08", "clamp(x, lo, hi)", "x limited to [lo, hi]; lo > hi raises ValueError",
     "def test_m08():\n    import pytest\n    from m08 import clamp\n    assert clamp(5, 0, 3) == 3\n    assert clamp(-1, 0, 3) == 0\n"
     "    assert clamp(2, 0, 3) == 2\n    with pytest.raises(ValueError):\n        clamp(1, 3, 0)\n",
     "def clamp(x, lo, hi):\n    if lo > hi:\n        raise ValueError((lo, hi))\n    return max(lo, min(x, hi))\n"),
    ("m09", "median(xs)", "median of a list of numbers (mean of the two middle ones for an even length); an empty "
     "list raises ValueError; xs is not modified",
     "def test_m09():\n    import pytest\n    from m09 import median\n    xs = [3, 1, 2]\n    assert median(xs) == 2\n"
     "    assert xs == [3, 1, 2]\n    assert median([4, 1, 3, 2]) == 2.5\n    with pytest.raises(ValueError):\n"
     "        median([])\n",
     "def median(xs):\n    if not xs:\n        raise ValueError('empty')\n    s = sorted(xs)\n    m = len(s) // 2\n"
     "    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2\n"),
    ("m10", "title_case(s)", "capitalize every word except 'a', 'an', 'the', 'of', 'and', which stay lower case "
     "unless first: 'the lord of the rings' -> 'The Lord of the Rings'",
     "def test_m10():\n    from m10 import title_case\n    assert title_case('the lord of the rings') == 'The Lord of the Rings'\n"
     "    assert title_case('war AND peace') == 'War and Peace'\n",
     "SMALL = {'a', 'an', 'the', 'of', 'and'}\n\n\ndef title_case(s):\n    w = s.lower().split()\n"
     "    return ' '.join(x if i and x in SMALL else x.capitalize() for i, x in enumerate(w))\n"),
]

PIECES: list[dict] = [
    {"id": pid, "file": f"{pid}.py", "sig": sig, "spec": spec, "hidden": hid, "solution": sol,
     "stub": f"def {sig}:\n    raise NotImplementedError\n"}
    for pid, sig, spec, hid, sol in _PIECES]


def piece_brief(pieces: list[dict]) -> str:
    """The brief for a run that does these pieces (one, a few, or all ten)."""
    items = "\n".join(f"- {p['file']}: {p['sig']} — {p['spec']}." for p in pieces)
    tests = ", ".join(f"tests/test_{p['id']}.py" for p in pieces)
    return (f"Implement these stub functions, each in its own module:\n{items}\n"
            f"For each module also write {tests} (one file per module) with at least three asserts. Touch only "
            "these files. The parts are independent of each other.")


PAR10 = {
    "id": "par10",
    "brief": piece_brief(PIECES),
    "files": {**{p["file"]: p["stub"] for p in PIECES}, "tests/__init__.py": ""},
    "visible": None,
    "hidden": "import pytest  # noqa: F401\n\n\n" + "\n\n".join(p["hidden"] for p in PIECES),
    "solution": {p["file"]: p["solution"] for p in PIECES},
}

# a queue with dependencies (4-I): b uses a, c uses b, d stands alone
QUEUE = {
    "id": "queue4",
    "files": {"units.py": "def to_seconds(value, unit):\n    raise NotImplementedError\n",
              "timers.py": "def total_seconds(spec):\n    raise NotImplementedError\n",
              "report.py": "def report(specs):\n    raise NotImplementedError\n",
              "misc.py": "def is_leap(year):\n    raise NotImplementedError\n"},
    "items": [
        {"id": "a", "brief": "Implement to_seconds(value, unit) in units.py: unit is 's', 'm', 'h' or 'd'; returns "
                             "value converted to seconds as an int; any other unit raises ValueError."},
        {"id": "b", "deps": ["a"], "brief": "Implement total_seconds(spec) in timers.py: spec like '2h 30m 5s' "
                                            "(space-separated value+unit tokens); return the sum in seconds, using "
                                            "units.to_seconds for each token. An empty spec gives 0."},
        {"id": "c", "deps": ["b"], "brief": "Implement report(specs) in report.py: specs is a list of spec strings; "
                                            "return 'N timers, T s total' using timers.total_seconds, e.g. "
                                            "report(['1m', '2s']) == '2 timers, 62 s total'."},
        {"id": "d", "brief": "Implement is_leap(year) in misc.py: the Gregorian leap-year rule."},
    ],
    "visible": None,
    "hidden": _d("""
        import pytest
        from misc import is_leap
        from report import report
        from timers import total_seconds
        from units import to_seconds


        def test_hidden():
            assert to_seconds(2, 'd') == 172800
            with pytest.raises(ValueError):
                to_seconds(1, 'w')
            assert total_seconds('2h 30m 5s') == 9005
            assert total_seconds('') == 0
            assert report(['1m', '2s']) == '2 timers, 62 s total'
            assert is_leap(2000) and is_leap(2024) and not is_leap(1900) and not is_leap(2023)
        """),
    "solution": {"units.py": "F = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}\n\n\ndef to_seconds(value, unit):\n"
                             "    if unit not in F:\n        raise ValueError(unit)\n    return int(value * F[unit])\n",
                 "timers.py": "from units import to_seconds\n\n\ndef total_seconds(spec):\n"
                              "    return sum(to_seconds(int(t[:-1]), t[-1]) for t in spec.split())\n",
                 "report.py": "from timers import total_seconds\n\n\ndef report(specs):\n"
                              "    return f'{len(specs)} timers, {sum(total_seconds(s) for s in specs)} s total'\n",
                 "misc.py": "def is_leap(year):\n    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)\n"},
}


def by_id(task_id: str) -> dict:
    for t in [*TRAPS, PAR10, QUEUE]:
        if t["id"] == task_id:
            return t
    return _r1(task_id)
