"""reset_runtime restores runtime state exactly from seed (docs/PLAN.md §4c)."""

import pytest

from clear_tools.store import reset_runtime


def make_seed(root):
    seed = root / "seed"
    (seed / "nested").mkdir(parents=True)
    (seed / "records.json").write_text('{"value": 1}')
    (seed / "nested" / "document.txt").write_text("text")
    return seed


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_reset_creates_runtime_identical_to_seed(tmp_path):
    seed = make_seed(tmp_path)
    runtime = tmp_path / "runtime"

    reset_runtime(seed, runtime)

    assert snapshot(runtime) == snapshot(seed)


def test_reset_discards_changes_made_during_a_run(tmp_path):
    seed = make_seed(tmp_path)
    runtime = tmp_path / "runtime"
    reset_runtime(seed, runtime)
    (runtime / "records.json").write_text('{"value": 2}')
    (runtime / "created_during_run.json").write_text("{}")

    reset_runtime(seed, runtime)

    assert snapshot(runtime) == snapshot(seed)


@pytest.mark.parametrize("runtime_rel", ["seed", "seed/runtime", "."])
def test_reset_refuses_overlapping_directories(tmp_path, runtime_rel):
    seed = make_seed(tmp_path)
    before = snapshot(seed)

    with pytest.raises(ValueError):
        reset_runtime(seed, tmp_path / runtime_rel)

    assert snapshot(seed) == before


def test_reset_keeps_runtime_when_seed_is_missing(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "records.json").write_text("{}")

    with pytest.raises(FileNotFoundError):
        reset_runtime(tmp_path / "missing", runtime)

    assert (runtime / "records.json").exists()
