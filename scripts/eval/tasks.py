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
    for t in [*TASKS, PARALLEL_TASK]:
        if t["id"] == task_id:
            return t
    raise KeyError(task_id)
