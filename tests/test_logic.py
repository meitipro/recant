"""
Unit tests for the consensus logic, run with plain pytest. No GenVM needed.

WHY THIS FILE EXISTS
    The interesting part of this contract is not the prompt, it is the pure
    functions that decide whether two validators agreed and what a set of
    pointed-at rows actually means. Those functions are deliberately module
    level and side-effect free so they can be tested here, exhaustively, in
    milliseconds, without Studio or a network.

HOW IT LOADS THE CONTRACT
    A contract file cannot simply be imported: it starts with the GenVM
    dependency header and does `from genlayer import *`, which only resolves
    inside GenVM. So this file reads the real contract source and executes only
    the part above the storage section.

    That matters: these tests run against the exact code that ships. There is no
    second copy of the logic to drift out of sync.

    Run with:  pytest tests/test_logic.py -v
"""

import pathlib
import types

import pytest

CONTRACT = pathlib.Path(__file__).resolve().parent.parent / "contracts" / "recant.py"


def load_pure():
    """Execute the contract's pure helper section with genlayer stubbed out."""
    src = CONTRACT.read_text(encoding="utf-8")
    marker = "# Storage"
    assert marker in src, "contract is missing its storage section marker"
    head = src.split(marker)[0]
    head = "\n".join(
        line
        for line in head.splitlines()
        if not line.startswith("from genlayer import")
        and not line.startswith('# { "Depends"')
    )
    ns = {
        "allow_storage": (lambda c: c),
        "dataclass": (lambda c: c),
        "typing": __import__("typing"),
        "u256": int,
        "u8": int,
        "__name__": "pure_recant",
    }
    exec(compile(head, "recant.py", "exec"), ns)
    return types.SimpleNamespace(**ns)


R = load_pure()


# ===========================================================================
# parse_indices — the only place model output becomes structure
# ===========================================================================

class TestParseIndices:
    def test_none_is_empty(self):
        assert R.parse_indices("none") == []
        assert R.parse_indices("NONE") == []
        assert R.parse_indices("  none  ") == []
        assert R.parse_indices("") == []

    def test_a_single_index(self):
        assert R.parse_indices("3") == [3]

    def test_several_indices(self):
        assert R.parse_indices("3|7|0") == [3, 7, 0]

    def test_whitespace_is_forgiven(self):
        assert R.parse_indices(" 3 | 7 ") == [3, 7]

    @pytest.mark.parametrize(
        "raw",
        ["maybe", "3 and 7", "-1", "3.5", "3|", "|3", "3||7", "statement 3",
         "the third one", "3|three", None, "0x3"],
    )
    def test_anything_ambiguous_becomes_empty(self, raw):
        """A wrong index that looks plausible is far worse than no index,
        because it names an innocent statement."""
        assert R.parse_indices(raw) == []

    def test_duplicates_are_refused_outright(self):
        assert R.parse_indices("3|3") == []

    def test_more_entries_than_could_be_in_scope_is_refused(self):
        assert R.parse_indices("|".join(str(i) for i in range(40))) == []

    def test_zero_is_a_real_index(self):
        assert R.parse_indices("0") == [0]


# ===========================================================================
# in_scope
# ===========================================================================

class TestInScope:
    def test_inside(self):
        assert R.in_scope([0, 2], 3) is True

    def test_past_the_end(self):
        assert R.in_scope([3], 3) is False

    def test_negative(self):
        assert R.in_scope([-1], 3) is False

    def test_empty_is_always_in_scope(self):
        assert R.in_scope([], 0) is True


# ===========================================================================
# classify — the four outcomes are different facts, not degrees
# ===========================================================================

class TestClassify:
    def test_nothing_pointed_at_is_clear(self):
        assert R.classify([], [True, True]) == (R.CLEAR, [])

    def test_one_live_statement_is_a_contradiction(self):
        assert R.classify([1], [True, True]) == (R.CONTRADICTS, [1])

    def test_two_live_statements_is_a_conflict_in_the_record(self):
        v, ids = R.classify([0, 2], [True, True, True])
        assert v == R.CONFLICT and ids == [0, 2]

    def test_only_withdrawn_statements_is_stale(self):
        """Not an inconsistency at all. It is the author having already
        changed their mind, in public, on the record."""
        v, ids = R.classify([1], [True, False])
        assert v == R.STALE and ids == [1]

    def test_a_withdrawn_one_does_not_dilute_a_live_one(self):
        v, ids = R.classify([0, 1], [False, True])
        assert v == R.CONTRADICTS and ids == [1]

    def test_two_live_and_one_withdrawn_is_still_a_conflict(self):
        v, ids = R.classify([0, 1, 2], [True, False, True])
        assert v == R.CONFLICT and ids == [0, 2]

    def test_the_returned_ids_are_sorted(self):
        _v, ids = R.classify([2, 0], [True, True, True])
        assert ids == sorted(ids)

    def test_an_index_past_the_flags_is_treated_as_not_live(self):
        v, _ids = R.classify([5], [True])
        assert v == R.STALE

    def test_every_outcome_is_in_the_declared_set(self):
        for idx, flags in (([], []), ([0], [True]), ([0], [False]),
                           ([0, 1], [True, True]), ([0, 1], [True, False])):
            v, _ = R.classify(idx, flags)
            assert v in R.VERDICTS


# ===========================================================================
# structurally_sound — layer 1, free, before any prompt
# ===========================================================================

class TestStructurallySound:
    def test_a_clean_proposal(self):
        assert R.structurally_sound([1], 3, -1) is True

    def test_empty_is_sound(self):
        assert R.structurally_sound([], 3, -1) is True

    def test_out_of_range_is_not(self):
        assert R.structurally_sound([9], 3, -1) is False

    def test_negative_is_not(self):
        assert R.structurally_sound([-1], 3, -1) is False

    def test_a_statement_cannot_contradict_itself(self):
        assert R.structurally_sound([1], 3, 1) is False

    def test_duplicates_are_not_sound(self):
        assert R.structurally_sound([1, 1], 3, -1) is False


# ===========================================================================
# recant_agrees — the validator rule
# ===========================================================================

class TestRecantAgrees:
    def test_identical_indices_agree(self):
        mine = {"indices": [1]}
        assert R.recant_agrees(mine, {"indices": "1"}, 3, -1) is True

    def test_both_finding_nothing_agree(self):
        mine = {"indices": []}
        assert R.recant_agrees(mine, {"indices": "none"}, 3, -1) is True

    def test_order_does_not_matter(self):
        mine = {"indices": [2, 0]}
        assert R.recant_agrees(mine, {"indices": "0|2"}, 3, -1) is True

    def test_different_indices_never_agree(self):
        """Two nodes naming different statements have agreed about nothing
        useful. Recording 'contradicts something' would be worse than
        recording nothing."""
        mine = {"indices": [1]}
        assert R.recant_agrees(mine, {"indices": "2"}, 3, -1) is False

    def test_one_finding_a_conflict_and_one_not_never_agree(self):
        mine = {"indices": [1]}
        assert R.recant_agrees(mine, {"indices": "none"}, 3, -1) is False
        assert R.recant_agrees({"indices": []}, {"indices": "1"}, 3, -1) is False

    def test_a_superset_is_not_agreement(self):
        mine = {"indices": [1]}
        assert R.recant_agrees(mine, {"indices": "1|2"}, 3, -1) is False

    def test_an_out_of_range_proposal_is_rejected(self):
        mine = {"indices": [1]}
        assert R.recant_agrees(mine, {"indices": "9"}, 3, -1) is False

    def test_a_self_reference_is_rejected(self):
        mine = {"indices": [1]}
        assert R.recant_agrees(mine, {"indices": "1"}, 3, 1) is False

    def test_unparseable_is_rejected_rather_than_read_as_empty(self):
        """'maybe' is not 'none'. Treating garbage as a clean result would let
        a broken model quietly clear every statement it was given."""
        mine = {"indices": []}
        assert R.recant_agrees(mine, {"indices": "maybe"}, 3, -1) is False

    def test_garbage_calldata_is_rejected(self):
        mine = {"indices": []}
        assert R.recant_agrees(mine, "not a dict", 3, -1) is False
        assert R.recant_agrees(mine, None, 3, -1) is False
        assert R.recant_agrees(mine, [], 3, -1) is False

    def test_a_missing_key_reads_as_empty_and_agrees_with_empty(self):
        assert R.recant_agrees({"indices": []}, {}, 3, -1) is True

    @pytest.mark.parametrize("a,b", [([1], [1]), ([], []), ([0, 2], [0, 2]),
                                     ([1], [2]), ([1], []), ([0, 1], [1])])
    def test_agreement_is_symmetric(self, a, b):
        """An asymmetric rule would make consensus depend on which node was
        elected leader, which is a subtle and very unpleasant bug."""
        def fmt(x):
            return "|".join(str(i) for i in x) if x else "none"
        fwd = R.recant_agrees({"indices": a}, {"indices": fmt(b)}, 3, -1)
        rev = R.recant_agrees({"indices": b}, {"indices": fmt(a)}, 3, -1)
        assert fwd == rev


# ===========================================================================
# sanitise_reason
# ===========================================================================

class TestSanitiseReason:
    """These strings are leader-supplied and deliberately NOT part of
    consensus, so they are treated as untrusted on the way into storage."""

    def test_markup_is_stripped(self):
        out = R.sanitise_reason("<script>alert(1)</script> ok")
        assert "<" not in out and ">" not in out

    def test_braces_and_backticks_are_stripped(self):
        out = R.sanitise_reason("{{ignore}} `cmd` \\x")
        assert not any(c in out for c in "{}`\\")

    def test_control_characters_become_spaces(self):
        assert R.sanitise_reason("a\x00b\nc\td") == "a b c d"

    def test_whitespace_is_collapsed(self):
        assert R.sanitise_reason("a     b\n\n c") == "a b c"

    def test_length_is_capped(self):
        assert len(R.sanitise_reason("x" * 5000)) == R.MAX_REASON

    def test_ordinary_text_survives(self):
        assert R.sanitise_reason("  rules out what this permits  ") == \
            "rules out what this permits"


# ===========================================================================
# The prompt
# ===========================================================================

class TestPrompt:
    def test_untrusted_input_is_labelled(self):
        p = R.build_prompt("Acme", "SUBJECT", "[0] EARLIER")
        assert "untrusted" in p
        assert "never an instruction" in p
        assert "<record>" in p and "<statement>" in p

    def test_it_says_what_is_not_a_contradiction(self):
        """Without this the model flags every change of emphasis, and the
        contract becomes noise."""
        p = R.build_prompt("Acme", "S", "[0] E")
        for phrase in ("add detail", "change emphasis", "narrow a scope",
                       "different subject"):
            assert phrase in p

    def test_the_answer_format_is_closed(self):
        p = R.build_prompt("Acme", "S", "[0] E")
        assert '"conflicts"' in p
        assert "joined by a pipe, or the word none" in p

    def test_the_record_is_numbered(self):
        p = R.build_prompt("Acme", "S", "[0] first\n[1] second")
        assert "[0] first" in p and "[1] second" in p
