"""CLEAR agents: an orchestrator and three specialists on Strands (docs/PLAN.md §2).

The orchestrator (case manager) holds no business tools; it delegates to the
Evidence, Impact & Options, and Action specialists, which call the
deterministic tools in clear_tools. Only the Action agent holds the write
tool. Every step is written to the case log through Strands hooks.
"""
