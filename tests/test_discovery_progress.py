from scripts.discovery_progress import catalog_fingerprint, reconcile_progress


def test_catalog_fingerprint_tracks_ordered_dataset_ids():
    items = [{"id": "a"}, {"id": "b"}]
    assert catalog_fingerprint(items) == catalog_fingerprint(items)
    assert catalog_fingerprint(items) != catalog_fingerprint(items[::-1])

def test_stale_out_of_range_indexes_reset_even_if_count_matches():
    old = {"batch_count": 50, "catalog_fingerprint": "same", "successful_batches": [111],
           "failed_batches": [5, 170], "blocked_batches": [0, 75]}
    state, reset = reconcile_progress(old, 50, "same")
    assert reset
    assert state["successful_batches"] == state["failed_batches"] == state["blocked_batches"] == []
    assert state["next_batch"] == 0

def test_changed_catalog_resets_indexes_when_batch_count_is_unchanged():
    old = {"batch_count": 50, "catalog_fingerprint": "old", "successful_batches": [1, 2],
           "failed_batches": [], "blocked_batches": []}
    state, reset = reconcile_progress(old, 50, "new")
    assert reset and state["successful_batches"] == []

def test_same_catalog_preserves_valid_progress():
    old = {"batch_count": 3, "catalog_fingerprint": "stable", "successful_batches": [0, 2],
           "failed_batches": [1], "blocked_batches": [], "completed_batches": 2}
    state, reset = reconcile_progress(old, 3, "stable")
    assert not reset
    assert state["successful_batches"] == [0, 2]
    assert state["failed_batches"] == [1]

def test_legacy_progress_without_fingerprint_resets():
    state, reset = reconcile_progress({"batch_count": 3, "successful_batches": [0]}, 3, "new")
    assert reset and state["successful_batches"] == []
