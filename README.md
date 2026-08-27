<p align="left"><img src="brand/lockup.svg" alt="recant" height="64"></p>

# Recant — self-consistency across a record of statements

A reusable primitive that checks a new statement against every earlier statement by the **same author**, and names the one it contradicts.

- **Contract:** [`contracts/recant.py`](contracts/recant.py)
- **Tests:** `pip install pytest && pytest tests/ -q` — nothing else to install
- **Deployed:** `0x2b4367c45ec6CD309BdEEE5eC7bFd2f20A63A3F7` on studionet ([explorer](https://explorer-studio.genlayer.com/address/0x2b4367c45ec6CD309BdEEE5eC7bFd2f20A63A3F7))
- **Specification:** [CONTRACTS.md](CONTRACTS.md)
- **Decisions and limits:** [DECISIONS.md](DECISIONS.md)
- **License:** MIT. Copy the agreement rule; that is what it is for.

---

## The problem

In March an organisation says "we will never sell user data". In October it says
"we share data with selected partners". Each statement, read alone, is
unremarkable. **The contradiction exists only in the pair, and nobody holds both
at once.**

**Consensus settles the judgment it is handed, and this one is handed half the
input.** Every validator sees the new statement on its own. The earlier record
is not part of the input at all, so five nodes agree, correctly and
confidently, on a claim that fights something the same contract recorded two
months ago.

The agreement is real. The consistency is absent, and it is absent because of
what the block was given rather than because of how the nodes agreed on it.

> Consensus makes one judgment reliable. Handing it the record is what makes the
> next one agree with the last.

That is the whole of what Recant does: it puts the record in front of the
validators, in a shape they can agree on exactly.

## How consensus is used

The block receives the new statement **and every earlier statement by that
author**, numbered. It returns **one integer**: the index of the statement this
one contradicts, or `none`.

That is the whole trick, and it is worth stating plainly:

- The judgment is hard. Read a corpus, understand what each statement commits
  to, separate a real contradiction from a change of emphasis.
- The thing that crosses consensus is **a number**.

**Difficulty of the judgment and difficulty of the agreement are independent
properties**, and the second one is chosen by whoever designs the block's return
value. Most contracts return whatever the model produced, which is the
finest-grained form available and the least stable. Returning an index into a
list the contract already holds is the coarsest form that still carries the
answer.

### The validator, in two layers

```python
# LAYER 1 -- structural honesty. Costs nothing, runs before any prompt.
#   An index must be in range, must not point at the statement being checked,
#   and must not be a duplicate. All three are checkable against data the
#   validator already has. A malformed proposal is rejected before this
#   validator spends a single inference on it.
if not structurally_sound(their_indices, scope_size, self_index):
    return False

# LAYER 2 -- agreement on the indices themselves, not on "something conflicts".
#   Two nodes naming different statements have agreed about nothing useful,
#   and storing "contradicts something" would be worse than storing nothing.
return sorted(mine["indices"]) == sorted(their_indices)
```

## Four outcomes, and they are different facts

| Verdict | Meaning |
|---|---|
| `clear` | Nothing in the record is inconsistent with this |
| `contradicts` | Exactly one live statement is, and it is named |
| `conflict` | Several are — a finding about the **record**, not about the new statement |
| `stale` | The only inconsistency is with something already withdrawn |

`stale` is the one worth pausing on. A statement that contradicts a **withdrawn**
statement is not inconsistent at all: it is the author having already changed
their mind, in public, on the record. Withdrawing does not delete, because a
statement that was made and then taken back is a different fact from a statement
never made.

### All four, on chain

The deployed record at
[`0x2b4367c45ec6CD309BdEEE5eC7bFd2f20A63A3F7`](https://explorer-studio.genlayer.com/address/0x2b4367c45ec6CD309BdEEE5eC7bFd2f20A63A3F7)
carries one author and four statements, checked in order:

| Statement | Verdict | Against |
|---|---|---|
| "We will never sell or share user data with any third party." | `clear` | — |
| "Our uptime target for the coming year is ninety nine percent." | `clear` | — |
| "We share user data with selected commercial partners." | `contradicts` | `0` |
| "We share user data with commercial partners under contract." | `stale` | `0` |

Rows three and four say the same thing. Between them the author withdrew the
first statement, so the same claim comes back `stale` instead of `contradicts`
— from a withdrawal flag the block never sees. Read it back yourself with
`consistency(0)`, which returns `inconsistent_pct: 25`.

On `check(3)` two of five validators voted **disagree** with no error anywhere:
they ran the prompt, reached a different set of indices, and layer 2 declined to
call that agreement. The transaction finalized on the majority. That is the
refusal path on a live network, not in a simulator.

## Why this is not a thin LLM wrapper

The model never decides an outcome. **It points at a row in a list the contract
owns.** Everything else is deterministic: which statements are in scope, whether
the target is withdrawn, whether a multi-way conflict is reportable, and what
the record then says.

Swap in a worse model and the mechanism still works. It finds fewer
contradictions, which is the correct response to a worse model.

## The record grows

This is the only primitive in this line that **gets stronger with use**. The
fiftieth statement is checked against forty-nine. A contract deployed once and
used for a year is worth more than the day it shipped, and the value lives in
state rather than in code.

---

## The API

```python
register(label)                  # open a record for one author
state(author_id, text)           # add a statement. recording != judging
withdraw(statement_id)           # take one back. does not delete
check(statement_id)              # judge it against the earlier record

verdict(statement_id)   -> str   # clear | contradicts | conflict | stale | ""
against(statement_id)   -> str   # the statement ids it fights, pipe joined
latest(statement_id)    -> dict  # the verdict, the target, the reason
record(author_id)       -> dict  # the whole record, oldest first
consistency(author_id)  -> dict  # how often this author contradicts themselves
```

Recording and judging are two transactions **on purpose**. A statement belongs
on the record the moment it is made, whether or not anybody has got around to
checking it. A contract that refused to record what it could not immediately
judge would have gaps exactly where the interesting statements are.

## Using it from another contract

```python
@gl.contract_interface
class Recant:
    class View:
        def verdict(self, statement_id: int) -> str: ...

# act only on a statement that is consistent with its own record
if Recant(RECANT_ADDR).view().verdict(sid) == "clear":
    self._proceed()
```

`verdict()` returns an empty string for an unchecked statement rather than
raising, so the caller has one branch to handle instead of two.

---

## Running the tests

```bash
pip install pytest
pytest tests/ -q
```

<!-- measured:tests -->
`pytest tests/ -q` reports **111 passed, 1 skipped**, and every one of the **26** mutations below is caught.
<!-- /measured:tests -->

**`tests/test_logic.py`** — the pure rules, exhaustively. They are module-level
functions in the contract, so this file reads the **real contract source** and
executes the helper section with a stub for `genlayer`. There is no second copy
of the logic to drift out of sync.

**`tests/test_e2e.py`** — the contract itself, executed on
[`tests/glsim.py`](tests/glsim.py), a small GenVM stand-in included here. This
reaches the deterministic half: storage round-trips, the scope walk, the
withdrawal path, and every branch that only fires when the leader and a
validator see different things.

The important part is that the leader and the validator get **their own** mock
answers:

```python
self.mocks(says("0"), v_prompts=says("1"))   # the nodes named different statements
```

Every mocking framework feeds both nodes the same data by default, which is
exactly why a contract that quietly assumes both nodes see identical bytes
passes its suite and fails on a real network.

### The tests have teeth

Every safety property was broken on purpose to confirm a test notices. The
table is generated by `python scripts/mutate.py`, which applies each mutation to
a scratch copy of the repository and records which test caught it.

<!-- measured:mutations -->
| Mutation | Caught by |
|---|---|
| the layer 1 structural check removed | `test_a_self_reference_is_rejected` |
| agreement loosened to "both found something" | `test_nodes_naming_different_statements_do_not_agree` |
| unparseable output read as clean | `test_unparseable_is_rejected_rather_than_read_as_empty` |
| a statement allowed to contradict itself | `test_a_statement_cannot_contradict_itself` |
| out of range indices allowed | `test_an_out_of_range_index_is_rejected` |
| duplicates accepted by the parser | `test_duplicates_are_not_sound` |
| the reason sanitiser disabled | `test_a_leader_supplied_reason_is_sanitised` |
| control characters left in reasons | `test_a_leader_supplied_reason_is_sanitised` |
| non-numeric accepted by the parser | `test_a_garbage_answer_is_not_read_as_clean` |
| withdrawn statements treated as live | `test_contradicting_a_withdrawn_statement_is_stale_not_a_contradiction` |
| a multi-way conflict collapsed to one | `test_several_contradictions_are_a_conflict_in_the_record` |
| `stale` collapsed into `contradicts` | `test_contradicting_a_withdrawn_statement_is_stale_not_a_contradiction` |
| an empty answer read as a contradiction rather than clear | `test_a_consistent_statement_is_clear` |
| later statements pulled into scope | `test_the_first_statement_is_clear_without_a_model` |
| the author filter dropped from scope | `test_only_the_same_author_is_in_scope` |
| the scope cap removed, so an unbounded prompt is built | `test_the_scope_is_capped_at_the_most_recent_MAX_SCOPE` |
| the view bounds check removed | `test_a_read_with_a_nonexistent_id_is_a_user_error` |
| negative ids allowed through to Python list indexing | `test_a_read_with_a_negative_id_does_not_return_the_last_record` |
| anyone allowed to withdraw | `test_only_the_registrar_may_withdraw` |
| re-checking allowed, so a verdict can be overwritten | `test_checking_twice_is_refused` |
| withdrawing twice allowed | `test_withdrawing_twice_is_refused` |
| a nested mapping returned from the block | `test_a_consistent_statement_is_clear` |
| a bool returned from the block | `test_a_consistent_statement_is_clear` |
| a collection nested back into a storage dataclass | `test_the_first_statement_is_clear_without_a_model` |
| an int storage field | `test_the_first_statement_is_clear_without_a_model` |
| a storage field declared twice | `test_no_storage_field_is_declared_twice` |
<!-- /measured:mutations -->

---

## Design rules

- **Nothing outside the closed set gets through.** Model output becomes a list
  of integer indices or nothing. A word, a negative, a float, a duplicate — all
  become empty rather than a guess, because a wrong index that looks plausible
  is far worse than no index: it names an innocent statement.
- **The deterministic half derives, it does not trust.** The model points at
  rows; the contract decides what that means, using withdrawal state the block
  never saw.
- **Untrusted input is labelled as such.** Every prompt is built in contract
  code. Statements sit inside tags and are named as data that is never an
  instruction, and text addressing the model is itself grounds for answering
  `none`.
- **Refusing is a designed outcome.** `clear`, `stale` and a failed consensus
  are all better than a confident wrong name.
- **No web access.** Every input is text the caller supplies, which removes an
  entire class of deployment failure.

## Further reading in this repository

- [CONTRACTS.md](CONTRACTS.md) — the full specification: purpose, consensus,
  state model, API, reuse
- [DECISIONS.md](DECISIONS.md) — engineering decisions and the honest limits
- [brand/](brand/) — the mark, the lockup, the palette, and the social card
- [lib/recant_consensus.py](lib/recant_consensus.py) — the agreement rules on
  their own, to be copied

## Related work

Separate primitives, built to the same standard and submitted independently:
[Crosscheck](https://github.com/meitipro/genlayer-crosscheck) — a
framing-sensitivity detector. [Tolerance](https://github.com/meitipro/genlayer-tolerance)
— per-field numeric agreement.

They share an author and a discipline, not a codebase. Each deploys, tests and
is used entirely on its own.

---

Published by [InferNode](https://x.com/Infer_node).
