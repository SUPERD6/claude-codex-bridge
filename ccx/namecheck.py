"""Undefined-name check (`namecheck`): a name loaded inside a function that a write run changed, which no scope
defines, so calling that function raises NameError. Standard library only (ast + symtable), a few ms per file.

Why: in round 5 two sub-agents shipped exactly this bug (a helper used without its import, behind an
`except Exception`), the tests passed, and only a reviewer reading the diff caught one of them.

Mode (`[defaults] namecheck` in tiers.toml, or `ccx run --namecheck`):
  warn (default) - hits go to the record (`namecheck`), the lead's compact result and the review brief, as weak
                   evidence; the work is not failed.
  fail           - a hit fails the work like a failed acceptance check: kind `check_failed`, check.reason
                   "namecheck"; the acceptance command is not run.
  off            - not run.

What it deliberately does not report (it misses a bug rather than flag good code):
  - a file with `from x import *`, `exec(...)`, `globals()`, writes through `builtins` / `__builtins__`, enum
    members exported to the module (`enum.global_enum`, `_convert_`), or `import cython`;
  - names inside a `try:` whose handler catches NameError (the compatibility idiom);
  - every annotation: local variable annotations are never evaluated (PEP 526), argument and return annotations
    are not under `from __future__ import annotations` or Python 3.14 (PEP 649);
  - decorators, defaults and module-level code (they run at import, which any test of the module does);
  - `_` and `get_ipython` (installed into builtins by gettext.install / IPython);
  - a file that does not parse (listed as `unparsed`, never a failure: it may be newer syntax than ccx's Python).
Only functions whose lines the run changed count, plus any function using a module-level name the run removed.

Builtins are a fixed set so the verdict does not depend on which Python runs ccx: every name `dir(builtins)` has
on 3.11 (Windows, which adds WindowsError), plus the ones 3.13 added, plus whatever the running interpreter has
(a newer Python's additions never become hits). Checked against 3.11.9 and 3.14.4; tests assert the running
interpreter adds nothing outside the set on 3.11-3.13.
"""
from __future__ import annotations

import ast
import builtins
import io
import symtable
import time
import tokenize
from pathlib import Path

MODES = ("warn", "fail", "off")

_BUILTINS_FIXED = frozenset("""
ArithmeticError AssertionError AttributeError BaseException BaseExceptionGroup BlockingIOError BrokenPipeError
BufferError BytesWarning ChildProcessError ConnectionAbortedError ConnectionError ConnectionRefusedError
ConnectionResetError DeprecationWarning EOFError Ellipsis EncodingWarning EnvironmentError Exception
ExceptionGroup False FileExistsError FileNotFoundError FloatingPointError FutureWarning GeneratorExit IOError
ImportError ImportWarning IndentationError IndexError InterruptedError IsADirectoryError KeyError
KeyboardInterrupt LookupError MemoryError ModuleNotFoundError NameError None NotADirectoryError NotImplemented
NotImplementedError OSError OverflowError PendingDeprecationWarning PermissionError ProcessLookupError
RecursionError ReferenceError ResourceWarning RuntimeError RuntimeWarning StopAsyncIteration StopIteration
SyntaxError SyntaxWarning SystemError SystemExit TabError TimeoutError True TypeError UnboundLocalError
UnicodeDecodeError UnicodeEncodeError UnicodeError UnicodeTranslateError UnicodeWarning UserWarning ValueError
Warning WindowsError ZeroDivisionError __build_class__ __debug__ __doc__ __import__ __loader__ __name__
__package__ __spec__ abs aiter all anext any ascii bin bool breakpoint bytearray bytes callable chr
classmethod compile complex copyright credits delattr dict dir divmod enumerate eval exec exit filter float
format frozenset getattr globals hasattr hash help hex id input int isinstance issubclass iter len license
list locals map max memoryview min next object oct open ord pow print property quit range repr reversed round
set setattr slice sorted staticmethod str sum super tuple type vars zip
PythonFinalizationError _IncompleteInputError
""".split())
MODULE_NAMES = frozenset({"__file__", "__cached__", "__path__", "__builtins__", "__annotations__"})
INJECTED = frozenset({"_", "get_ipython"})
KNOWN = _BUILTINS_FIXED | frozenset(dir(builtins)) | MODULE_NAMES | INJECTED

_FUNCS = (ast.FunctionDef, ast.AsyncFunctionDef)
_COMPS = {ast.ListComp: "listcomp", ast.SetComp: "setcomp", ast.DictComp: "dictcomp", ast.GeneratorExp: "genexpr"}
_TRY = tuple(t for t in (ast.Try, getattr(ast, "TryStar", None)) if t)


def mode(req=None, cfg: dict | None = None) -> str:
    """The flag wins, then [defaults] namecheck, then warn."""
    m = (getattr(req, "namecheck", None) or ((cfg or {}).get("defaults") or {}).get("namecheck") or "warn")
    m = str(m).strip().lower()
    return m if m in MODES else "warn"


def _decode(data: bytes | str) -> str:
    """Bytes as Python reads them: a BOM or a coding cookie respected (PowerShell writes UTF-8 with a BOM)."""
    if isinstance(data, str):
        return data.lstrip("﻿")
    enc, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
    return data.decode(enc, errors="replace")


def _tables(t):
    yield t
    for c in t.get_children():
        yield from _tables(c)


def _norm(name: str) -> str:
    return name.strip("<>")


def _candidates(top: symtable.SymbolTable) -> dict[tuple[str, int], set[str]]:
    """Per scope, keyed by (name, line): the names it reads that resolve to module globals or builtins. Two scopes
    with one key (two lambdas on a line) share the names both of them leave unresolved, never more."""
    out: dict[tuple[str, int], set[str]] = {}
    for t in _tables(top):
        kind = str(getattr(t.get_type(), "value", t.get_type()))
        if kind not in ("function", "class"):
            continue
        # not is_assigned/is_parameter: symtable takes any table named "top" for the module (a method `top`)
        names = {s.get_name() for s in t.get_symbols() if s.is_referenced() and s.is_global()
                 and not s.is_assigned() and not s.is_parameter() and not s.is_imported()}
        key = (_norm(t.get_name()), t.get_lineno())
        out[key] = (out[key] & names) if key in out else names
    return out


def _dynamic(tree: ast.Module) -> str | None:
    """Why names in this file may come from somewhere a static check can't see; None when they can't."""
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and any(a.name == "*" for a in n.names):
            return "star import"
        if isinstance(n, ast.Import) and any(a.name == "cython" for a in n.names):
            return "Cython source"                         # pure-Python mode: cimported names are not imports
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            if n.func.id in ("exec", "globals"):          # globals() kept in a variable and written later
                return n.func.id
            if (n.func.id == "setattr" and n.args and isinstance(n.args[0], ast.Name)
                    and n.args[0].id in ("builtins", "__builtins__")):
                return "writes builtins"
        if isinstance(n, (ast.Subscript, ast.Attribute)) and isinstance(n.ctx, (ast.Store, ast.Del)):
            v = n.value
            if isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id in ("globals", "vars"):
                return "writes globals()"
            if isinstance(v, ast.Name) and v.id in ("builtins", "__builtins__"):
                return "writes builtins"
        if isinstance(n, (ast.Attribute, ast.Name)) and (getattr(n, "attr", None) or getattr(n, "id", "")) in (
                "global_enum", "_convert_"):
            return "enum members exported to the module"   # enum.global_enum, IntEnum._convert_ (stdlib ssl, re)
    return None


def module_names(tree: ast.Module, top: symtable.SymbolTable) -> set[str]:
    """Names bound at module level on any branch (conditional, try/except ImportError, TYPE_CHECKING imports
    included), plus every `global x` a function declares."""
    out = {s.get_name() for s in top.get_symbols() if s.is_assigned() or s.is_imported() or s.is_namespace()}
    for n in ast.walk(tree):
        if isinstance(n, ast.Global):
            out.update(n.names)
    return out


def _catches_nameerror(t) -> bool:
    for h in t.handlers:
        typ = h.type
        for x in (typ.elts if isinstance(typ, ast.Tuple) else [typ] if typ is not None else []):
            if isinstance(x, ast.Name) and x.id in ("NameError", "UnboundLocalError"):
                return True
    return False


class _Loads:
    """Every Name load with the scope it is evaluated in, the functions around it, the comprehension variables
    in force, and whether a NameError handler guards it. Annotations are skipped."""

    def __init__(self) -> None:
        self.out: list[tuple[ast.Name, tuple, tuple, bool]] = []

    def visit(self, node, scopes: tuple, funcs: tuple, comp: frozenset, guarded: bool) -> None:
        if isinstance(node, _FUNCS):
            for x in [*node.decorator_list, *node.args.defaults, *(d for d in node.args.kw_defaults if d)]:
                self.visit(x, scopes, funcs, comp, guarded)
            for x in node.body:
                self.visit(x, scopes + (node,), funcs + (node,), comp, False)
            return
        if isinstance(node, ast.Lambda):
            for x in [*node.args.defaults, *(d for d in node.args.kw_defaults if d)]:
                self.visit(x, scopes, funcs, comp, guarded)
            self.visit(node.body, scopes + (node,), funcs, comp, guarded)
            return
        if isinstance(node, ast.ClassDef):
            for x in [*node.decorator_list, *node.bases, *(k.value for k in node.keywords)]:
                self.visit(x, scopes, funcs, comp, guarded)
            for x in node.body:
                self.visit(x, scopes + (node,), funcs, comp, False)
            return
        if type(node) in _COMPS:
            gens = node.generators
            self.visit(gens[0].iter, scopes, funcs, comp, guarded)        # evaluated in the enclosing scope
            bound = set()
            for g in gens:
                bound.update(x.id for x in ast.walk(g.target) if isinstance(x, ast.Name))
            inner, sc = comp | bound, scopes + (node,)
            for k, g in enumerate(gens):
                if k:
                    self.visit(g.iter, sc, funcs, inner, guarded)
                self.visit(g.target, sc, funcs, inner, guarded)
                for x in g.ifs:
                    self.visit(x, sc, funcs, inner, guarded)
            for x in ([node.key, node.value] if isinstance(node, ast.DictComp) else [node.elt]):
                self.visit(x, sc, funcs, inner, guarded)
            return
        if isinstance(node, _TRY):
            g = guarded or _catches_nameerror(node)
            for x in node.body:
                self.visit(x, scopes, funcs, comp, g)
            for x in [*node.handlers, *node.orelse, *node.finalbody]:
                self.visit(x, scopes, funcs, comp, guarded)
            return
        if isinstance(node, ast.AnnAssign):
            for x in (node.target, node.value):
                if x is not None:
                    self.visit(x, scopes, funcs, comp, guarded)
            return
        if isinstance(node, ast.arg):
            return
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if funcs and node.id not in comp and not guarded:
                self.out.append((node, scopes, funcs, guarded))
            return
        for x in ast.iter_child_nodes(node):
            self.visit(x, scopes, funcs, comp, guarded)


def _scope_key(node) -> tuple[str, int]:
    if isinstance(node, (*_FUNCS, ast.ClassDef)):
        return node.name, node.lineno
    if isinstance(node, ast.Lambda):
        return "lambda", node.lineno
    return _COMPS[type(node)], node.lineno


def _start(fn) -> int:
    return min([fn.lineno, *(d.lineno for d in fn.decorator_list)])


def check_source(src: bytes | str, path: str = "<src>", changed: set[int] | None = None,
                 removed: set[str] | frozenset = frozenset()) -> tuple[list[dict], str | None]:
    """(hits, why the file was not checked). `changed`: the new-side line numbers the run touched (None = the
    whole file is new); `removed`: module-level names the run took away, reported in any function."""
    try:
        text = _decode(src)
        tree = ast.parse(text, path)
        top = symtable.symtable(text, path, "exec")
    except (SyntaxError, ValueError, UnicodeError) as e:
        return [], f"unparsed: {type(e).__name__} line {getattr(e, 'lineno', '?')}"
    why = _dynamic(tree)
    if why:
        return [], why
    defined = module_names(tree, top) | KNOWN
    cands = _candidates(top)
    walker = _Loads()
    for x in tree.body:
        walker.visit(x, (), (), frozenset(), False)
    hits, seen = [], set()
    for name, scopes, funcs, _ in walker.out:
        if name.id in defined or (name.lineno, name.id) in seen:
            continue
        resolved = None
        for sc in reversed(scopes):            # an inlined comprehension (3.12+) has no table of its own
            resolved = cands.get(_scope_key(sc))
            if resolved is not None:
                break
        if not resolved or name.id not in resolved:
            continue
        if changed is not None and name.id not in removed and not any(
                any(_start(f) <= ln <= (f.end_lineno or f.lineno) for ln in changed) for f in funcs):
            continue
        seen.add((name.lineno, name.id))
        hits.append({"file": path, "line": name.lineno, "func": funcs[-1].name, "name": name.id})
    return sorted(hits, key=lambda h: (h["line"], h["name"])), None


def defined_names(src: bytes | str) -> set[str]:
    """Module-level names of a source (empty if it does not parse)."""
    try:
        text = _decode(src)
        return module_names(ast.parse(text), symtable.symtable(text, "<old>", "exec"))
    except (SyntaxError, ValueError, UnicodeError):
        return set()


def scan(cwd: Path, snap: dict | None, names: list[str] | None = None, diff: str | None = None) -> dict:
    """Check the .py files a run changed since its undo snapshot. `names`/`diff`: what review.changes() returned
    already (saves the git calls)."""
    from . import review as rv
    t0 = time.perf_counter()
    out: dict = {"hits": [], "files": 0}
    if not snap:
        out["skipped"] = "no undo snapshot (not a git repo?)"
        return out
    if names is None or diff is None:
        names, diff = rv.changes(cwd, snap)
    per = rv._per_file(diff)
    repo = Path(snap.get("repo") or cwd)
    notes = []
    for n in names:
        if not n.endswith(".py"):
            continue
        f = next((x for x in (repo / n, Path(cwd) / n) if x.is_file()), None)
        if f is None:
            continue                                       # deleted
        try:
            data = f.read_bytes()
        except OSError:
            continue
        old = rv._git(repo, "show", f"{snap['base']}:{n.replace(chr(92), '/')}") if snap.get("base") else ""
        if old:
            lines = set(per.get(n) or per.get(n.replace("\\", "/")) or [])
            if not lines:
                continue
            removed = defined_names(old) - defined_names(data)
        else:
            lines, removed = None, set()                  # new file: every function is the run's
        out["files"] += 1
        hits, why = check_source(data, n.replace("\\", "/"), lines, removed)
        out["hits"] += hits
        if why:
            notes.append(f"{n}: {why}")
    if notes:
        out["not_checked"] = notes[:10]
    out["hits"] = out["hits"][:20]
    out["ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return out


def line(h: dict) -> str:
    return f"{h['file']}:{h['line']} {h['func']}() uses undefined name '{h['name']}'"


def for_run(req, cfg: dict, p, record: dict, cwd: Path) -> dict | None:
    """The check for a finished write run (None when off or not a write run). Never raises."""
    m = mode(req, cfg)
    if m == "off" or getattr(req, "mode", "write") != "write" or getattr(req, "ephemeral", False):
        return None
    try:
        from .workspace import run_snapshot
        res = scan(Path(cwd), run_snapshot(p, record))
    except Exception as e:  # noqa: BLE001 — a static check never breaks the run
        res = {"hits": [], "files": 0, "error": f"{type(e).__name__}: {e}"[:200]}
    res["mode"] = m
    return res


def as_check(nc: dict, cmd: str | None) -> dict:
    """mode fail: the record's `check` for a hit, read by everything that already knows check_failed."""
    tail = "\n".join(line(h) for h in nc["hits"])
    return {"cmd": "ccx namecheck", "passed": False, "exit": 1, "reason": "namecheck", "tail": tail,
            "duration_sec": round(nc.get("ms", 0) / 1000, 3), **({"not_run": cmd} if cmd else {})}


def brief_note(nc: dict | None) -> str:
    """For the reviewer: weak evidence, to confirm or dismiss."""
    if not nc or not nc.get("hits"):
        return ""
    return ("\nA static check (ccx namecheck, weak evidence: confirm by reading the code) found names that no "
            "scope defines in the changed functions:\n" + "".join(f"- {line(h)}\n" for h in nc["hits"][:8]))
