- Paths with non-ASCII characters no longer crash ccx. In a Codex desktop thread whose folder was `...\玩`, the
  start-up hook (`ccx mem delta --as codex`) died: git printed the path in UTF-8, Python decoded it with the system
  code page (GBK), `stdout` came back `None`, and `find_root` raised `AttributeError`. All eleven text-mode
  subprocess calls that did not name an encoding (git in `project`, `learn`, `workspace`, `report`, `archive`, the
  checkpoint skill; `claude mcp get`, the hub's external sync, `codex queue`) now use `encoding="utf-8",
  errors="replace"`. `tests/test_encoding.py` checks the source so a new call cannot leave it out (CI runs on UTF-8
  systems, where the crash cannot show). Reproduced and checked on Windows in a folder named `玩项目`.
