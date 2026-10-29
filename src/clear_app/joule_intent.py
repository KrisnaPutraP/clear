"""What a planner means in a Joule message, read by Claude in SAP AI Core.

The model gets the message together with the open cases, the transfers
awaiting approval, and the prepared events, and returns a structured intent.
It decides nothing: an approval or a rejection only leads to a preview, and
only a confirmation that carries a code CLEAR issued executes it
(clear_app.joule). When the model fails or takes longer than TIMEOUT_SECONDS,
the caller falls back to the keyword rules.
"""

import concurrent.futures
import json
from typing import Literal

from pydantic import BaseModel, Field
from strands import Agent

TIMEOUT_SECONDS = 20  # Joule waits 60 s for the whole answer.

PROMPT = """You read one message that a supply planner wrote to CLEAR in SAP Joule, and say what the planner wants.
CLEAR resolves exceptions on inbound shipments: it investigates, proposes a stock transfer, and waits for the
planner to approve or reject it. The message may be in English or Indonesian.

Choose exactly one kind:
- approve: the planner clearly tells you to approve a transfer now.
- reject: the planner clearly tells you to reject a transfer now.
- hold: the planner tells you not to approve or reject yet, to wait, or to cancel a decision
  ("do not approve", "not yet", "wait for customs", "cancel", "jangan dulu", "tunggu").
- question: the planner asks whether or why to do something, or asks about the plan, its numbers, or its
  evidence ("should I approve?", "why not transfer everything?").
- decisions: the planner asks what needs their decision or approval, or what is pending.
- list: the planner asks to list or show the cases.
- status: the planner asks for the status or progress of a shipment or a case.
- details: the planner asks for the full evidence, rationale, or assessed options.
- start: the planner asks to work an event from the feed, or reports a new exception on a shipment.
- help: anything else, or you are not sure.

Rules:
- A negation, a question, a condition, or a future intention is never approve or reject.
- Use only IDs from the context below; never invent one. Leave an ID empty when the message does not
  name it and the context does not make it unambiguous. When exactly one transfer is awaiting approval and
  the message refers to "the transfer", use its validation ID.
- For reject, put the planner's reason, translated to English, in reason; leave it empty if they gave none.
"""


class Intent(BaseModel):
    """What the planner wants, read from one Joule message."""

    kind: Literal["approve", "reject", "hold", "question", "decisions", "list", "status", "details", "start",
                  "help"] = Field(description="The single kind that fits the message, by the rules")
    validation_id: str | None = Field(None, description="VAL-…, only from the transfers awaiting approval")
    case_id: str | None = Field(None, description="CASE-…, only from the cases in the context")
    shipment_id: str | None = Field(None, description="SHP-…, only from the cases or events in the context")
    event_id: str | None = Field(None, description="An event ID from the feed, only for start")
    reason: str | None = Field(None, description="For reject: the planner's reason in English")


class ClaudeUnderstanding:
    """Reads a message with the LLM; returns None when the model fails or is too slow."""

    def __init__(self, model_for, timeout: float = TIMEOUT_SECONDS):
        self.model_for, self.timeout = model_for, timeout
        self._pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)

    def __call__(self, text: str, context: dict) -> Intent | None:
        future = self._pool.submit(self._read, text, context)
        try:
            return future.result(timeout=self.timeout)
        except Exception:  # A slow or failing model must not cost the planner the answer.
            return None

    def _read(self, text: str, context: dict) -> Intent:
        agent = Agent(model=self.model_for("intent"), system_prompt=PROMPT, callback_handler=None)
        prompt = f"Context:\n{json.dumps(context, indent=1)}\n\nPlanner's message:\n{text}"
        return agent(prompt, structured_output_model=Intent).structured_output
