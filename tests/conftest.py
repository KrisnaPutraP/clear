"""Shared fixtures: every test gets its own runtime copy of the committed seed."""

import re
from pathlib import Path

import pytest

from clear_tools.store import JsonStore, reset_runtime

SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "seed"

# Labelled lines in the generated documents, standing in for LLM extraction.
_LABELS = {
    "purchase_order": re.compile(r"Buyer PO No\.:?\s*(\d+)"),
    "material": re.compile(r"Buyer Material No\.:\s*(\S+)"),
    "quantity": re.compile(r"Quantity:\s*([\d,]+(?:\.\d+)?)\s*(MT)\b"),
}


@pytest.fixture
def store(tmp_path):
    runtime = tmp_path / "runtime"
    reset_runtime(SEED_DIR, runtime)
    return JsonStore(runtime)


@pytest.fixture
def extract():
    """A function that extracts fields from get_documents() output the way a
    correct LLM extraction would: the value plus the exact source line."""

    def run(bundle: dict) -> list[dict]:
        extractions = []
        for document in bundle["documents"]:
            for line in document["text"].splitlines():
                for field, pattern in _LABELS.items():
                    match = pattern.search(line)
                    if not match:
                        continue
                    extraction = {"document_type": document["document_type"], "field": field,
                                  "value": match.group(1), "quote": line.strip()}
                    if field == "quantity":
                        extraction["value"] = float(match.group(1).replace(",", ""))
                        extraction["unit"] = match.group(2)
                    extractions.append(extraction)
        return extractions

    return run
