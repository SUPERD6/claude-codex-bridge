"""What the sub-agent is told about testing (round 5c: in-process tests that missed broken wiring, an existing
regression test edited to fit a misreading)."""
from ccx import prompts


def _first(selfcheck):
    return prompts.PROMPT.format(run_id="r1", caller="lead", cwd="/w", mode_text="write", context_line="",
                                 memory_line="", brief="do x", selfcheck=selfcheck)


def test_selfchecks_ask_to_test_through_the_named_command_from_outside_the_repo():
    for text in (prompts.SELFCHECK, prompts.SELFCHECK_CMD.format(check="pytest -q tests/test_x.py")):
        assert "separate process from a directory outside the repository" in text
        assert "in-process does not test the wiring" in text
        assert "wait for its effect" in text
        assert "only the relevant test files" in text
    assert "`pytest -q tests/test_x.py`" in prompts.SELFCHECK_CMD.format(check="pytest -q tests/test_x.py")


def test_existing_tests_rule_reaches_first_follow_up_and_continue_prompts():
    rule = "do not change what an existing test sets up or asserts"
    first = _first(prompts.SELFCHECK)
    assert rule in first.split("## Task")[0]                    # on the Rules lines, before the task
    assert rule in prompts.FOLLOWUP.format(run_id="r1", brief="again")
    assert rule in prompts.CONTINUE.format(run_id="r1", caller="lead", cwd="/w", mode_text="write",
                                           brief="next", selfcheck=prompts.SELFCHECK)
    assert "satisfy both" in prompts.KEEP_TESTS and "say why" in prompts.KEEP_TESTS


def test_added_wording_stays_short():
    assert len(prompts.KEEP_TESTS) < 220 and len(prompts.WIRING) < 400


def test_selfchecks_ask_for_targeted_runs_and_one_full_check_at_the_end():
    cmd = prompts.SELFCHECK_CMD.format(check="pytest -q tests")
    for text in (prompts.SELFCHECK, cmd):
        assert "targeted" in text and "-x" in text and "-k NAME" in text
    assert "run the full check at most once, at the end" in cmd
    assert "not the whole check" in cmd and "outside your sandbox" in cmd and "one test id" in cmd


def test_review_fix_round_asks_for_targeted_tests_not_the_whole_check():
    import inspect
    from ccx import delegate
    src = inspect.getsource(delegate)
    assert "run the checks again" not in src
    assert "re-run only the tests touching" in src and "not the whole check, ccx runs that itself" in src
