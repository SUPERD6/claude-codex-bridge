"""Never let a test find a real agent CLI on its own (e.g. a desktop app's bundled dsh from the registry): tests
run the fakes in tests/fakes only. Set before any test, so the ccx processes the tests start inherit it."""
import os

os.environ["CCX_NO_LOCATE"] = "1"
