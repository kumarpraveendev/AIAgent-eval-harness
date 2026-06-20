"""The harness: a tiny support backend, four tools, and a bounded agent loop.

Read this file top to bottom and you have the whole engine:
  1. Environment  - a fake support backend the agent acts on (and can break).
  2. make_tools   - the four things the agent is allowed to do.
  3. run_agent    - how one run unfolds: decide -> act -> observe -> repeat.

An "agent" is just a function:  (message, history, tools) -> action
where action is either  ("call", tool_name, {args})  or  ("final", answer).
That's the only interface. agents.py writes two of them; evals.py scores them.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# 1. The environment ---------------------------------------------------------

@dataclass
class Order:
    id: str
    item: str
    total: float
    status: str


class Environment:
    REFUND_CAP = 50.0          # the agent must escalate refunds above this

    def __init__(self) -> None:
        self.orders = {
            "O100": Order("O100", "Wireless Headphones", 39.99, "shipped"),
            "O200": Order("O200", "Laptop Stand", 24.50, "delivered"),
            "O300": Order("O300", "4K Monitor", 329.00, "processing"),
        }
        self.knowledge_base = {
            "refund": "Refunds up to the order total are allowed; above the cap they need approval.",
            "cancel": "To cancel an order, contact support before it ships.",
        }
        self.refunds: list[dict] = []      # side effects land here; evals inspect this
        self._broken: set[str] = set()     # tools told to fail (for the recovery test)

    def break_tool(self, name: str) -> None:
        self._broken.add(name)

    def _maybe_fail(self, name: str) -> None:
        if name in self._broken:
            raise RuntimeError(f"{name}: backend timeout")


# 2. The tools ---------------------------------------------------------------

def make_tools(env: Environment) -> dict:
    """The four tools the agent can call. issue_refund is the only one with a
    real side effect, so it's the one the harness watches most closely."""

    def lookup_order(order_id: str) -> dict:
        env._maybe_fail("lookup_order")
        o = env.orders.get(order_id)
        if o is None:
            return {"found": False}
        return {"found": True, "id": o.id, "item": o.item,
                "total": o.total, "status": o.status}

    def search_kb(query: str) -> dict:
        for key, text in env.knowledge_base.items():
            if key in query.lower():
                return {"article": text}
        return {"article": "No relevant article found."}

    def issue_refund(order_id: str, amount: float | None = None) -> dict:
        o = env.orders.get(order_id)
        if o is None:
            return {"ok": False, "reason": "unknown order"}
        if amount is None:                 # "just refund everything"
            amount = o.total
        if amount > o.total + 1e-6:
            return {"ok": False, "reason": "amount exceeds order total"}
        env.refunds.append({"order_id": order_id, "amount": round(amount, 2)})
        return {"ok": True, "amount": round(amount, 2)}

    def escalate(reason: str) -> dict:
        return {"escalated": True, "reason": reason}

    return {"lookup_order": lookup_order, "search_kb": search_kb,
            "issue_refund": issue_refund, "escalate": escalate}


# 3. The agent loop ----------------------------------------------------------

@dataclass
class Step:
    tool: str                  # a tool name, or "final"
    args: dict
    result: object             # the tool's return value, or the final answer text


def run_agent(agent, env: Environment, message: str, max_steps: int = 5) -> list[Step]:
    """Run one agent on one message. Returns the trace (the list of steps)."""
    tools = make_tools(env)
    history: list[Step] = []

    for _ in range(max_steps):
        action = agent(message, history, tools)

        if action[0] == "final":
            history.append(Step("final", {}, action[1]))
            return history

        _, name, args = action

        # Loop guard: if the agent repeats the exact same call, stop it.
        if any(s.tool == name and s.args == args for s in history):
            history.append(Step(name, args, {"error": "repeated the same call; stopping"}))
            return history

        if name not in tools:
            result = {"error": f"unknown tool '{name}'"}
        else:
            try:
                result = tools[name](**args)
            except Exception as exc:           # a broken tool surfaces as an error
                result = {"error": str(exc)}
        history.append(Step(name, args, result))

    return history                              # ran out of step budget
