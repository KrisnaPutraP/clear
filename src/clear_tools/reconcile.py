"""reconcile_documents (docs/PLAN.md §4b, §5a).

Deterministic. The LLM extracts fields from each shipping document and passes
them in with source quotes; this tool compares them in code, with each other
and with the purchase order, and returns the discrepancies and the missing
documents.
"""
