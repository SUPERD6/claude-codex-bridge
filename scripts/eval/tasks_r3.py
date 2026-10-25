"""Round-3 tasks (docs/research/2026-10-25-r3-plan.md): harder and vaguer than round 2's traps.

Every task is a small package of 4-7 files that has to be read before it can be changed; the change touches more
than one file or has to fit code that is already there; and the brief leaves ONE requirement to be inferred from
that code ("like the other commands", "the usual way", "like every other log line"). The visible test checks only
the main path; the hidden test checks the inferred requirement too. The inferred part is always something the
existing code shows (a helper, a convention, a registry, a cache key, a migration list), never a guess.

tests/test_eval_tasks.py checks that every start fails its hidden test and every reference solution passes."""
from __future__ import annotations

from textwrap import dedent


def _d(s: str) -> str:
    return dedent(s).lstrip("\n")


HARD: list[dict] = [
    {
        "id": "cli-stats",
        "infer": "register the command by importing it in commands/__init__.py, give it a docstring for help, report "
                 "bad input with UserError (exit 2, 'error: ...' on stderr)",
        "brief": "Add a `stats` command to the tool: `stats FILE` prints `count=N min=X max=Y mean=Z` for the numbers "
                 "in FILE (one per line, blank lines skipped; min and max printed with Python's `{:g}` format, mean "
                 "with 2 decimals). It should be listed by `help` like the other commands. Bad input (a missing "
                 "file, a line that is not a number, a file with no numbers) must be reported the way the tool "
                 "reports bad input everywhere else.",
        "files": {
            "tool/__init__.py": "",
            "tool/errors.py": _d('''
                class UserError(Exception):
                    """Bad input from the person running the tool: main() prints 'error: <message>' to stderr and
                    returns 2."""
                '''),
            "tool/registry.py": _d('''
                COMMANDS = {}


                def command(name):
                    """Register a command function under `name`; its docstring's first line is its help text."""
                    def wrap(fn):
                        COMMANDS[name] = fn
                        return fn
                    return wrap
                '''),
            "tool/io.py": _d('''
                from .errors import UserError


                def read_lines(path):
                    try:
                        with open(path, encoding="utf-8") as f:
                            return f.read().splitlines()
                    except FileNotFoundError:
                        raise UserError(f"no such file: {path}") from None
                '''),
            "tool/commands/__init__.py": _d('''
                # every command module is imported here, so that its @command registers it
                from . import count, head  # noqa: F401
                '''),
            "tool/commands/count.py": _d('''
                from ..errors import UserError
                from ..io import read_lines
                from ..registry import command


                @command("count")
                def count(args, out):
                    """Count the lines of a file."""
                    if len(args) != 1:
                        raise UserError("usage: count FILE")
                    out.write(f"{len(read_lines(args[0]))}\\n")
                '''),
            "tool/commands/head.py": _d('''
                from ..errors import UserError
                from ..io import read_lines
                from ..registry import command


                @command("head")
                def head(args, out):
                    """Print the first N lines of a file (default 5)."""
                    if not args or len(args) > 2:
                        raise UserError("usage: head FILE [N]")
                    try:
                        n = int(args[1]) if len(args) == 2 else 5
                    except ValueError:
                        raise UserError(f"not a number: {args[1]}") from None
                    for line in read_lines(args[0])[:n]:
                        out.write(line + "\\n")
                '''),
            "tool/main.py": _d('''
                import sys

                from . import commands  # noqa: F401  (registers the commands)
                from .errors import UserError
                from .registry import COMMANDS


                def main(argv, out=None, err=None):
                    out = out or sys.stdout
                    err = err or sys.stderr
                    if not argv or argv[0] == "help":
                        for name in sorted(COMMANDS):
                            doc = (COMMANDS[name].__doc__ or "").strip().splitlines()
                            out.write(f"{name:8}{doc[0] if doc else ''}\\n")
                        return 0
                    fn = COMMANDS.get(argv[0])
                    if fn is None:
                        err.write(f"error: unknown command {argv[0]}\\n")
                        return 2
                    try:
                        fn(argv[1:], out)
                    except UserError as e:
                        err.write(f"error: {e}\\n")
                        return 2
                    return 0
                '''),
        },
        "visible": _d('''
            import io

            from tool.main import main


            def test_stats(tmp_path):
                f = tmp_path / "n.txt"
                f.write_text("3\\n1\\n\\n2\\n", encoding="utf-8")
                out = io.StringIO()
                assert main(["stats", str(f)], out, io.StringIO()) == 0
                assert out.getvalue().strip() == "count=3 min=1 max=3 mean=2.00"
            '''),
        "hidden": _d('''
            import io

            from tool.main import main


            def run(*argv):
                out, err = io.StringIO(), io.StringIO()
                rc = main(list(argv), out, err)
                return rc, out.getvalue(), err.getvalue()


            def test_hidden(tmp_path):
                f = tmp_path / "n.txt"
                f.write_text("2.5\\n-1\\n4\\n", encoding="utf-8")
                assert run("stats", str(f))[1].strip() == "count=3 min=-1 max=4 mean=1.83"
                rc, out, _ = run("help")
                line = [x for x in out.splitlines() if x.startswith("stats")]
                assert line and line[0][len("stats"):].strip(), "stats must be listed in help with its help text"
                rc, out, err = run("stats", str(tmp_path / "missing.txt"))
                assert rc == 2 and err.startswith("error: ") and "missing.txt" in err
                bad = tmp_path / "bad.txt"
                bad.write_text("1\\nzwei\\n", encoding="utf-8")
                rc, out, err = run("stats", str(bad))
                assert rc == 2 and err.startswith("error: ")
                empty = tmp_path / "empty.txt"
                empty.write_text("\\n\\n", encoding="utf-8")
                rc, out, err = run("stats", str(empty))
                assert rc == 2 and err.startswith("error: ")
            '''),
        "solution": {
            "tool/commands/__init__.py": "from . import count, head, stats  # noqa: F401\n",
            "tool/commands/stats.py": _d('''
                from ..errors import UserError
                from ..io import read_lines
                from ..registry import command


                @command("stats")
                def stats(args, out):
                    """Count, min, max and mean of the numbers in a file."""
                    if len(args) != 1:
                        raise UserError("usage: stats FILE")
                    nums = []
                    for line in read_lines(args[0]):
                        if not line.strip():
                            continue
                        try:
                            nums.append(float(line))
                        except ValueError:
                            raise UserError(f"not a number: {line}") from None
                    if not nums:
                        raise UserError(f"no numbers in {args[0]}")
                    out.write(f"count={len(nums)} min={min(nums):g} max={max(nums):g} "
                              f"mean={sum(nums) / len(nums):.2f}\\n")
                '''),
        },
    },
    {
        "id": "coupon",
        "infer": "amounts go through shop.money.money (Decimal, half-up to the cent); discounts are negative "
                 "adjustments, which is how the receipt shows them",
        "brief": "Implement apply_coupon(cart, code) in shop/coupons.py using the COUPONS table: a percent coupon "
                 "takes that percent off the subtotal, a fixed one takes the amount off. A cart has at most one "
                 "coupon: applying another replaces the earlier one. The discount must show on the receipt like "
                 "the other adjustments (label `coupon CODE`), and the total can never go below zero. An unknown "
                 "code raises KeyError.",
        "files": {
            "shop/__init__.py": "",
            "shop/money.py": _d('''
                from decimal import ROUND_HALF_UP, Decimal

                CENT = Decimal("0.01")


                def money(x) -> Decimal:
                    """Every amount in the shop goes through here: a Decimal rounded half-up to the cent."""
                    return Decimal(str(x)).quantize(CENT, rounding=ROUND_HALF_UP)
                '''),
            "shop/cart.py": _d('''
                from .money import money


                class Cart:
                    def __init__(self):
                        self.lines = []          # (sku, unit_price, qty)
                        self.adjustments = []    # (label, amount); a negative amount is a discount

                    def add(self, sku, price, qty=1):
                        self.lines.append((sku, money(price), qty))

                    def subtotal(self):
                        return money(sum(p * q for _, p, q in self.lines))

                    def total(self):
                        return money(self.subtotal() + sum(a for _, a in self.adjustments))
                '''),
            "shop/shipping.py": _d('''
                from .money import money

                FREE_FROM = money("50")


                def add_shipping(cart, fee="4.99"):
                    if cart.subtotal() < FREE_FROM:
                        cart.adjustments.append(("shipping", money(fee)))
                '''),
            "shop/receipt.py": _d('''
                def receipt(cart):
                    rows = [f"{sku} x{q}  {p * q}" for sku, p, q in cart.lines]
                    rows.append(f"subtotal  {cart.subtotal()}")
                    rows += [f"{label}  {amount}" for label, amount in cart.adjustments]
                    rows.append(f"total  {cart.total()}")
                    return "\\n".join(rows)
                '''),
            "shop/coupons.py": _d('''
                COUPONS = {"SAVE10": ("percent", 10), "FLAT5": ("fixed", "5.00")}


                def apply_coupon(cart, code):
                    raise NotImplementedError
                '''),
        },
        "visible": _d('''
            from shop.cart import Cart
            from shop.coupons import apply_coupon


            def test_percent():
                c = Cart()
                c.add("A", "20.00")
                apply_coupon(c, "SAVE10")
                assert str(c.total()) == "18.00"
            '''),
        "hidden": _d('''
            import pytest
            from shop.cart import Cart
            from shop.coupons import apply_coupon
            from shop.receipt import receipt
            from shop.shipping import add_shipping


            def test_hidden():
                c = Cart()
                c.add("A", "10.25")
                add_shipping(c)
                apply_coupon(c, "SAVE10")
                assert str(c.total()) == "14.21"           # 10.25 - 1.03 (1.025 rounded half-up) + 4.99
                assert "coupon SAVE10  -1.03" in receipt(c)
                apply_coupon(c, "FLAT5")
                assert [a[0] for a in c.adjustments] == ["shipping", "coupon FLAT5"]
                assert "coupon FLAT5  -5.00" in receipt(c)
                small = Cart()
                small.add("B", "3.00")
                apply_coupon(small, "FLAT5")
                assert str(small.total()) == "0.00"
                with pytest.raises(KeyError):
                    apply_coupon(small, "NOPE")
            '''),
        "solution": {
            "shop/coupons.py": _d('''
                from .money import money

                COUPONS = {"SAVE10": ("percent", 10), "FLAT5": ("fixed", "5.00")}


                def apply_coupon(cart, code):
                    kind, value = COUPONS[code]
                    cart.adjustments = [a for a in cart.adjustments if not a[0].startswith("coupon ")]
                    sub = cart.subtotal()
                    off = money(sub * value / 100) if kind == "percent" else money(value)
                    rest = cart.total()
                    off = min(off, rest)
                    cart.adjustments.append((f"coupon {code}", money(-off)))
                '''),
        },
    },
    {
        "id": "env-config",
        "infer": "environment values are converted with coerce() like file values; "
                 "sections have no underscore, so APP_DB_POOL_SIZE is db.pool_size",
        "brief": "Add environment-variable overrides to app.config.load: it gets an `env` argument (a mapping, "
                 "default os.environ). A variable APP_<SECTION>_<KEY> in upper case (e.g. APP_SERVER_PORT) "
                 "overrides that setting; the environment beats the file, the file beats the defaults. "
                 "Environment values must be handled like values from the file.",
        "files": {
            "app/__init__.py": "",
            "app/defaults.py": _d('''
                DEFAULTS = {
                    "server": {"host": "127.0.0.1", "port": 8080, "debug": False},
                    "db": {"url": "sqlite:///app.db", "pool_size": 5},
                }
                '''),
            "app/coerce.py": _d('''
                TRUE = {"1", "true", "yes", "on"}
                FALSE = {"0", "false", "no", "off"}


                def coerce(raw, default):
                    """Turn a text value into the type of the default (bool first: a bool is also an int)."""
                    if isinstance(default, bool):
                        v = raw.strip().lower()
                        if v in TRUE:
                            return True
                        if v in FALSE:
                            return False
                        raise ValueError(f"not a boolean: {raw!r}")
                    if isinstance(default, int):
                        return int(raw)
                    return raw
                '''),
            "app/config.py": _d('''
                import configparser
                import copy

                from .coerce import coerce
                from .defaults import DEFAULTS


                def load(path=None):
                    """Defaults, then the ini file. Unknown sections or keys in the file are not applied; they are
                    listed as 'section.key' in cfg['_ignored']."""
                    cfg = copy.deepcopy(DEFAULTS)
                    ignored = []
                    if path:
                        cp = configparser.ConfigParser()
                        cp.read(path, encoding="utf-8")
                        for sec in cp.sections():
                            for key, raw in cp.items(sec):
                                if sec in cfg and key in cfg[sec]:
                                    cfg[sec][key] = coerce(raw, DEFAULTS[sec][key])
                                else:
                                    ignored.append(f"{sec}.{key}")
                    cfg["_ignored"] = ignored
                    return cfg
                '''),
        },
        "visible": _d('''
            from app.config import load


            def test_env_host():
                assert load(env={"APP_SERVER_HOST": "0.0.0.0"})["server"]["host"] == "0.0.0.0"
            '''),
        "hidden": _d('''
            from app.config import load


            def test_hidden(tmp_path, monkeypatch):
                ini = tmp_path / "a.ini"
                ini.write_text("[server]\\nport = 8081\\nhost = h1\\n", encoding="utf-8")
                env = {"APP_SERVER_PORT": "9000", "APP_SERVER_DEBUG": "yes", "APP_DB_POOL_SIZE": "7",
                       "APP_NOPE_X": "1", "OTHER": "x"}
                cfg = load(str(ini), env=env)
                assert cfg["server"]["port"] == 9000 and isinstance(cfg["server"]["port"], int)
                assert cfg["server"]["debug"] is True
                assert cfg["server"]["host"] == "h1"
                assert cfg["db"]["pool_size"] == 7
                assert load(env={})["server"]["port"] == 8080
                monkeypatch.setenv("APP_SERVER_PORT", "7000")
                assert load()["server"]["port"] == 7000
            '''),
        "solution": {
            "app/config.py": _d('''
                import configparser
                import copy
                import os

                from .coerce import coerce
                from .defaults import DEFAULTS


                def load(path=None, env=None):
                    env = os.environ if env is None else env
                    cfg = copy.deepcopy(DEFAULTS)
                    ignored = []

                    def put(sec, key, raw):
                        if sec in cfg and key in cfg[sec]:
                            cfg[sec][key] = coerce(raw, DEFAULTS[sec][key])
                        else:
                            ignored.append(f"{sec}.{key}")
                    if path:
                        cp = configparser.ConfigParser()
                        cp.read(path, encoding="utf-8")
                        for sec in cp.sections():
                            for key, raw in cp.items(sec):
                                put(sec, key, raw)
                    for name, raw in env.items():
                        if name.startswith("APP_") and "_" in name[4:]:
                            sec, key = name[4:].lower().split("_", 1)
                            put(sec, key, raw)
                    cfg["_ignored"] = ignored
                    return cfg
                '''),
        },
    },
    {
        "id": "rename-user",
        "infer": "every write drops the cache keys it makes stale: ('id', uid), the old name AND the new name "
                 "(find_by_name caches a miss as None)",
        "brief": "Add UserRepo.rename(uid, new_name) in users/repo.py. Names are unique ignoring case: renaming to a "
                 "name another user has raises DuplicateName (add it next to the other errors); renaming to the "
                 "same name in a different case is allowed. An unknown id raises NotFound.",
        "files": {
            "users/__init__.py": "",
            "users/errors.py": _d('''
                class NotFound(Exception):
                    pass


                class DuplicateEmail(Exception):
                    pass
                '''),
            "users/cache.py": _d('''
                class Cache:
                    """Remembers whatever load() returned for a key, None included, until the key is dropped."""

                    def __init__(self):
                        self._d = {}

                    def get(self, key, load):
                        if key not in self._d:
                            self._d[key] = load()
                        return self._d[key]

                    def drop(self, *keys):
                        for k in keys:
                            self._d.pop(k, None)
                '''),
            "users/repo.py": _d('''
                from .cache import Cache
                from .errors import DuplicateEmail, NotFound


                class UserRepo:
                    """Rows live in self._rows (id -> dict). Reads go through the cache; every write must drop the
                    cache keys it makes stale."""

                    def __init__(self, rows=None):
                        self._rows = {r["id"]: dict(r) for r in rows or []}
                        self._cache = Cache()

                    def get(self, uid):
                        return self._cache.get(("id", uid), lambda: self._load(uid))

                    def find_by_name(self, name):
                        key = name.lower()
                        return self._cache.get(("name", key), lambda: next(
                            (dict(r) for r in self._rows.values() if r["name"].lower() == key), None))

                    def _load(self, uid):
                        if uid not in self._rows:
                            raise NotFound(uid)
                        return dict(self._rows[uid])

                    def update_email(self, uid, email):
                        if uid not in self._rows:
                            raise NotFound(uid)
                        if any(r["email"] == email and r["id"] != uid for r in self._rows.values()):
                            raise DuplicateEmail(email)
                        self._rows[uid]["email"] = email
                        self._cache.drop(("id", uid), ("name", self._rows[uid]["name"].lower()))
                '''),
        },
        "visible": _d('''
            from users.repo import UserRepo


            def test_rename():
                r = UserRepo([{"id": 1, "name": "alice", "email": "a@x"}])
                r.rename(1, "alicia")
                assert r.find_by_name("alicia")["id"] == 1
            '''),
        "hidden": _d('''
            import pytest
            from users import errors
            from users.repo import UserRepo


            def test_hidden():
                r = UserRepo([{"id": 1, "name": "alice", "email": "a@x"}, {"id": 2, "name": "bob", "email": "b@x"}])
                assert r.get(1)["name"] == "alice"
                assert r.find_by_name("Alicia") is None          # a miss is cached too
                assert r.find_by_name("alice")["id"] == 1
                r.rename(1, "alicia")
                assert r.get(1)["name"] == "alicia"
                assert r.find_by_name("alice") is None
                assert r.find_by_name("ALICIA")["id"] == 1
                with pytest.raises(errors.DuplicateName):
                    r.rename(1, "Bob")
                r.rename(1, "Alicia")
                assert r.get(1)["name"] == "Alicia"
                assert r.find_by_name("alicia")["name"] == "Alicia"
                with pytest.raises(errors.NotFound):
                    r.rename(9, "zed")
            '''),
        "solution": {
            "users/errors.py": "class NotFound(Exception):\n    pass\n\n\nclass DuplicateEmail(Exception):\n"
                               "    pass\n\n\nclass DuplicateName(Exception):\n    pass\n",
            "users/repo.py": _d('''
                from .cache import Cache
                from .errors import DuplicateEmail, DuplicateName, NotFound


                class UserRepo:
                    def __init__(self, rows=None):
                        self._rows = {r["id"]: dict(r) for r in rows or []}
                        self._cache = Cache()

                    def get(self, uid):
                        return self._cache.get(("id", uid), lambda: self._load(uid))

                    def find_by_name(self, name):
                        key = name.lower()
                        return self._cache.get(("name", key), lambda: next(
                            (dict(r) for r in self._rows.values() if r["name"].lower() == key), None))

                    def _load(self, uid):
                        if uid not in self._rows:
                            raise NotFound(uid)
                        return dict(self._rows[uid])

                    def update_email(self, uid, email):
                        if uid not in self._rows:
                            raise NotFound(uid)
                        if any(r["email"] == email and r["id"] != uid for r in self._rows.values()):
                            raise DuplicateEmail(email)
                        self._rows[uid]["email"] = email
                        self._cache.drop(("id", uid), ("name", self._rows[uid]["name"].lower()))

                    def rename(self, uid, new_name):
                        if uid not in self._rows:
                            raise NotFound(uid)
                        if any(r["name"].lower() == new_name.lower() and r["id"] != uid for r in self._rows.values()):
                            raise DuplicateName(new_name)
                        old = self._rows[uid]["name"]
                        self._rows[uid]["name"] = new_name
                        self._cache.drop(("id", uid), ("name", old.lower()), ("name", new_name.lower()))
                '''),
        },
    },
    {
        "id": "csv-report",
        "infer": "a report for people looks like the text report: column labels as the header, each value through "
                 "its column's fmt; quoting by the csv module (values like '1,234.50' contain commas)",
        "brief": "Add a `csv` output format to the report, so render(rows, 'csv') works. It is meant for people who "
                 "open the file in a spreadsheet, so it should read like the text report: one header row, then one "
                 "row per record.",
        "files": {
            "report/__init__.py": "",
            "report/columns.py": _d('''
                from dataclasses import dataclass
                from typing import Callable


                def money(v):
                    return f"{v:,.2f}"


                def pct(v):
                    return f"{v * 100:.1f}%"


                @dataclass(frozen=True)
                class Column:
                    key: str
                    label: str
                    fmt: Callable = str


                COLUMNS = [Column("customer", "Customer"), Column("orders", "Orders"), Column("total", "Total", money),
                           Column("share", "Share", pct)]
                '''),
            "report/formatters.py": _d('''
                import json

                from .columns import COLUMNS

                FORMATTERS = {}


                def formatter(name):
                    def wrap(fn):
                        FORMATTERS[name] = fn
                        return fn
                    return wrap


                @formatter("text")
                def text(rows):
                    """For people: column labels, every value through its column's fmt."""
                    lines = ["  ".join(c.label for c in COLUMNS)]
                    lines += ["  ".join(c.fmt(r[c.key]) for c in COLUMNS) for r in rows]
                    return "\\n".join(lines) + "\\n"


                @formatter("json")
                def as_json(rows):
                    """For programs: raw values, keyed by column key."""
                    return json.dumps([{c.key: r[c.key] for c in COLUMNS} for r in rows])
                '''),
            "report/render.py": _d('''
                from .formatters import FORMATTERS


                class UnknownFormat(ValueError):
                    pass


                def render(rows, fmt="text"):
                    if fmt not in FORMATTERS:
                        raise UnknownFormat(f"{fmt!r}; known: {', '.join(sorted(FORMATTERS))}")
                    return FORMATTERS[fmt](rows)
                '''),
        },
        "visible": _d('''
            from report.render import render


            def test_csv_exists():
                out = render([{"customer": "Zed", "orders": 1, "total": 5.0, "share": 0.5}], "csv")
                assert out.splitlines()[0].startswith("Customer")
            '''),
        "hidden": _d('''
            import csv
            import io

            from report.render import render


            def test_hidden():
                rows = [{"customer": "Acme, Inc.", "orders": 3, "total": 1234.5, "share": 0.125},
                        {"customer": "Bo", "orders": 1, "total": 7, "share": 0.875}]
                got = list(csv.reader(io.StringIO(render(rows, "csv"))))
                assert got == [["Customer", "Orders", "Total", "Share"], ["Acme, Inc.", "3", "1,234.50", "12.5%"],
                               ["Bo", "1", "7.00", "87.5%"]]
            '''),
        "solution": {
            "report/formatters.py": _d('''
                import csv
                import io
                import json

                from .columns import COLUMNS

                FORMATTERS = {}


                def formatter(name):
                    def wrap(fn):
                        FORMATTERS[name] = fn
                        return fn
                    return wrap


                @formatter("text")
                def text(rows):
                    lines = ["  ".join(c.label for c in COLUMNS)]
                    lines += ["  ".join(c.fmt(r[c.key]) for c in COLUMNS) for r in rows]
                    return "\\n".join(lines) + "\\n"


                @formatter("json")
                def as_json(rows):
                    return json.dumps([{c.key: r[c.key] for c in COLUMNS} for r in rows])


                @formatter("csv")
                def as_csv(rows):
                    buf = io.StringIO()
                    w = csv.writer(buf)
                    w.writerow([c.label for c in COLUMNS])
                    for r in rows:
                        w.writerow([c.fmt(r[c.key]) for c in COLUMNS])
                    return buf.getvalue()
                '''),
        },
    },
    {
        "id": "search-api",
        "infer": "like list_items: archived items hidden, the same page/per_page parsing (clamped to MAX_PER_PAGE, "
                 "BadRequest on bad values), filter before paginating, the same envelope; missing q is a BadRequest",
        "brief": "Implement search_items(params) in api/handlers.py: like list_items, but only the items whose name "
                 "contains params['q'] (ignoring case). q is required.",
        "files": {
            "api/__init__.py": "",
            "api/errors.py": _d('''
                class BadRequest(Exception):
                    """The client sent bad parameters: the server answers 400 with the message."""
                '''),
            "api/params.py": _d('''
                from .errors import BadRequest


                def int_param(params, name, default, lo=1, hi=None):
                    raw = params.get(name)
                    if raw is None:
                        return default
                    try:
                        v = int(raw)
                    except (TypeError, ValueError):
                        raise BadRequest(f"{name} must be a whole number") from None
                    if v < lo:
                        raise BadRequest(f"{name} must be >= {lo}")
                    return min(v, hi) if hi else v
                '''),
            "api/pagination.py": _d('''
                import math

                MAX_PER_PAGE = 50


                def page_of(items, page, per_page):
                    total = len(items)
                    start = (page - 1) * per_page
                    return {"items": items[start:start + per_page], "page": page, "per_page": per_page, "total": total,
                            "pages": max(1, math.ceil(total / per_page))}
                '''),
            "api/store.py": _d('''
                ITEMS = [
                    {"id": 1, "name": "Desk lamp", "archived": False},
                    {"id": 2, "name": "Floor lamp", "archived": True},
                    {"id": 3, "name": "Chair", "archived": False},
                ]
                '''),
            "api/handlers.py": _d('''
                from .pagination import MAX_PER_PAGE, page_of
                from .params import int_param
                from .store import ITEMS


                def list_items(params, items=None):
                    items = [i for i in (ITEMS if items is None else items) if not i["archived"]]
                    page = int_param(params, "page", 1)
                    per_page = int_param(params, "per_page", 20, hi=MAX_PER_PAGE)
                    return page_of(items, page, per_page)


                def search_items(params, items=None):
                    raise NotImplementedError
                '''),
        },
        "visible": _d('''
            from api.handlers import search_items


            def test_search():
                res = search_items({"q": "chair"})
                assert [i["id"] for i in res["items"]] == [3]
            '''),
        "hidden": _d('''
            import pytest
            from api.errors import BadRequest
            from api.handlers import search_items


            def test_hidden():
                assert [i["id"] for i in search_items({"q": "LAMP"})["items"]] == [1]
                items = [{"id": n, "name": f"lamp {n}" if n % 2 else f"cup {n}", "archived": n == 5} for n in range(1, 201)]
                res = search_items({"q": "lamp", "per_page": "500", "page": "2"}, items)
                assert res["per_page"] == 50 and res["page"] == 2 and res["total"] == 99 and res["pages"] == 2
                assert [i["id"] for i in res["items"]][:2] == [103, 105]
                for bad in ({"q": "lamp", "page": "x"}, {"q": "lamp", "page": "0"}, {}):
                    with pytest.raises(BadRequest):
                        search_items(bad, items)
            '''),
        "solution": {
            "api/handlers.py": _d('''
                from .errors import BadRequest
                from .pagination import MAX_PER_PAGE, page_of
                from .params import int_param
                from .store import ITEMS


                def _visible(items):
                    return [i for i in (ITEMS if items is None else items) if not i["archived"]]


                def _page(params, items):
                    page = int_param(params, "page", 1)
                    per_page = int_param(params, "per_page", 20, hi=MAX_PER_PAGE)
                    return page_of(items, page, per_page)


                def list_items(params, items=None):
                    return _page(params, _visible(items))


                def search_items(params, items=None):
                    q = params.get("q")
                    if not q:
                        raise BadRequest("q is required")
                    return _page(params, [i for i in _visible(items) if q.lower() in i["name"].lower()])
                '''),
        },
    },
    {
        "id": "retry-json",
        "infer": "retry exactly like download: RETRY_STATUS and ConnectionError, waits from backoff.delays through "
                 "the injected self.sleep, no retry on other 4xx, ClientError carries the attempts",
        "brief": "Client.get_json gives up on the first flaky response. Make it retry the same way download does, "
                 "and make sure the two cannot drift apart again.",
        "files": {
            "net/__init__.py": "",
            "net/errors.py": _d('''
                class ClientError(Exception):
                    def __init__(self, status, url, attempts=1):
                        super().__init__(f"{status} from {url} after {attempts} attempt(s)")
                        self.status, self.url, self.attempts = status, url, attempts
                '''),
            "net/backoff.py": _d('''
                def delays(base, n):
                    """The waits between n + 1 attempts: base, 2 * base, 4 * base, ..."""
                    return [base * 2 ** i for i in range(n)]
                '''),
            "net/transport.py": _d('''
                from dataclasses import dataclass


                @dataclass
                class Response:
                    status: int
                    body: str


                class Transport:
                    """send(method, url) -> Response; may raise ConnectionError."""

                    def send(self, method, url):
                        raise NotImplementedError
                '''),
            "net/client.py": _d('''
                import json
                import time

                from .backoff import delays
                from .errors import ClientError

                RETRY_STATUS = {502, 503, 504}


                class Client:
                    def __init__(self, transport, max_retries=2, base_delay=0.5, sleep=time.sleep):
                        self.transport = transport
                        self.max_retries = max_retries
                        self.base_delay = base_delay
                        self.sleep = sleep            # tests pass a fake

                    def download(self, url):
                        """The raw body. Retries RETRY_STATUS and ConnectionError, waiting delays(base_delay,
                        max_retries) between attempts."""
                        waits = delays(self.base_delay, self.max_retries)
                        for attempt in range(self.max_retries + 1):
                            try:
                                resp = self.transport.send("GET", url)
                            except ConnectionError:
                                if attempt == self.max_retries:
                                    raise
                            else:
                                if resp.status < 400:
                                    return resp.body
                                if resp.status not in RETRY_STATUS or attempt == self.max_retries:
                                    raise ClientError(resp.status, url, attempt + 1)
                            self.sleep(waits[attempt])

                    def get_json(self, url):
                        resp = self.transport.send("GET", url)
                        if resp.status >= 400:
                            raise ClientError(resp.status, url)
                        return json.loads(resp.body)
                '''),
        },
        "visible": _d('''
            from net.client import Client
            from net.transport import Response


            class Seq:
                def __init__(self, *items):
                    self.items = list(items)

                def send(self, method, url):
                    x = self.items.pop(0)
                    if isinstance(x, Exception):
                        raise x
                    return x


            def test_retry_once():
                c = Client(Seq(Response(503, ""), Response(200, '{"a": 1}')), sleep=lambda s: None)
                assert c.get_json("u") == {"a": 1}
            '''),
        "hidden": _d('''
            import pytest
            from net.client import Client
            from net.errors import ClientError
            from net.transport import Response


            class Seq:
                def __init__(self, *items):
                    self.items = list(items)

                def send(self, method, url):
                    x = self.items.pop(0)
                    if isinstance(x, Exception):
                        raise x
                    return x


            def test_hidden():
                slept = []
                c = Client(Seq(Response(503, ""), Response(502, ""), Response(200, "[1]")), sleep=slept.append)
                assert c.get_json("u") == [1] and slept == [0.5, 1.0]
                slept.clear()
                c = Client(Seq(ConnectionError(), Response(200, "{}")), sleep=slept.append)
                assert c.get_json("u") == {} and slept == [0.5]
                slept.clear()
                c = Client(Seq(Response(404, "")), sleep=slept.append)
                with pytest.raises(ClientError) as e:
                    c.get_json("u")
                assert e.value.attempts == 1 and slept == []
                c = Client(Seq(*[Response(504, "")] * 3), sleep=slept.append, base_delay=1)
                with pytest.raises(ClientError) as e:
                    c.get_json("u")
                assert e.value.attempts == 3 and e.value.status == 504 and slept == [1, 2]
                c = Client(Seq(Response(503, ""), Response(200, "abc")), sleep=lambda s: None)
                assert c.download("u") == "abc"
            '''),
        "solution": {
            "net/client.py": _d('''
                import json
                import time

                from .backoff import delays
                from .errors import ClientError

                RETRY_STATUS = {502, 503, 504}


                class Client:
                    def __init__(self, transport, max_retries=2, base_delay=0.5, sleep=time.sleep):
                        self.transport = transport
                        self.max_retries = max_retries
                        self.base_delay = base_delay
                        self.sleep = sleep

                    def _get(self, url):
                        waits = delays(self.base_delay, self.max_retries)
                        for attempt in range(self.max_retries + 1):
                            try:
                                resp = self.transport.send("GET", url)
                            except ConnectionError:
                                if attempt == self.max_retries:
                                    raise
                            else:
                                if resp.status < 400:
                                    return resp.body
                                if resp.status not in RETRY_STATUS or attempt == self.max_retries:
                                    raise ClientError(resp.status, url, attempt + 1)
                            self.sleep(waits[attempt])

                    def download(self, url):
                        return self._get(url)

                    def get_json(self, url):
                        return json.loads(self._get(url))
                '''),
        },
    },
    {
        "id": "debug-line",
        "infer": "every log line goes through redact() (on the original header/query names, before adding the h./q. "
                 "prefix, or 'h.authorization' is not a secret name) and logfmt() (sorting and quoting)",
        "brief": "Implement debug_line(request) in logs/debug.py: one log line, 'debug ' followed by the request's "
                 "method, path, headers and query parameters in the same key=value style as the audit lines. "
                 "Header names become `h.<name>` and query parameters `q.<name>`. The request is a dict with "
                 "method, path, headers (dict) and query (dict).",
        "files": {
            "logs/__init__.py": "",
            "logs/redact.py": _d('''
                SECRET = {"authorization", "cookie", "password", "token", "api_key", "x-api-key"}


                def redact(d):
                    """A copy of d with secret values replaced by '***' (names compared ignoring case)."""
                    return {k: ("***" if k.lower() in SECRET else v) for k, v in d.items()}
                '''),
            "logs/logfmt.py": _d('''
                def logfmt(fields):
                    """key=value pairs sorted by key; a value with a space or '=' (or an empty one) is
                    double-quoted."""
                    def q(v):
                        s = str(v)
                        return f'"{s}"' if (" " in s or "=" in s or not s) else s
                    return " ".join(f"{k}={q(v)}" for k, v in sorted(fields.items()))
                '''),
            "logs/audit.py": _d('''
                from .logfmt import logfmt
                from .redact import redact


                def audit_line(user, action, details):
                    """Every line this project logs goes through redact() before it is formatted."""
                    return "audit " + logfmt({"user": user, "action": action, **redact(details)})
                '''),
            "logs/debug.py": _d('''
                def debug_line(request):
                    raise NotImplementedError
                '''),
        },
        "visible": _d('''
            from logs.debug import debug_line


            def test_simple():
                req = {"method": "GET", "path": "/", "headers": {"Accept": "text/html"}, "query": {}}
                assert debug_line(req) == "debug h.Accept=text/html method=GET path=/"
            '''),
        "hidden": _d('''
            from logs.debug import debug_line


            def test_hidden():
                req = {"method": "POST", "path": "/login",
                       "headers": {"Authorization": "Bearer abc123", "User-Agent": "curl 8", "Cookie": "s=1"},
                       "query": {"token": "t0k", "next": "/home"}}
                line = debug_line(req)
                assert line.startswith("debug ")
                assert "abc123" not in line and "t0k" not in line and "s=1" not in line
                assert "h.Authorization=***" in line and "q.token=***" in line and "h.Cookie=***" in line
                assert 'h.User-Agent="curl 8"' in line and "q.next=/home" in line
                keys = [kv.split("=", 1)[0] for kv in line[len("debug "):].replace('"curl 8"', "x").split(" ")]
                assert keys == sorted(keys)
            '''),
        "solution": {
            "logs/debug.py": _d('''
                from .logfmt import logfmt
                from .redact import redact


                def debug_line(request):
                    fields = {"method": request["method"], "path": request["path"]}
                    fields.update({f"h.{k}": v for k, v in redact(request.get("headers") or {}).items()})
                    fields.update({f"q.{k}": v for k, v in redact(request.get("query") or {}).items()})
                    return "debug " + logfmt(fields)
                '''),
        },
    },
    {
        "id": "display-name",
        "infer": "'the usual way' to upgrade stored databases is a new migration appended to MIGRATIONS (version 3) "
                 "that fills display_name for existing rows",
        "brief": "Users need a display_name (shown instead of the username), defaulting to the username. Add it to "
                 "User, to create_user (an optional display_name argument) and to get_user. Databases that are "
                 "already stored must be upgraded the usual way.",
        "files": {
            "db/__init__.py": "",
            "db/migrations.py": _d('''
                # One function per schema change, in order. Never edit a shipped migration: add a new one.


                def m001_create_users(db):
                    db.setdefault("users", [])


                def m002_add_email_verified(db):
                    for u in db["users"]:
                        u.setdefault("email_verified", False)


                MIGRATIONS = [m001_create_users, m002_add_email_verified]
                '''),
            "db/schema.py": _d('''
                from .migrations import MIGRATIONS


                def migrate(db):
                    """Bring a stored db (a dict) up to date: run the migrations after db['version'], in order."""
                    v = db.get("version", 0)
                    for i, m in enumerate(MIGRATIONS[v:], start=v + 1):
                        m(db)
                        db["version"] = i
                    return db


                def new_db():
                    return migrate({"version": 0})
                '''),
            "db/users.py": _d('''
                from dataclasses import dataclass


                @dataclass
                class User:
                    username: str
                    email: str
                    email_verified: bool = False


                def create_user(db, username, email):
                    row = {"username": username, "email": email, "email_verified": False}
                    db["users"].append(row)
                    return User(**row)


                def get_user(db, username):
                    return User(**next(r for r in db["users"] if r["username"] == username))
                '''),
        },
        "visible": _d('''
            from db.schema import new_db
            from db.users import create_user, get_user


            def test_display_name():
                db = new_db()
                create_user(db, "ann", "a@x", display_name="Ann B.")
                assert get_user(db, "ann").display_name == "Ann B."
            '''),
        "hidden": _d('''
            from db.schema import migrate, new_db
            from db.users import create_user, get_user


            def test_hidden():
                old = {"version": 2, "users": [{"username": "zed", "email": "z@x", "email_verified": True}]}
                migrate(old)
                assert old["version"] == 3
                assert old["users"][0]["display_name"] == "zed"
                assert get_user(old, "zed").display_name == "zed"
                db = new_db()
                assert db["version"] == 3
                assert create_user(db, "bo", "b@x").display_name == "bo"
                assert db["users"][0]["display_name"] == "bo"
                assert migrate(dict(old))["version"] == 3
            '''),
        "solution": {
            "db/migrations.py": _d('''
                def m001_create_users(db):
                    db.setdefault("users", [])


                def m002_add_email_verified(db):
                    for u in db["users"]:
                        u.setdefault("email_verified", False)


                def m003_add_display_name(db):
                    for u in db["users"]:
                        u.setdefault("display_name", u["username"])


                MIGRATIONS = [m001_create_users, m002_add_email_verified, m003_add_display_name]
                '''),
            "db/users.py": _d('''
                from dataclasses import dataclass


                @dataclass
                class User:
                    username: str
                    email: str
                    email_verified: bool = False
                    display_name: str = ""


                def create_user(db, username, email, display_name=None):
                    row = {"username": username, "email": email, "email_verified": False,
                           "display_name": display_name or username}
                    db["users"].append(row)
                    return User(**row)


                def get_user(db, username):
                    return User(**next(r for r in db["users"] if r["username"] == username))
                '''),
        },
    },
    {
        "id": "rename-slug",
        "infer": "renamed functions keep the old name through compat.deprecated_alias (DeprecationWarning naming "
                 "the new function); callers inside the package switch to the new name so they do not warn",
        "brief": "Rename text.slug.slugify to make_slug and update its callers. Code outside this repo still calls "
                 "slugify, so keep that name working for a while, the way this package already handles renamed "
                 "functions.",
        "files": {
            "text/__init__.py": "",
            "text/compat.py": _d('''
                import functools
                import warnings


                def deprecated_alias(new, old_name):
                    """The old name of a renamed function: works, but warns once per call site."""
                    @functools.wraps(new)
                    def old(*a, **kw):
                        warnings.warn(f"{old_name} is deprecated; use {new.__name__}", DeprecationWarning, stacklevel=2)
                        return new(*a, **kw)
                    old.__name__ = old_name
                    return old
                '''),
            "text/titles.py": _d('''
                from .compat import deprecated_alias


                def make_title(s):
                    return " ".join(w.capitalize() for w in s.split())


                old_title = deprecated_alias(make_title, "old_title")      # renamed 2025-03
                '''),
            "text/slug.py": _d('''
                import re


                def slugify(s):
                    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
                '''),
            "text/pages.py": _d('''
                from .slug import slugify


                def page_url(title):
                    return "/p/" + slugify(title)
                '''),
            "text/tags.py": _d('''
                from . import slug


                def tag_ids(tags):
                    return sorted({slug.slugify(t) for t in tags})
                '''),
        },
        "visible": _d('''
            from text.slug import make_slug


            def test_make_slug():
                assert make_slug("Hello, World") == "hello-world"
            '''),
        "hidden": _d('''
            import warnings

            import pytest
            from text.pages import page_url
            from text.slug import make_slug, slugify
            from text.tags import tag_ids


            def test_hidden():
                with pytest.warns(DeprecationWarning, match="make_slug"):
                    assert slugify("A b") == "a-b"
                with warnings.catch_warnings():
                    warnings.simplefilter("error")
                    assert page_url("Hello World") == "/p/hello-world"
                    assert tag_ids(["Big Cat", "big-cat", "Dog"]) == ["big-cat", "dog"]
                    assert make_slug("x y") == "x-y"
            '''),
        "solution": {
            "text/slug.py": _d('''
                import re

                from .compat import deprecated_alias


                def make_slug(s):
                    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


                slugify = deprecated_alias(make_slug, "slugify")
                '''),
            "text/pages.py": "from .slug import make_slug\n\n\ndef page_url(title):\n    return \"/p/\" + make_slug(title)\n",
            "text/tags.py": "from . import slug\n\n\ndef tag_ids(tags):\n    return sorted({slug.make_slug(t) for t in tags})\n",
        },
    },
]


def by_id(task_id: str) -> dict:
    for t in HARD:
        if t["id"] == task_id:
            return t
    raise KeyError(task_id)
