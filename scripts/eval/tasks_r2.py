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

# The first screen (luna low, 2 runs each) got 19/20 of TRAPS right: a brief that lists the rules is easy to follow.
# TRAPS2 puts the trap in the code the change has to fit into: a second copy of the logic, a cache, a helper with
# the wrong rounding, a subclass override, bool being an int, a slice taken before the filter.
TRAPS2: list[dict] = [
    _r1("inventory"),
    {
        "id": "dupparse",
        "brief": "Dates without zero padding, like '2024-3-5', must be accepted wherever this project reads a date: "
                 "dates.parse_date and the command line (cli.main, which returns the weekday name). Months and days "
                 "may have 1 or 2 digits; everything else is still rejected as before.",
        "files": {"dates.py": _d("""
                      import re
                      from datetime import date

                      _RX = re.compile(r'(\\d{4})-(\\d{2})-(\\d{2})')


                      def parse_date(s):
                          m = _RX.fullmatch(s.strip())
                          if not m:
                              raise ValueError(f'bad date: {s!r}')
                          return date(*map(int, m.groups()))
                      """),
                  "cli.py": _d("""
                      import re
                      import sys
                      from datetime import date


                      def _parse(s):
                          m = re.fullmatch(r'(\\d{4})-(\\d{2})-(\\d{2})', s.strip())
                          if not m:
                              raise SystemExit(f'bad date: {s}')
                          return date(*map(int, m.groups()))


                      def main(argv=None):
                          argv = sys.argv[1:] if argv is None else argv
                          return _parse(argv[0]).strftime('%A')
                      """)},
        "visible": _d("""
            from datetime import date

            from dates import parse_date


            def test_unpadded():
                assert parse_date('2024-3-5') == date(2024, 3, 5)
            """),
        "hidden": _d("""
            import pytest
            from datetime import date

            from cli import main
            from dates import parse_date


            def test_hidden():
                assert main(['2024-3-5']) == 'Tuesday'
                assert main(['2024-03-05']) == 'Tuesday'
                assert parse_date('2024-03-05') == date(2024, 3, 5)
                with pytest.raises(ValueError):
                    parse_date('2024-123-5')
                with pytest.raises(SystemExit):
                    main(['24-3-5'])
            """),
        "solution": {"dates.py": _d("""
                         import re
                         from datetime import date

                         _RX = re.compile(r'(\\d{4})-(\\d{1,2})-(\\d{1,2})')


                         def parse_date(s):
                             m = _RX.fullmatch(s.strip())
                             if not m:
                                 raise ValueError(f'bad date: {s!r}')
                             return date(*map(int, m.groups()))
                         """),
                     "cli.py": _d("""
                         import sys

                         from dates import parse_date


                         def _parse(s):
                             try:
                                 return parse_date(s)
                             except ValueError:
                                 raise SystemExit(f'bad date: {s}')


                         def main(argv=None):
                             argv = sys.argv[1:] if argv is None else argv
                             return _parse(argv[0]).strftime('%A')
                         """)},
    },
    {
        "id": "cache",
        "brief": "Add Catalog.set_price(sku, price) to catalog.py: it changes that item's price; an unknown sku "
                 "raises KeyError and a negative price raises ValueError. Everything Catalog reports (get, "
                 "total_value) must reflect the new price.",
        "files": {"catalog.py": _d("""
            class Item:
                def __init__(self, sku, price):
                    self.sku, self.price = sku, price


            class Catalog:
                def __init__(self):
                    self._items = {}
                    self._total = None

                def add(self, item):
                    self._items[item.sku] = item
                    self._total = None

                def get(self, sku):
                    return self._items[sku]

                def total_value(self):
                    if self._total is None:
                        self._total = sum(i.price for i in self._items.values())
                    return self._total
            """)},
        "visible": _d("""
            from catalog import Catalog, Item


            def test_set_price():
                c = Catalog()
                c.add(Item('a', 5))
                c.set_price('a', 7)
                assert c.get('a').price == 7
            """),
        "hidden": _d("""
            import pytest
            from catalog import Catalog, Item


            def test_hidden():
                c = Catalog()
                c.add(Item('a', 5))
                c.add(Item('b', 1))
                assert c.total_value() == 6
                c.set_price('a', 10)
                assert c.total_value() == 11
                with pytest.raises(KeyError):
                    c.set_price('zz', 1)
                with pytest.raises(ValueError):
                    c.set_price('a', -1)
                assert c.total_value() == 11
            """),
        "solution": {"catalog.py": _d("""
            class Item:
                def __init__(self, sku, price):
                    self.sku, self.price = sku, price


            class Catalog:
                def __init__(self):
                    self._items = {}
                    self._total = None

                def add(self, item):
                    self._items[item.sku] = item
                    self._total = None

                def get(self, sku):
                    return self._items[sku]

                def set_price(self, sku, price):
                    item = self._items[sku]
                    if price < 0:
                        raise ValueError('negative price')
                    item.price = price
                    self._total = None

                def total_value(self):
                    if self._total is None:
                        self._total = sum(i.price for i in self._items.values())
                    return self._total
            """)},
    },
    {
        "id": "rounding",
        "brief": "Implement invoice_total(lines) in invoice.py. lines is a list of (qty, unit_price) with qty an int "
                 "and unit_price a decimal string in dollars, e.g. (3, '0.335'). Each line's amount is qty * "
                 "unit_price rounded half UP to whole cents, line by line; the result is the sum in integer cents. "
                 "The project's money helpers are in money.py.",
        "files": {"money.py": _d("""
                      from decimal import ROUND_HALF_EVEN, Decimal


                      def to_cents(amount):
                          \"\"\"A dollar amount (Decimal, str or int) -> integer cents.\"\"\"
                          return int((Decimal(amount) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_EVEN))
                      """),
                  "invoice.py": "def invoice_total(lines):\n    raise NotImplementedError\n"},
        "visible": _d("""
            from invoice import invoice_total


            def test_basic():
                assert invoice_total([(2, '1.50')]) == 300
            """),
        "hidden": _d("""
            from invoice import invoice_total


            def test_hidden():
                assert invoice_total([(1, '0.125')]) == 13
                assert invoice_total([(3, '0.335')]) == 101
                assert invoice_total([(1, '0.105'), (1, '0.105')]) == 22
                assert invoice_total([]) == 0
            """),
        "solution": {"invoice.py": _d("""
            from decimal import ROUND_HALF_UP, Decimal


            def invoice_total(lines):
                return sum(int((q * Decimal(p) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP)) for q, p in lines)
            """)},
    },
    {
        "id": "exporter",
        "brief": "In export.py, a value that contains the separator, a double quote or a newline must be quoted: "
                 "wrap it in double quotes and double every double quote inside ('a,b' -> '\"a,b\"', 'x\"y' -> "
                 "'\"x\"\"y\"'). This applies to every exporter in export.py; other values are written as before.",
        "files": {"export.py": _d("""
            class Exporter:
                sep = ','

                def format_row(self, values):
                    return self.sep.join(str(v) for v in values)

                def export(self, rows):
                    return '\\n'.join(self.format_row(r) for r in rows)


            class CsvExporter(Exporter):
                def format_row(self, values):
                    # CSV writes None as an empty field
                    return self.sep.join('' if v is None else str(v) for v in values)


            class TsvExporter(Exporter):
                sep = '\\t'
            """)},
        "visible": _d("""
            from export import Exporter


            def test_quote():
                assert Exporter().format_row(['a,b', 1]) == '"a,b",1'
            """),
        "hidden": _d("""
            from export import CsvExporter, Exporter, TsvExporter


            def test_hidden():
                assert CsvExporter().format_row(['a,b', None, 'x"y', 2]) == '"a,b",,"x""y",2'
                assert TsvExporter().format_row(['a\\tb', 'c,d']) == '"a\\tb"\\tc,d'
                assert Exporter().format_row(['line\\nbreak', 'ok']) == '"line\\nbreak",ok'
            """),
        "solution": {"export.py": _d("""
            class Exporter:
                sep = ','

                def cell(self, v):
                    s = str(v)
                    if self.sep in s or '"' in s or '\\n' in s:
                        return '"' + s.replace('"', '""') + '"'
                    return s

                def format_row(self, values):
                    return self.sep.join(self.cell(v) for v in values)

                def export(self, rows):
                    return '\\n'.join(self.format_row(r) for r in rows)


            class CsvExporter(Exporter):
                def format_row(self, values):
                    # CSV writes None as an empty field
                    return self.sep.join('' if v is None else self.cell(v) for v in values)


            class TsvExporter(Exporter):
                sep = '\\t'
            """)},
    },
    {
        "id": "tags",
        "brief": "Add Item.remove_tag(t) (removing a tag the item does not have is not an error) and Item.has_tag(t) "
                 "to tags.py. Tag names are case-insensitive: 'Red' and 'red' are the same tag, and tags are stored "
                 "lower-cased (also those given to the constructor). Each item's tags are its own.",
        "files": {"tags.py": _d("""
            class Item:
                def __init__(self, name, tags=[]):
                    self.name = name
                    self.tags = tags

                def add_tag(self, t):
                    if t not in self.tags:
                        self.tags.append(t)
            """)},
        "visible": _d("""
            from tags import Item


            def test_remove():
                i = Item('a')
                i.add_tag('x')
                i.remove_tag('x')
                assert not i.has_tag('x')
            """),
        "hidden": _d("""
            from tags import Item


            def test_hidden():
                a, b = Item('a'), Item('b')
                a.add_tag('Red')
                a.add_tag('red')
                assert a.has_tag('RED') and a.tags == ['red']
                assert not b.has_tag('red') and b.tags == []
                a.remove_tag('nope')
                given = ['X']
                c = Item('c', given)
                c.add_tag('y')
                assert c.has_tag('x') and c.tags == ['x', 'y'] and given == ['X']
            """),
        "solution": {"tags.py": _d("""
            class Item:
                def __init__(self, name, tags=None):
                    self.name = name
                    self.tags = []
                    for t in tags or []:
                        self.add_tag(t)

                def add_tag(self, t):
                    t = t.lower()
                    if t not in self.tags:
                        self.tags.append(t)

                def remove_tag(self, t):
                    if t.lower() in self.tags:
                        self.tags.remove(t.lower())

                def has_tag(self, t):
                    return t.lower() in self.tags
            """)},
    },
    {
        "id": "config",
        "brief": "Extend load() in config.py with a third source, cli (a dict, default None), that wins over "
                 "everything: cli > environment > file > defaults; a cli value of None means 'not given'. Values "
                 "from the environment are strings: convert each to the type of that key's default (bool: "
                 "'true'/'1'/'yes' -> True and 'false'/'0'/'no' -> False, any case; int: int(); anything else stays "
                 "a string). An environment value that cannot be converted raises ValueError naming the variable.",
        "files": {"config.py": _d("""
            DEFAULTS = {'debug': False, 'port': 8080, 'name': 'app'}


            def load(env=None, file_values=None):
                out = dict(DEFAULTS)
                out.update(file_values or {})
                for k in DEFAULTS:
                    v = (env or {}).get('APP_' + k.upper())
                    if v is not None:
                        out[k] = v
                return out
            """)},
        "visible": _d("""
            from config import load


            def test_cli():
                assert load(cli={'port': 1})['port'] == 1
            """),
        "hidden": _d("""
            import pytest
            from config import load


            def test_hidden():
                assert load(env={'APP_DEBUG': 'Yes', 'APP_PORT': '9000'}) == {'debug': True, 'port': 9000, 'name': 'app'}
                assert load(env={'APP_DEBUG': '0'})['debug'] is False
                assert load(env={'APP_PORT': '9000'}, cli={'port': None})['port'] == 9000
                assert load(env={'APP_PORT': '1'}, file_values={'port': 2}, cli={'port': 3})['port'] == 3
                assert load(env={'APP_NAME': '7'})['name'] == '7'
                with pytest.raises(ValueError) as e:
                    load(env={'APP_PORT': 'x'})
                assert 'APP_PORT' in str(e.value)
                with pytest.raises(ValueError):
                    load(env={'APP_DEBUG': 'maybe'})
            """),
        "solution": {"config.py": _d("""
            DEFAULTS = {'debug': False, 'port': 8080, 'name': 'app'}
            TRUE, FALSE = ('true', '1', 'yes'), ('false', '0', 'no')


            def _conv(var, v, default):
                if isinstance(default, bool):
                    if v.lower() in TRUE:
                        return True
                    if v.lower() in FALSE:
                        return False
                    raise ValueError(f'{var}: not a bool: {v!r}')
                if isinstance(default, int):
                    try:
                        return int(v)
                    except ValueError:
                        raise ValueError(f'{var}: not an int: {v!r}')
                return v


            def load(env=None, file_values=None, cli=None):
                out = dict(DEFAULTS)
                out.update(file_values or {})
                for k in DEFAULTS:
                    var = 'APP_' + k.upper()
                    v = (env or {}).get(var)
                    if v is not None:
                        out[k] = _conv(var, v, DEFAULTS[k])
                out.update({k: v for k, v in (cli or {}).items() if v is not None})
                return out
            """)},
    },
    {
        "id": "pagefilter",
        "brief": "Add an optional q argument to list_items in api.py: keep only the items whose name contains q, "
                 "ignoring case. Filtering comes before pagination, 'total' counts the matching items, and the "
                 "result also gets 'pages' (the number of pages for that total, at least 1). q None or '' means no "
                 "filter.",
        "files": {"api.py": _d("""
            ITEMS = [{'id': i, 'name': n} for i, n in
                     enumerate(['Apple', 'Banana', 'Cherry', 'apricot', 'Blueberry', 'Avocado'], 1)]


            def list_items(page=1, size=2, items=None):
                items = ITEMS if items is None else items
                start = (page - 1) * size
                return {'items': items[start:start + size], 'page': page, 'total': len(items)}
            """)},
        "visible": _d("""
            from api import list_items


            def test_filter():
                assert [x['name'] for x in list_items(1, 2, q='ap')['items']] == ['Apple', 'apricot']
            """),
        "hidden": _d("""
            from api import list_items


            def test_hidden():
                r = list_items(2, 2, q='A')
                assert [x['name'] for x in r['items']] == ['apricot', 'Avocado']
                assert (r['total'], r['pages'], r['page']) == (4, 2, 2)
                r = list_items(1, 2, q='zzz')
                assert (r['items'], r['total'], r['pages']) == ([], 0, 1)
                assert list_items(1, 4)['pages'] == 2
                assert list_items(1, 4, q='')['total'] == 6
            """),
        "solution": {"api.py": _d("""
            ITEMS = [{'id': i, 'name': n} for i, n in
                     enumerate(['Apple', 'Banana', 'Cherry', 'apricot', 'Blueberry', 'Avocado'], 1)]


            def list_items(page=1, size=2, items=None, q=None):
                items = ITEMS if items is None else items
                if q:
                    items = [x for x in items if q.lower() in x['name'].lower()]
                start = (page - 1) * size
                return {'items': items[start:start + size], 'page': page, 'total': len(items),
                        'pages': max(1, -(-len(items) // size))}
            """)},
    },
    {
        "id": "rank",
        "brief": "Implement rank(scores) in leader.py: scores maps player name -> points. Return a list of (rank, "
                 "name, points), highest points first; players with equal points share a rank and are ordered by "
                 "name ignoring case, and the next rank skips accordingly (1, 2, 2, 4). An empty dict gives [].",
        "files": {"leader.py": "def rank(scores):\n    raise NotImplementedError\n"},
        "visible": _d("""
            from leader import rank


            def test_basic():
                assert rank({'a': 1, 'b': 3}) == [(1, 'b', 3), (2, 'a', 1)]
            """),
        "hidden": _d("""
            from leader import rank


            def test_hidden():
                got = rank({'Bob': 5, 'al': 5, 'cy': 7, 'dee': 1})
                assert got == [(1, 'cy', 7), (2, 'al', 5), (2, 'Bob', 5), (4, 'dee', 1)]
                assert rank({}) == []
                assert rank({'x': 2, 'y': 2}) == [(1, 'x', 2), (1, 'y', 2)]
            """),
        "solution": {"leader.py": _d("""
            def rank(scores):
                rows = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0].lower()))
                out = []
                for i, (name, pts) in enumerate(rows):
                    r = out[-1][0] if out and out[-1][2] == pts else i + 1
                    out.append((r, name, pts))
                return out
            """)},
    },
]

# The second screen got 16/18 right too; only `inventory` failed (2/2, and 6/6 in round 1). Its shape: one brief
# with three numbered requirements over three files, one of them never touched by the visible test, and a detail in
# what it returns and how it sorts. COMPOUND copies that shape in four other domains.

def _pkg(name: str, models: str, store: str, report: str) -> dict:
    return {f"{name}/__init__.py": "", f"{name}/models.py": _d(models), f"{name}/store.py": _d(store),
            f"{name}/report.py": _d(report)}


COMPOUND: list[dict] = [
    _r1("inventory"),
    {
        "id": "bank",
        "brief": "In the bank package: (1) Bank.withdraw(acct_id, amount) must raise ValueError when amount <= 0 or "
                 "when the balance would go below -limit, leaving the balance unchanged. (2) Add overdrawn(bank) to "
                 "report.py: the account ids whose balance is below 0, sorted by balance + limit ascending (the "
                 "least room left first), ties by id. (3) summary(bank) gets an 'overdrawn' key: the total amount "
                 "overdrawn, i.e. the sum of -balance over those accounts.",
        "files": _pkg("bank", """
            from dataclasses import dataclass


            @dataclass
            class Account:
                id: str
                owner: str
                balance: int
                limit: int = 0
            """, """
            class Bank:
                def __init__(self):
                    self._accts = {}

                def add(self, acct):
                    if acct.id in self._accts:
                        raise KeyError(f'duplicate account: {acct.id}')
                    self._accts[acct.id] = acct

                def get(self, acct_id):
                    return self._accts[acct_id]

                def accounts(self):
                    return list(self._accts.values())

                def withdraw(self, acct_id, amount):
                    a = self._accts[acct_id]
                    a.balance -= amount
                    return a.balance
            """, """
            def summary(bank):
                accts = bank.accounts()
                return {'accounts': len(accts), 'total': sum(a.balance for a in accts)}
            """),
        "visible": _d("""
            from bank.models import Account
            from bank.report import summary
            from bank.store import Bank


            def test_summary():
                b = Bank()
                b.add(Account('a', 'A', 100))
                assert summary(b) == {'accounts': 1, 'total': 100, 'overdrawn': 0}
            """),
        "hidden": _d("""
            import pytest
            from bank.models import Account
            from bank.report import overdrawn, summary
            from bank.store import Bank


            def test_hidden():
                b = Bank()
                for a in [Account('x', 'X', -50, 100), Account('w', 'W', -10, 20), Account('v', 'V', 5, 0),
                          Account('u', 'U', -40, 50)]:
                    b.add(a)
                assert overdrawn(b) == ['u', 'w', 'x']
                assert summary(b)['overdrawn'] == 100
                with pytest.raises(ValueError):
                    b.withdraw('v', 6)
                assert b.get('v').balance == 5
                with pytest.raises(ValueError):
                    b.withdraw('v', 0)
                assert b.withdraw('x', 50) == -100
            """),
        "solution": {"bank/store.py": _d("""
                         class Bank:
                             def __init__(self):
                                 self._accts = {}

                             def add(self, acct):
                                 if acct.id in self._accts:
                                     raise KeyError(f'duplicate account: {acct.id}')
                                 self._accts[acct.id] = acct

                             def get(self, acct_id):
                                 return self._accts[acct_id]

                             def accounts(self):
                                 return list(self._accts.values())

                             def withdraw(self, acct_id, amount):
                                 a = self._accts[acct_id]
                                 if amount <= 0 or a.balance - amount < -a.limit:
                                     raise ValueError('bad withdrawal')
                                 a.balance -= amount
                                 return a.balance
                         """),
                     "bank/report.py": _d("""
                         def overdrawn(bank):
                             low = [a for a in bank.accounts() if a.balance < 0]
                             return [a.id for a in sorted(low, key=lambda a: (a.balance + a.limit, a.id))]


                         def summary(bank):
                             accts = bank.accounts()
                             return {'accounts': len(accts), 'total': sum(a.balance for a in accts),
                                     'overdrawn': sum(-a.balance for a in accts if a.balance < 0)}
                         """)},
    },
    {
        "id": "board",
        "brief": "In the todo package: (1) Board.complete(task_id) must raise KeyError for an unknown id and "
                 "ValueError if the task is already done; it returns how many tasks are still open. (2) Add "
                 "next_up(board, n) to report.py: the ids of the n open tasks to do next, by priority (1 is the "
                 "highest), then by due day (a task without a due day comes after those with one), then by id. "
                 "(3) summary(board, today=0) gets a 'late' key: how many OPEN tasks have a due day before today.",
        "files": _pkg("todo", """
            from dataclasses import dataclass


            @dataclass
            class Task:
                id: str
                title: str
                priority: int
                due: int | None = None
                done: bool = False
            """, """
            class Board:
                def __init__(self):
                    self._tasks = {}

                def add(self, task):
                    self._tasks[task.id] = task

                def get(self, task_id):
                    return self._tasks[task_id]

                def tasks(self):
                    return list(self._tasks.values())

                def complete(self, task_id):
                    self._tasks[task_id].done = True
            """, """
            def summary(board, today=0):
                ts = board.tasks()
                return {'tasks': len(ts), 'open': sum(not t.done for t in ts)}
            """),
        "visible": _d("""
            from todo.models import Task
            from todo.report import summary
            from todo.store import Board


            def test_summary():
                b = Board()
                b.add(Task('a', 'A', 1))
                assert summary(b) == {'tasks': 1, 'open': 1, 'late': 0}
            """),
        "hidden": _d("""
            import pytest
            from todo.models import Task
            from todo.report import next_up, summary
            from todo.store import Board


            def test_hidden():
                b = Board()
                for t in [Task('e', 'E', 2, None), Task('d', 'D', 2, 5), Task('c', 'C', 1, None),
                          Task('b', 'B', 2, 5), Task('a', 'A', 1, 3, True), Task('f', 'F', 3, 1)]:
                    b.add(t)
                assert next_up(b, 4) == ['c', 'b', 'd', 'e']
                assert summary(b, today=4) == {'tasks': 6, 'open': 5, 'late': 1}
                assert b.complete('c') == 4
                with pytest.raises(ValueError):
                    b.complete('c')
                with pytest.raises(KeyError):
                    b.complete('zz')
            """),
        "solution": {"todo/store.py": _d("""
                         class Board:
                             def __init__(self):
                                 self._tasks = {}

                             def add(self, task):
                                 self._tasks[task.id] = task

                             def get(self, task_id):
                                 return self._tasks[task_id]

                             def tasks(self):
                                 return list(self._tasks.values())

                             def complete(self, task_id):
                                 t = self._tasks[task_id]
                                 if t.done:
                                     raise ValueError(f'already done: {task_id}')
                                 t.done = True
                                 return sum(not x.done for x in self._tasks.values())
                         """),
                     "todo/report.py": _d("""
                         def next_up(board, n):
                             open_ = [t for t in board.tasks() if not t.done]
                             key = lambda t: (t.priority, t.due is None, t.due or 0, t.id)  # noqa: E731
                             return [t.id for t in sorted(open_, key=key)[:n]]


                         def summary(board, today=0):
                             ts = board.tasks()
                             return {'tasks': len(ts), 'open': sum(not t.done for t in ts),
                                     'late': sum(not t.done and t.due is not None and t.due < today for t in ts)}
                         """)},
    },
    {
        "id": "fleet",
        "brief": "In the fleet package: (1) Garage.drive(plate, km) must raise ValueError when km <= 0, leaving the "
                 "odometer unchanged; it returns the new odometer reading. (2) Add due_for_service(garage) to "
                 "report.py: the plates of the cars whose km since their last service is at least service_every, "
                 "the most overdue (km past the service point) first, ties by plate. (3) summary(garage) gets a "
                 "'due' key: how many cars are due.",
        "files": _pkg("fleet", """
            from dataclasses import dataclass


            @dataclass
            class Car:
                plate: str
                km: int
                service_every: int
                last_service_km: int = 0
            """, """
            class Garage:
                def __init__(self):
                    self._cars = {}

                def add(self, car):
                    self._cars[car.plate] = car

                def get(self, plate):
                    return self._cars[plate]

                def cars(self):
                    return list(self._cars.values())

                def drive(self, plate, km):
                    self._cars[plate].km += km
            """, """
            def summary(garage):
                cars = garage.cars()
                return {'cars': len(cars), 'km': sum(c.km for c in cars)}
            """),
        "visible": _d("""
            from fleet.models import Car
            from fleet.report import summary
            from fleet.store import Garage


            def test_summary():
                g = Garage()
                g.add(Car('A1', 100, 1000))
                assert summary(g) == {'cars': 1, 'km': 100, 'due': 0}
            """),
        "hidden": _d("""
            import pytest
            from fleet.models import Car
            from fleet.report import due_for_service, summary
            from fleet.store import Garage


            def test_hidden():
                g = Garage()
                for c in [Car('B2', 1500, 1000, 0), Car('A1', 2600, 1000, 1000), Car('C3', 900, 1000, 0),
                          Car('D4', 3000, 1000, 2000)]:
                    g.add(c)
                assert due_for_service(g) == ['A1', 'B2', 'D4']
                assert summary(g)['due'] == 3
                with pytest.raises(ValueError):
                    g.drive('C3', 0)
                assert g.get('C3').km == 900
                assert g.drive('C3', 100) == 1000
                assert due_for_service(g)[-1] == 'D4'
            """),
        "solution": {"fleet/store.py": _d("""
                         class Garage:
                             def __init__(self):
                                 self._cars = {}

                             def add(self, car):
                                 self._cars[car.plate] = car

                             def get(self, plate):
                                 return self._cars[plate]

                             def cars(self):
                                 return list(self._cars.values())

                             def drive(self, plate, km):
                                 if km <= 0:
                                     raise ValueError('km must be > 0')
                                 c = self._cars[plate]
                                 c.km += km
                                 return c.km
                         """),
                     "fleet/report.py": _d("""
                         def _over(c):
                             return c.km - c.last_service_km - c.service_every


                         def due_for_service(garage):
                             due = [c for c in garage.cars() if _over(c) >= 0]
                             return [c.plate for c in sorted(due, key=lambda c: (-_over(c), c.plate))]


                         def summary(garage):
                             cars = garage.cars()
                             return {'cars': len(cars), 'km': sum(c.km for c in cars),
                                     'due': sum(_over(c) >= 0 for c in cars)}
                         """)},
    },
    {
        "id": "courses",
        "brief": "In the school package: (1) School.enroll(code, student) must raise ValueError when the course is "
                 "full or the student is already in it, leaving the course unchanged; it returns the seats left. "
                 "(2) Add nearly_full(school) to report.py: the codes of the courses at least 80% full, the fullest "
                 "(enrolled / capacity) first, ties by code. (3) summary(school) gets a 'seats_left' key: the free "
                 "seats over all courses.",
        "files": _pkg("school", """
            from dataclasses import dataclass, field


            @dataclass
            class Course:
                code: str
                capacity: int
                students: list = field(default_factory=list)
            """, """
            class School:
                def __init__(self):
                    self._courses = {}

                def add(self, course):
                    self._courses[course.code] = course

                def get(self, code):
                    return self._courses[code]

                def courses(self):
                    return list(self._courses.values())

                def enroll(self, code, student):
                    self._courses[code].students.append(student)
            """, """
            def summary(school):
                cs = school.courses()
                return {'courses': len(cs), 'students': sum(len(c.students) for c in cs)}
            """),
        "visible": _d("""
            from school.models import Course
            from school.report import summary
            from school.store import School


            def test_summary():
                s = School()
                s.add(Course('c1', 10, ['ann']))
                assert summary(s) == {'courses': 1, 'students': 1, 'seats_left': 9}
            """),
        "hidden": _d("""
            import pytest
            from school.models import Course
            from school.report import nearly_full, summary
            from school.store import School


            def test_hidden():
                s = School()
                for c in [Course('b', 5, list('pqrs')), Course('a', 10, list('abcdefghi')), Course('c', 4, list('wxyz')),
                          Course('d', 10, list('abcdefg')), Course('e', 2, list('mn'))]:
                    s.add(c)
                assert nearly_full(s) == ['c', 'e', 'a', 'b']
                assert summary(s)['seats_left'] == 5
                with pytest.raises(ValueError):
                    s.enroll('c', 'new')
                with pytest.raises(ValueError):
                    s.enroll('a', 'a')
                assert s.get('a').students == list('abcdefghi')
                assert s.enroll('a', 'zed') == 0
            """),
        "solution": {"school/store.py": _d("""
                         class School:
                             def __init__(self):
                                 self._courses = {}

                             def add(self, course):
                                 self._courses[course.code] = course

                             def get(self, code):
                                 return self._courses[code]

                             def courses(self):
                                 return list(self._courses.values())

                             def enroll(self, code, student):
                                 c = self._courses[code]
                                 if len(c.students) >= c.capacity or student in c.students:
                                     raise ValueError('cannot enroll')
                                 c.students.append(student)
                                 return c.capacity - len(c.students)
                         """),
                     "school/report.py": _d("""
                         def nearly_full(school):
                             full = [c for c in school.courses() if len(c.students) >= 0.8 * c.capacity]
                             return [c.code for c in sorted(full, key=lambda c: (-len(c.students) / c.capacity, c.code))]


                         def summary(school):
                             cs = school.courses()
                             return {'courses': len(cs), 'students': sum(len(c.students) for c in cs),
                                     'seats_left': sum(c.capacity - len(c.students) for c in cs)}
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
    for t in [*TRAPS, *TRAPS2, *COMPOUND, PAR10, QUEUE]:
        if t["id"] == task_id:
            return t
    return _r1(task_id)
