"""B-1 fuzz corpus: every model-controlled field on the claims path.

The inventory below is the audit table from the improvement
program (Phase 1, claim B-1): each field a model can influence at
the claims-bundle boundary, with the disposition the audit found.
The corpus exercises every field with type confusions — a
malformed shape must surface as DeltaFormatError (a model outcome
fed back in-phase), never as an unhandled AttributeError /
TypeError / KeyError, never as a silently accepted wrong shape,
and never as a study halt. Case zero is the Stage B attempt-8
submission (16 plain-string evidence entries across 7 claims in a
delta), the defect that halted a study on 2026-10-23.

The meta-test at the bottom fails if the inventory names a field
this corpus does not exercise.
"""
import pytest

from benchmark_runner.store import Store
from benchmark_runner.workflow import (
    DeltaFormatError, executed_tests, grounded_claims,
    merge_claim_delta, resolve_claim_submission)


def valid_claim(**overrides):
    claim = {
        "id": "c1",
        "kind": "assertion",
        "statement": "The widget compiles.",
        "falsification_tests": ["pytest -k widget"],
        "evidence": [],
    }
    claim.update(overrides)
    return claim


def valid_bundle(**claim_overrides):
    return {"claims": [valid_claim(**claim_overrides)]}


def resolve(submission, base=None):
    return resolve_claim_submission(base, submission)


# --- Case zero: the attempt-8 delta -------------------------------------

def attempt8_delta():
    standing = {"claims": [
        {"id": f"c{i}", "kind": "assertion", "statement": f"s{i}",
         "evidence": []} for i in range(7)]}
    upserts = []
    strings = [f"evidence-string-{i}" for i in range(16)]
    for i in range(7):
        upserts.append({"id": f"c{i}", "kind": "assertion",
                        "statement": f"s{i}",
                        "evidence": strings[i::7]})
    return standing, {"delta": {"upsert": upserts}}


def test_case_zero_attempt8_delta_is_a_model_outcome():
    standing, submission = attempt8_delta()
    with pytest.raises(DeltaFormatError):
        resolve(submission, base=standing)


def test_case_zero_attempt8_full_bundle_is_a_model_outcome():
    _, submission = attempt8_delta()
    bundle = {"claims": submission["delta"]["upsert"]}
    with pytest.raises(DeltaFormatError):
        resolve(bundle)


# --- The malformed battery ------------------------------------------------
# Each case: (inventory field, builder of a full-bundle submission
# carrying the malformed shape). Every one must be refused at the
# boundary with DeltaFormatError.

def _claim_without(key):
    claim = valid_claim()
    del claim[key]
    return {"claims": [claim]}


MALFORMED = [
    ("claim.entry", lambda: {"claims": ["just-a-string"]}),
    ("claim.entry", lambda: {"claims": [None]}),
    ("claim.id", lambda: _claim_without("id")),
    ("claim.id", lambda: valid_bundle(id=None)),
    ("claim.id", lambda: valid_bundle(id="")),
    ("claim.id", lambda: valid_bundle(id=7)),
    ("claim.id", lambda: valid_bundle(id=["c1"])),
    ("claim.id", lambda: valid_bundle(id={"x": 1})),
    ("claim.falsification_tests",
     lambda: valid_bundle(falsification_tests="pytest -k widget")),
    ("claim.falsification_tests",
     lambda: valid_bundle(falsification_tests={"t": 1})),
    ("claim.evidence", lambda: valid_bundle(evidence={"not": "a list"})),
    ("claim.evidence", lambda: valid_bundle(evidence="not-a-list")),
    ("evidence.entry", lambda: valid_bundle(evidence=["a-string"])),
    ("evidence.entry", lambda: valid_bundle(evidence=[None])),
    ("evidence.source_id",
     lambda: valid_bundle(evidence=[{"source_id": ["a", "b"]}])),
    ("evidence.source_id",
     lambda: valid_bundle(evidence=[{"source_id": {"a": 1}}])),
    ("evidence.source_id",
     lambda: valid_bundle(evidence=[{"source_id": 42}])),
    ("evidence.ref", lambda: valid_bundle(evidence=[{"ref": ["p"]}])),
    ("evidence.description",
     lambda: valid_bundle(evidence=[{"description": 5}])),
    ("evidence.description",
     lambda: valid_bundle(evidence=[{"description": ["x"]}])),
    ("evidence.kind", lambda: valid_bundle(evidence=[{"kind": {}}])),
    ("evidence.source_quality",
     lambda: valid_bundle(evidence=[{"source_quality": 1}])),
]


@pytest.mark.parametrize("field,build", MALFORMED,
                         ids=[f"{f}-{i}" for i, (f, _) in
                              enumerate(MALFORMED)])
def test_malformed_full_bundle_refused_at_boundary(field, build):
    with pytest.raises(DeltaFormatError):
        resolve(build())


# --- The same shapes at the other boundaries ------------------------------

def test_grounded_claims_refuses_unhashable_source_id(tmp_path):
    bundle = valid_bundle(evidence=[{"source_id": ["a"]}])
    with pytest.raises(DeltaFormatError):
        grounded_claims(bundle, Store(tmp_path), "attempt-1")


def test_executed_tests_self_validates(tmp_path):
    bundle = {"claims": [{"kind": "assertion", "evidence": []}]}
    with pytest.raises(DeltaFormatError):
        executed_tests(bundle, Store(tmp_path), "attempt-1")


def test_delta_upsert_id_must_be_a_string():
    standing = valid_bundle()
    bad = {"delta": {"upsert": [{"id": ["c9"], "kind": "assertion"}]}}
    with pytest.raises(DeltaFormatError):
        merge_claim_delta(standing, bad)
    bad2 = {"delta": {"upsert": [{"id": 0, "kind": "assertion"}]}}
    with pytest.raises(DeltaFormatError):
        merge_claim_delta(standing, bad2)


# --- Controls: valid shapes, including hostile content, pass --------------

def test_valid_bundle_flows_through_all_boundaries(tmp_path):
    bundle = valid_bundle(evidence=[{
        "kind": "observed", "source_id": "deadbeef", "ref": "x/y.json",
        "description": "saw it", "source_quality": "test"}])
    resolved = resolve(bundle)
    store = Store(tmp_path)
    grounded = grounded_claims(resolved, store, "attempt-1")
    assert grounded["claims"][0]["id"] == "c1"
    assert executed_tests(resolved, store, "attempt-1") == {}


def test_hostile_unicode_and_oversized_valid_fields_pass():
    nasty = "🔥\x00claim — ünïcode " + "x" * 200_000
    bundle = valid_bundle(statement=nasty,
                          evidence=[{"description": nasty}])
    resolved = resolve(bundle)
    assert resolved["claims"][0]["statement"] == nasty


def test_optional_fields_may_be_absent():
    claim = {"id": "c1", "kind": "assertion"}
    assert resolve({"claims": [claim]})["claims"][0]["id"] == "c1"
    claim2 = valid_claim(evidence=[{"source_id": "abc"}])
    assert resolve({"claims": [claim2]})


def test_grounding_join_accepts_id_less_harness_bundles(tmp_path):
    # The id requirement is scoped to the boundaries whose joins
    # key claims by id (submission resolution, executed tests).
    # The grounding join does not consume ids, and harness-built
    # id-less bundles are a suite-pinned legitimate input to it
    # (tests/test_workflow.py) — shapes are still validated there.
    bundle = {"claims": [{"evidence": [{
        "ref": "objects/x", "source_id": "abc", "kind": "observed",
        "source_quality": "test"}]}]}
    grounded = grounded_claims(bundle, Store(tmp_path), "attempt-1")
    assert grounded["claims"][0]["evidence"][0]["kind"] == "asserted"
    # Evidence shapes are still enforced at the grounding join.
    with pytest.raises(DeltaFormatError):
        grounded_claims(
            {"claims": [{"evidence": [{"source_id": ["x"]}]}]},
            Store(tmp_path), "a")


def test_delta_keyed_upsert_form_still_merges():
    standing = valid_bundle()
    submission = {"delta": {"upsert": {"c2": valid_claim(id="c2")}}}
    merged = merge_claim_delta(standing, submission)
    assert [c["id"] for c in merged["claims"]] == ["c1", "c2"]


# --- Inventory coverage -----------------------------------------------------

INVENTORY_FIELDS = {
    "claim.entry", "claim.id", "claim.falsification_tests",
    "claim.evidence", "evidence.entry", "evidence.source_id",
    "evidence.ref", "evidence.description", "evidence.kind",
    "evidence.source_quality",
}


def test_corpus_covers_the_inventory():
    covered = {field for field, _ in MALFORMED}
    assert covered == INVENTORY_FIELDS, (
        f"inventory fields without a corpus case: "
        f"{INVENTORY_FIELDS - covered}; corpus cases without an "
        f"inventory field: {covered - INVENTORY_FIELDS}")
