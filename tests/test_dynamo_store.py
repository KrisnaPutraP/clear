"""The DynamoDB store (docs/PLAN.md §4c) is a drop-in for JsonStore: same reads, same writes,
and the scenarios run unchanged on it. Uses an in-memory table checked against the DynamoDB API."""

import pytest

from aws_fakes import SEED_DIR, FakeDynamo
from clear_agents.testing import ScriptedDirector
from clear_app.contract import Clear
from clear_aws.dynamo_store import ConcurrentWriteError, DynamoStore, reset_table


@pytest.fixture
def dynamo():
    return FakeDynamo()


@pytest.fixture
def dynamo_store(dynamo):
    store = DynamoStore("cookusan-hackathon-clear-data", dynamo)
    reset_table(SEED_DIR, store)
    return store


def test_reset_loads_every_seed_file_and_reads_match_the_files(dynamo_store, store):
    seed_files = {p.relative_to(SEED_DIR).as_posix() for p in SEED_DIR.rglob("*") if p.is_file()}

    assert dynamo_store.names() == seed_files
    assert dynamo_store.read("logistics/shipments") == store.read("logistics/shipments")
    assert dynamo_store.read("records/case_log") == []
    document = "documents/SHP-1001/packing_list.txt"
    assert dynamo_store.read_text(document) == store.read_text(document)
    history = "history/exception_history_train.csv"
    assert dynamo_store.read_csv(history) == store.read_csv(history)
    assert dynamo_store.exists(document)
    assert not dynamo_store.exists("documents/SHP-1001/missing.txt")
    with pytest.raises(FileNotFoundError):
        dynamo_store.read("records/unknown")


def test_reset_removes_items_that_are_not_in_the_seed(dynamo_store):
    dynamo_store.write("records/extra", [1])

    reset_table(SEED_DIR, dynamo_store)

    assert "records/extra.json" not in dynamo_store.names()


def test_a_write_fails_when_another_writer_changed_the_item(dynamo, dynamo_store):
    other = DynamoStore(dynamo_store.table, dynamo)  # Another process, e.g. the runtime.
    cases = dynamo_store.read("records/cases")
    other.write("records/cases", other.read("records/cases") + [{"case_id": "CASE-0001"}])

    with pytest.raises(ConcurrentWriteError):
        dynamo_store.write("records/cases", cases + [{"case_id": "CASE-0001"}])
    assert len(dynamo_store.read("records/cases")) == 1


def test_a_snapshot_serves_reads_from_one_scan_and_refuses_writes(dynamo, dynamo_store):
    dynamo.calls.clear()
    with dynamo_store.snapshot():
        shipments = dynamo_store.read("logistics/shipments")
        assert dynamo_store.exists("documents/SHP-1001/packing_list.txt")
        with pytest.raises(RuntimeError):
            dynamo_store.write("records/cases", [])

    assert shipments == dynamo_store.read("logistics/shipments")
    assert dynamo.calls[:4] == ["Scan", "Scan", "Scan", "GetItem"]  # 27 items in pages of 10, then a live read.


@pytest.mark.parametrize("event_id", ["S1-DOC-HOLD", "S2-CONGESTION"])
def test_scenarios_reach_the_same_outcome_on_dynamodb(dynamo_store, store, event_id):
    outcomes = []
    for backend in (store, dynamo_store):
        clear = Clear(backend, ScriptedDirector(backend))
        case = clear.get_case(clear.send_event(event_id, wait=True))
        log = clear.get_case_log(case["case_id"])
        outcomes.append((case["status"], case["plan"]["recommended_option"],
                         [(e["actor"], e["kind"], e.get("tool"), e["summary"]) for e in log]))

    assert outcomes[0] == outcomes[1]
