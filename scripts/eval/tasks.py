"""Small, checkable coding tasks for the H11 self-vs-delegate comparison.

Each task is a tiny Python repo: a module with a stub or a bug, a visible test the agent may run, and a hidden
test that only the evaluator runs afterwards (so "passes the visible test" is not the same as "done right").
`solution` is a reference answer: tests/test_eval_tasks.py checks that the start code fails the hidden test
and the solution passes both, so every task is solvable and every check can fail.
"""
from __future__ import annotations

TASKS: list[dict] = [
    {
        "id": "slugify",
        "brief": "Implement slugify(text) in textutil.py: lowercase, turn every run of characters that are not "
                 "a-z or 0-9 into a single '-', and strip '-' from both ends. Example: '  Hello, World! ' -> "
                 "'hello-world'.",
        "files": {"textutil.py": "def slugify(text):\n    raise NotImplementedError\n"},
        "visible": "from textutil import slugify\n\n\ndef test_basic():\n"
                   "    assert slugify('  Hello, World! ') == 'hello-world'\n",
        "hidden": "from textutil import slugify\n\n\ndef test_hidden():\n"
                  "    assert slugify('A--B__c') == 'a-b-c'\n    assert slugify('***') == ''\n"
                  "    assert slugify('x1 y2') == 'x1-y2'\n    assert slugify('Ünïcode ok') == 'n-code-ok'\n",
        "solution": {"textutil.py": "import re\n\n\ndef slugify(text):\n"
                                    "    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')\n"},
    },
    {
        "id": "paginate",
        "brief": "paginate(items, page, size) in pager.py has a bug: pages are 1-based, but it returns the wrong "
                 "slice. Fix it. A page past the end returns []. page < 1 or size < 1 raises ValueError.",
        "files": {"pager.py": "def paginate(items, page, size):\n    start = page * size\n"
                              "    return items[start:start + size]\n"},
        "visible": "from pager import paginate\n\n\ndef test_first_page():\n"
                   "    assert paginate(list(range(10)), 1, 3) == [0, 1, 2]\n",
        "hidden": "import pytest\nfrom pager import paginate\n\n\ndef test_hidden():\n"
                  "    assert paginate(list(range(10)), 4, 3) == [9]\n    assert paginate(list(range(10)), 5, 3) == []\n"
                  "    with pytest.raises(ValueError):\n        paginate([1], 0, 3)\n"
                  "    with pytest.raises(ValueError):\n        paginate([1], 1, 0)\n",
        "solution": {"pager.py": "def paginate(items, page, size):\n    if page < 1 or size < 1:\n"
                                 "        raise ValueError('page and size must be >= 1')\n"
                                 "    start = (page - 1) * size\n    return items[start:start + size]\n"},
    },
    {
        "id": "duration",
        "brief": "Implement parse_duration(s) in duration.py: parse strings like '1h30m', '45s', '2h5s', '1h2m3s' "
                 "into total seconds (int). Units h, m, s, each at most once, in that order. Anything else "
                 "(empty string, unknown unit, wrong order, missing number) raises ValueError.",
        "files": {"duration.py": "def parse_duration(s):\n    raise NotImplementedError\n"},
        "visible": "from duration import parse_duration\n\n\ndef test_basic():\n"
                   "    assert parse_duration('1h30m') == 5400\n",
        "hidden": "import pytest\nfrom duration import parse_duration\n\n\ndef test_hidden():\n"
                  "    assert parse_duration('45s') == 45\n    assert parse_duration('2h5s') == 7205\n"
                  "    assert parse_duration('1h2m3s') == 3723\n"
                  "    for bad in ['', '5x', '3m1h', 'h', '1h1h', '10']:\n"
                  "        with pytest.raises(ValueError):\n            parse_duration(bad)\n",
        "solution": {"duration.py": "import re\n\n_RX = re.compile(r'(?:(\\d+)h)?(?:(\\d+)m)?(?:(\\d+)s)?')\n\n\n"
                                    "def parse_duration(s):\n    m = _RX.fullmatch(s or '')\n"
                                    "    if not s or not m or not any(m.groups()):\n"
                                    "        raise ValueError(f'bad duration: {s!r}')\n"
                                    "    h, mi, se = (int(g or 0) for g in m.groups())\n"
                                    "    return h * 3600 + mi * 60 + se\n"},
    },
    {
        "id": "roman",
        "brief": "Implement roman_to_int(s) in roman.py for valid Roman numerals I..MMMCMXCIX using subtractive "
                 "notation (IV, IX, XL, XC, CD, CM). Raise ValueError for characters that are not Roman digits "
                 "or for an empty string.",
        "files": {"roman.py": "def roman_to_int(s):\n    raise NotImplementedError\n"},
        "visible": "from roman import roman_to_int\n\n\ndef test_basic():\n    assert roman_to_int('XIV') == 14\n",
        "hidden": "import pytest\nfrom roman import roman_to_int\n\n\ndef test_hidden():\n"
                  "    assert roman_to_int('MCMXCIV') == 1994\n    assert roman_to_int('MMMCMXCIX') == 3999\n"
                  "    assert roman_to_int('XL') == 40\n"
                  "    for bad in ['', 'ABC', 'x']:\n        with pytest.raises(ValueError):\n"
                  "            roman_to_int(bad)\n",
        "solution": {"roman.py": "V = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}\n\n\n"
                                 "def roman_to_int(s):\n    if not s or any(c not in V for c in s):\n"
                                 "        raise ValueError(s)\n    total = 0\n"
                                 "    for i, c in enumerate(s):\n"
                                 "        v = V[c]\n"
                                 "        total += -v if i + 1 < len(s) and V[s[i + 1]] > v else v\n"
                                 "    return total\n"},
    },
    {
        "id": "dedupe",
        "brief": "Implement dedupe(items, key=None) in seq.py: return a new list with duplicates removed, keeping "
                 "the first occurrence and the original order. key, if given, maps an item to what counts as "
                 "equal. Items may be unhashable (e.g. dicts) when a key is given.",
        "files": {"seq.py": "def dedupe(items, key=None):\n    raise NotImplementedError\n"},
        "visible": "from seq import dedupe\n\n\ndef test_basic():\n    assert dedupe([3, 1, 3, 2, 1]) == [3, 1, 2]\n",
        "hidden": "from seq import dedupe\n\n\ndef test_hidden():\n"
                  "    rows = [{'id': 1, 'v': 'a'}, {'id': 2}, {'id': 1, 'v': 'b'}]\n"
                  "    assert dedupe(rows, key=lambda r: r['id']) == [{'id': 1, 'v': 'a'}, {'id': 2}]\n"
                  "    assert dedupe(['a', 'A', 'b'], key=str.lower) == ['a', 'b']\n"
                  "    src = [1, 1]\n    out = dedupe(src)\n    assert out == [1] and src == [1, 1]\n"
                  "    assert dedupe([]) == []\n",
        "solution": {"seq.py": "def dedupe(items, key=None):\n    seen, out = set(), []\n    for x in items:\n"
                               "        k = key(x) if key else x\n        if k not in seen:\n"
                               "            seen.add(k)\n            out.append(x)\n    return out\n"},
    },
    {
        "id": "intervals",
        "brief": "merge(intervals) in intervals.py should merge overlapping or touching [start, end] intervals "
                 "and return them sorted, but it gives wrong answers. Fix it without changing its signature; "
                 "do not modify the input list.",
        "files": {"intervals.py": "def merge(intervals):\n    out = []\n    for s, e in intervals:\n"
                                  "        if out and s < out[-1][1]:\n            out[-1][1] = e\n"
                                  "        else:\n            out.append([s, e])\n    return out\n"},
        "visible": "from intervals import merge\n\n\ndef test_basic():\n"
                   "    assert merge([[1, 3], [2, 6], [8, 10]]) == [[1, 6], [8, 10]]\n",
        "hidden": "from intervals import merge\n\n\ndef test_hidden():\n"
                  "    assert merge([[8, 10], [1, 3], [2, 6]]) == [[1, 6], [8, 10]]\n"
                  "    assert merge([[1, 4], [4, 5]]) == [[1, 5]]\n    assert merge([[1, 10], [2, 3]]) == [[1, 10]]\n"
                  "    src = [[2, 3], [1, 2]]\n    merge(src)\n    assert src == [[2, 3], [1, 2]]\n"
                  "    assert merge([]) == []\n",
        "solution": {"intervals.py": "def merge(intervals):\n    out = []\n"
                                     "    for s, e in sorted([list(i) for i in intervals]):\n"
                                     "        if out and s <= out[-1][1]:\n"
                                     "            out[-1][1] = max(out[-1][1], e)\n        else:\n"
                                     "            out.append([s, e])\n    return out\n"},
    },
    {
        "id": "topk",
        "brief": "Implement top_words(text, k) in words.py: count words (runs of letters a-z, case-insensitive), "
                 "return the k most frequent as (word, count) tuples, most frequent first, ties broken "
                 "alphabetically. k larger than the number of distinct words returns all of them.",
        "files": {"words.py": "def top_words(text, k):\n    raise NotImplementedError\n"},
        "visible": "from words import top_words\n\n\ndef test_basic():\n"
                   "    assert top_words('a b a', 1) == [('a', 2)]\n",
        "hidden": "from words import top_words\n\n\ndef test_hidden():\n"
                  "    assert top_words('b a c b a', 2) == [('a', 2), ('b', 2)]\n"
                  "    assert top_words(\"It's IT, it.\", 1) == [('it', 3)]\n"
                  "    assert top_words('x', 5) == [('x', 1)]\n    assert top_words('', 3) == []\n",
        "solution": {"words.py": "import re\nfrom collections import Counter\n\n\ndef top_words(text, k):\n"
                                 "    c = Counter(re.findall(r'[a-z]+', text.lower()))\n"
                                 "    return sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[:k]\n"},
    },
    {
        "id": "cli-json",
        "brief": "report.py prints a summary of numbers given on the command line ('count=3 total=6'). Add a "
                 "--json flag that prints the same data as a JSON object instead: {\"count\": 3, \"total\": 6}. "
                 "Without --json the output must stay exactly as it is now. Keep it standard library only.",
        "files": {"report.py": "import sys\n\n\ndef main(argv):\n    nums = [int(x) for x in argv]\n"
                               "    print(f'count={len(nums)} total={sum(nums)}')\n    return 0\n\n\n"
                               "if __name__ == '__main__':\n    sys.exit(main(sys.argv[1:]))\n"},
        "visible": "from report import main\n\n\ndef test_plain(capsys):\n    main(['1', '2', '3'])\n"
                   "    assert capsys.readouterr().out == 'count=3 total=6\\n'\n",
        "hidden": "import json\nfrom report import main\n\n\ndef test_hidden(capsys):\n"
                  "    main(['--json', '1', '2', '3'])\n"
                  "    assert json.loads(capsys.readouterr().out) == {'count': 3, 'total': 6}\n"
                  "    main(['4', '--json'])\n"
                  "    assert json.loads(capsys.readouterr().out) == {'count': 1, 'total': 4}\n"
                  "    main([])\n    assert capsys.readouterr().out == 'count=0 total=0\\n'\n",
        "solution": {"report.py": "import json\nimport sys\n\n\ndef main(argv):\n"
                                  "    as_json = '--json' in argv\n"
                                  "    nums = [int(x) for x in argv if x != '--json']\n"
                                  "    data = {'count': len(nums), 'total': sum(nums)}\n"
                                  "    if as_json:\n        print(json.dumps(data))\n    else:\n"
                                  "        print(f\"count={data['count']} total={data['total']}\")\n    return 0\n\n\n"
                                  "if __name__ == '__main__':\n    sys.exit(main(sys.argv[1:]))\n"},
    },
]

# Medium tasks (seven-cores A/B): several requirements, more than one file, so doing it yourself takes the lead
# more than a handful of requests.
MEDIUM: list[dict] = [
    {
        "id": "inventory",
        "brief": "In the inventory package: (1) Store.remove_stock(sku, n) must raise ValueError when n < 1 or when "
                 "it would take qty below 0, leaving the stock unchanged. (2) Add low_stock(store) to report.py: "
                 "the SKUs whose qty <= reorder_at, sorted by qty - reorder_at ascending, ties by sku. (3) "
                 "summary(store) gets a 'low' key: how many SKUs are low on stock.",
        "files": {"inventory/__init__.py": "",
                  "inventory/models.py": "from dataclasses import dataclass\n\n\n@dataclass\nclass Item:\n"
                                         "    sku: str\n    name: str\n    qty: int\n    reorder_at: int = 0\n",
                  "inventory/store.py": "class Store:\n    def __init__(self):\n        self._items = {}\n\n"
                                        "    def add(self, item):\n        if item.sku in self._items:\n"
                                        "            raise KeyError(f'duplicate sku: {item.sku}')\n"
                                        "        self._items[item.sku] = item\n\n    def get(self, sku):\n"
                                        "        return self._items[sku]\n\n    def items(self):\n"
                                        "        return list(self._items.values())\n\n"
                                        "    def remove_stock(self, sku, n):\n        item = self._items[sku]\n"
                                        "        item.qty -= n\n        return item.qty\n",
                  "inventory/report.py": "def summary(store):\n    items = store.items()\n"
                                         "    return {'skus': len(items), 'units': sum(i.qty for i in items)}\n"},
        "visible": "from inventory.models import Item\nfrom inventory.report import summary\n"
                   "from inventory.store import Store\n\n\ndef test_summary():\n    s = Store()\n"
                   "    s.add(Item('a', 'A', 5, 1))\n    assert summary(s) == {'skus': 1, 'units': 5, 'low': 0}\n",
        "hidden": "import pytest\nfrom inventory.models import Item\nfrom inventory.report import low_stock, summary\n"
                  "from inventory.store import Store\n\n\ndef test_hidden():\n    s = Store()\n"
                  "    for it in [Item('b', 'B', 2, 5), Item('a', 'A', 0, 3), Item('c', 'C', 9, 1), Item('d', 'D', 3, 3)]:\n"
                  "        s.add(it)\n    assert low_stock(s) == ['a', 'b', 'd']\n    assert summary(s)['low'] == 3\n"
                  "    with pytest.raises(ValueError):\n        s.remove_stock('c', 10)\n"
                  "    assert s.get('c').qty == 9\n    with pytest.raises(ValueError):\n        s.remove_stock('c', 0)\n"
                  "    assert s.remove_stock('c', 9) == 0\n",
        "solution": {"inventory/store.py": "class Store:\n    def __init__(self):\n        self._items = {}\n\n"
                                           "    def add(self, item):\n        if item.sku in self._items:\n"
                                           "            raise KeyError(f'duplicate sku: {item.sku}')\n"
                                           "        self._items[item.sku] = item\n\n    def get(self, sku):\n"
                                           "        return self._items[sku]\n\n    def items(self):\n"
                                           "        return list(self._items.values())\n\n"
                                           "    def remove_stock(self, sku, n):\n        item = self._items[sku]\n"
                                           "        if n < 1 or item.qty - n < 0:\n            raise ValueError(n)\n"
                                           "        item.qty -= n\n        return item.qty\n",
                     "inventory/report.py": "def low_stock(store):\n"
                                            "    low = [i for i in store.items() if i.qty <= i.reorder_at]\n"
                                            "    return [i.sku for i in sorted(low, key=lambda i: (i.qty - i.reorder_at, i.sku))]\n\n\n"
                                            "def summary(store):\n    items = store.items()\n"
                                            "    return {'skus': len(items), 'units': sum(i.qty for i in items),\n"
                                            "            'low': len(low_stock(store))}\n"},
    },
    {
        "id": "csvstats",
        "brief": "Implement column_stats(text) in csvstats.py. text is CSV with a header row (quoted fields may "
                 "contain commas: use the csv module). For every column whose non-empty cells all parse as numbers, "
                 "return {name: {'min': ..., 'max': ..., 'mean': ..., 'count': ...}}: mean rounded to 2 places, "
                 "count = number of non-empty cells. Empty cells are skipped. Leave out columns with any "
                 "non-numeric cell and columns with no non-empty cells.",
        "files": {"csvstats.py": "def column_stats(text):\n    raise NotImplementedError\n"},
        "visible": "from csvstats import column_stats\n\n\ndef test_basic():\n"
                   "    assert column_stats('x\\n1\\n3\\n') == {'x': {'min': 1, 'max': 3, 'mean': 2.0, 'count': 2}}\n",
        "hidden": "from csvstats import column_stats\n\n\ndef test_hidden():\n"
                  "    text = 'name,age,score,city\\n\"Smith, J\",30,1.5,NYC\\nLee,,2.5,LA\\nKim,40,,SF\\n'\n"
                  "    r = column_stats(text)\n    assert set(r) == {'age', 'score'}\n"
                  "    assert r['age'] == {'min': 30, 'max': 40, 'mean': 35.0, 'count': 2}\n"
                  "    assert r['score'] == {'min': 1.5, 'max': 2.5, 'mean': 2.0, 'count': 2}\n"
                  "    assert column_stats('a,b\\n') == {}\n"
                  "    assert column_stats('v\\n1\\n2\\n2\\n')['v']['mean'] == 1.67\n",
        "solution": {"csvstats.py": "import csv\nimport io\n\n\ndef _num(v):\n    try:\n        return int(v)\n"
                                    "    except ValueError:\n        return float(v)\n\n\n"
                                    "def column_stats(text):\n    rows = list(csv.reader(io.StringIO(text)))\n"
                                    "    if not rows:\n        return {}\n    head, body = rows[0], rows[1:]\n"
                                    "    out = {}\n    for i, name in enumerate(head):\n"
                                    "        vals = [r[i].strip() for r in body if i < len(r) and r[i].strip()]\n"
                                    "        if not vals:\n            continue\n        try:\n"
                                    "            nums = [_num(v) for v in vals]\n        except ValueError:\n"
                                    "            continue\n"
                                    "        out[name] = {'min': min(nums), 'max': max(nums),\n"
                                    "                     'mean': round(sum(nums) / len(nums), 2), 'count': len(nums)}\n"
                                    "    return out\n"},
    },
    {
        "id": "lru",
        "brief": "Implement class LRUCache(capacity) in lru.py with get(key, default=None), put(key, value), "
                 "len(cache), `key in cache` and stats() -> {'hits': ..., 'misses': ..., 'evictions': ...}. get of a "
                 "present key is a hit and makes it the most recent; a missing key is a miss and returns default. "
                 "put of an existing key updates it and makes it the most recent without evicting. `in` does not "
                 "count as a use. capacity < 1 raises ValueError.",
        "files": {"lru.py": "class LRUCache:\n    def __init__(self, capacity):\n        raise NotImplementedError\n"},
        "visible": "from lru import LRUCache\n\n\ndef test_basic():\n    c = LRUCache(1)\n    c.put('x', 1)\n"
                   "    assert c.get('x') == 1\n",
        "hidden": "import pytest\nfrom lru import LRUCache\n\n\ndef test_hidden():\n    c = LRUCache(2)\n"
                  "    c.put('a', 1)\n    c.put('b', 2)\n    assert c.get('a') == 1\n    c.put('c', 3)\n"
                  "    assert 'b' not in c and 'a' in c and len(c) == 2\n    assert c.get('b', 'x') == 'x'\n"
                  "    c.put('a', 10)\n    c.put('d', 4)\n    assert 'c' not in c and c.get('a') == 10\n"
                  "    assert c.stats() == {'hits': 2, 'misses': 1, 'evictions': 2}\n"
                  "    with pytest.raises(ValueError):\n        LRUCache(0)\n",
        "solution": {"lru.py": "from collections import OrderedDict\n\n\nclass LRUCache:\n"
                               "    def __init__(self, capacity):\n        if capacity < 1:\n"
                               "            raise ValueError(capacity)\n        self.cap = capacity\n"
                               "        self.d = OrderedDict()\n        self.h = self.m = self.e = 0\n\n"
                               "    def get(self, key, default=None):\n        if key in self.d:\n"
                               "            self.h += 1\n            self.d.move_to_end(key)\n"
                               "            return self.d[key]\n        self.m += 1\n        return default\n\n"
                               "    def put(self, key, value):\n        if key in self.d:\n"
                               "            self.d.move_to_end(key)\n        elif len(self.d) >= self.cap:\n"
                               "            self.d.popitem(last=False)\n            self.e += 1\n"
                               "        self.d[key] = value\n\n    def __len__(self):\n        return len(self.d)\n\n"
                               "    def __contains__(self, key):\n        return key in self.d\n\n"
                               "    def stats(self):\n        return {'hits': self.h, 'misses': self.m, 'evictions': self.e}\n"},
    },
]

# Memory tasks (seven-cores A/B, core 3): the brief leaves out a project convention that the hidden test checks.
# `memory` is the note the "mem" arm has in the project's memory (.ccx/context.md, via `ccx ctx add`); the "nomem"
# arm gets the same repo without it.
MEMORY: list[dict] = [
    {
        "id": "mem-errors",
        "brief": "Implement parse_port(s) in net.py: '8080' -> 8080 (int). Reject anything that is not a whole "
                 "number from 1 to 65535.",
        "memory": "Convention in this repo: functions reject bad input by raising errors.AppError (never ValueError "
                  "or TypeError), and the message starts with the function name, e.g. 'parse_port: ...'.",
        "files": {"errors.py": "class AppError(Exception):\n    pass\n",
                  "net.py": "def parse_port(s):\n    raise NotImplementedError\n"},
        "visible": "from net import parse_port\n\n\ndef test_basic():\n    assert parse_port('80') == 80\n",
        "hidden": "import pytest\nfrom errors import AppError\nfrom net import parse_port\n\n\ndef test_hidden():\n"
                  "    assert parse_port('8080') == 8080\n    for bad in ['0', '70000', 'abc', '', '1.5']:\n"
                  "        with pytest.raises(AppError) as e:\n            parse_port(bad)\n"
                  "        assert str(e.value).startswith('parse_port')\n",
        "solution": {"net.py": "from errors import AppError\n\n\ndef parse_port(s):\n"
                               "    if not s.isdigit() or not 1 <= int(s) <= 65535:\n"
                               "        raise AppError(f'parse_port: bad port {s!r}')\n    return int(s)\n"},
    },
    {
        "id": "mem-money",
        "brief": "Implement total(prices) in cart.py: the total of a list of prices.",
        "memory": "Money in this repo is integer cents everywhere: prices come in as strings like '12.34', and "
                  "functions that return money return an int number of cents (never floats).",
        "files": {"cart.py": "def total(prices):\n    raise NotImplementedError\n"},
        "visible": "from cart import total\n\n\ndef test_empty():\n    assert total([]) == 0\n",
        "hidden": "from cart import total\n\n\ndef test_hidden():\n    t = total(['1.10', '2.20'])\n"
                  "    assert t == 330 and isinstance(t, int)\n    assert total(['0.05'] * 3) == 15\n",
        "solution": {"cart.py": "from decimal import Decimal\n\n\ndef total(prices):\n"
                                "    return int(sum(Decimal(p) * 100 for p in prices))\n"},
    },
    {
        "id": "mem-log",
        "brief": "Implement greet(name) in hello.py returning 'Hello, <name>!'.",
        "memory": "Every public function in this repo logs one INFO line on the logger named 'app' with the message "
                  "'call <function name>' each time it is called.",
        "files": {"hello.py": "def greet(name):\n    raise NotImplementedError\n"},
        "visible": "from hello import greet\n\n\ndef test_basic():\n    assert greet('A') == 'Hello, A!'\n",
        "hidden": "import logging\nfrom hello import greet\n\n\ndef test_hidden(caplog):\n"
                  "    with caplog.at_level(logging.INFO, logger='app'):\n        assert greet('Bo') == 'Hello, Bo!'\n"
                  "    assert any(r.name == 'app' and r.getMessage() == 'call greet' for r in caplog.records)\n",
        "solution": {"hello.py": "import logging\n\nlog = logging.getLogger('app')\n\n\ndef greet(name):\n"
                                 "    log.info('call greet')\n    return f'Hello, {name}!'\n"},
    },
]

# F9: one task with four independent parts, so a sub-agent with built-in sub-agents could fan out.
PARALLEL_TASK = {
    "id": "four-functions",
    "brief": "This repo has four independent stub modules: a.py (is_palindrome(s): ignore case and non-letters), "
             "b.py (chunks(xs, n): split a list into lists of n, last one shorter; n < 1 raises ValueError), "
             "c.py (flatten(xs): flatten arbitrarily nested lists), d.py (camel_to_snake(s): 'parseHTTPReply' -> "
             "'parse_http_reply'). Implement all four, and write tests/test_a.py ... tests/test_d.py with at least "
             "three asserts each. The four parts are independent and can be done in parallel.",
    "files": {"a.py": "def is_palindrome(s):\n    raise NotImplementedError\n",
              "b.py": "def chunks(xs, n):\n    raise NotImplementedError\n",
              "c.py": "def flatten(xs):\n    raise NotImplementedError\n",
              "d.py": "def camel_to_snake(s):\n    raise NotImplementedError\n",
              "tests/__init__.py": ""},
    "visible": None,
    "hidden": "import pytest\nfrom a import is_palindrome\nfrom b import chunks\nfrom c import flatten\n"
              "from d import camel_to_snake\n\n\ndef test_hidden():\n"
              "    assert is_palindrome('A man, a plan, a canal: Panama')\n    assert not is_palindrome('ab')\n"
              "    assert chunks([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]\n"
              "    with pytest.raises(ValueError):\n        chunks([1], 0)\n"
              "    assert flatten([1, [2, [3, [4]]], []]) == [1, 2, 3, 4]\n"
              "    assert camel_to_snake('parseHTTPReply') == 'parse_http_reply'\n"
              "    assert camel_to_snake('simple') == 'simple'\n",
    "solution": {"a.py": "def is_palindrome(s):\n    t = [c.lower() for c in s if c.isalpha()]\n    return t == t[::-1]\n",
                 "b.py": "def chunks(xs, n):\n    if n < 1:\n        raise ValueError(n)\n"
                         "    return [xs[i:i + n] for i in range(0, len(xs), n)]\n",
                 "c.py": "def flatten(xs):\n    out = []\n    for x in xs:\n"
                         "        out.extend(flatten(x) if isinstance(x, list) else [x])\n    return out\n",
                 "d.py": "import re\n\n\ndef camel_to_snake(s):\n"
                         "    s = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\\1_\\2', s)\n"
                         "    return re.sub(r'([a-z0-9])([A-Z])', r'\\1_\\2', s).lower()\n"},
}


def by_id(task_id: str) -> dict:
    for t in [*TASKS, *MEDIUM, *MEMORY, PARALLEL_TASK]:
        if t["id"] == task_id:
            return t
    raise KeyError(task_id)
