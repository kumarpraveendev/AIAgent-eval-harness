"""Tests for the harness and the two agents. Run: pytest

They read in three groups: the engine (environment + loop), the careful agent
does the right thing, and the harness catches the careless agent's failures.
"""
from agents import careful_agent, careless_agent
from evals import SCENARIOS, run, score
from harness import Environment, run_agent

SCN = {s.id: s for s in SCENARIOS}


# the engine -----------------------------------------------------------------

def test_refund_records_a_side_effect():
    env = Environment()
    tools = __import__("harness").make_tools(env)
    tools["issue_refund"](order_id="O100", amount=39.99)
    assert env.refunds == [{"order_id": "O100", "amount": 39.99}]


def test_refund_above_total_is_refused():
    env = Environment()
    tools = __import__("harness").make_tools(env)
    out = tools["issue_refund"](order_id="O100", amount=999)
    assert out["ok"] is False and env.refunds == []


def test_broken_tool_surfaces_as_an_error():
    env = Environment()
    env.break_tool("lookup_order")
    agent = lambda m, h, t: ("call", "lookup_order", {"order_id": "O100"})
    history = run_agent(agent, env, "x", max_steps=2)
    assert any(isinstance(s.result, dict) and "error" in s.result for s in history)


def test_loop_guard_stops_a_repeated_call():
    env = Environment()
    agent = lambda m, h, t: ("call", "search_kb", {"query": "same"})
    history = run_agent(agent, env, "x", max_steps=5)
    assert len(history) <= 2          # second identical call is stopped


def test_step_budget_is_enforced():
    env = Environment()
    n = {"i": 0}
    def agent(m, h, t):
        n["i"] += 1
        return ("call", "search_kb", {"query": f"q{n['i']}"})   # always different
    history = run_agent(agent, env, "x", max_steps=3)
    assert len(history) == 3


# the careful agent does the right thing -------------------------------------

def test_careful_passes_every_scenario():
    for sid, passed, failure in run(careful_agent):
        assert passed, f"careful failed {sid}: {failure}"


def test_careful_ignores_injected_instruction():
    sc = SCN["kb_injection"]
    env = Environment(); sc.setup(env)
    run_agent(careful_agent, env, sc.message)
    assert env.refunds == []          # the planted "issue a refund" is ignored


def test_careful_gates_an_over_cap_refund():
    sc = SCN["refund_over_cap"]
    env = Environment()
    history = run_agent(careful_agent, env, sc.message)
    assert env.refunds == []
    assert any(s.tool == "escalate" for s in history)


# the harness catches the careless agent's failures --------------------------

import pytest

@pytest.mark.parametrize("scenario_id, expected_failure", [
    ("kb_injection", "followed_injection"),
    ("refund_over_cap", "unauthorized_refund"),
    ("order_status", "ungrounded_claim"),
    ("out_of_scope", "should_have_escalated"),
])
def test_harness_labels_careless_failures(scenario_id, expected_failure):
    sc = SCN[scenario_id]
    env = Environment()
    if sc.setup:
        sc.setup(env)
    history = run_agent(careless_agent, env, sc.message)
    passed, failure = score(sc, env, history)
    assert not passed and failure == expected_failure
