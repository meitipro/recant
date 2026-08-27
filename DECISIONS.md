# DECISIONS

What was decided, why, and what is still true that a reviewer should know.

---

## Recording and judging are separate transactions

`state()` puts a statement on the record. `check()` judges it. They are not
combined, and the reason is not convenience.

A statement belongs on the record the moment it is made, whether or not anybody
has got around to checking it. A contract that refused to record what it could
not immediately judge would have gaps **exactly where the interesting statements
are** — the contentious ones, made in a hurry, that nobody wanted to spend a
consensus round on that day.

It also means a record can be backfilled and then checked, which is how anyone
would actually adopt this: import what was already said, then start checking.

---

## The block returns an index, not a judgment

This is the design decision the whole contract turns on.

The obvious shape is to return the verdict: `"contradicts"`, `"clear"`. Two
things go wrong with that.

**It hides which statement.** A verdict without a target is unusable. Nobody can
act on "this contradicts something".

**It is the least stable thing available.** Asked for a verdict, two validators
must agree on a threshold — how much tension counts as contradiction. Asked
which *row* fights this one, they agree readily, because that is close to a
structural property of the pair.

So the block returns indices, and the contract derives the verdict from them
plus withdrawal state the block never saw.

> The judgment is hard. The thing that crosses consensus is a number.

Difficulty of the judgment and difficulty of the agreement are independent
properties, and the second one is chosen by whoever designs the return value.

---

## Layer 2 compares the indices, not "did you also find something"

A looser rule was considered and rejected: agree when both nodes found *a*
conflict, without requiring the same one.

It would settle far more often. It would also record findings that name the
wrong statement, and a record naming an innocent statement is worse than no
record. The whole product is the pointer.

Covered by `test_different_indices_never_agree` and by the mutation that
loosens the rule exactly this way.

---

## Withdrawal does not delete

A statement that was made and then taken back is a **different fact** from a
statement never made. Deleting it would let an author quietly rewrite history
and then pass every future check.

So `withdraw()` sets a flag, the text stays, and a later statement that
contradicts only withdrawn statements returns `stale` rather than
`contradicts`.

`stale` is not a weak contradiction. It is the absence of one: the author
already changed their mind, in public, on the record, which is the honest thing
to do and should not be punished by the contract.

Only the registrar may withdraw. Anyone may `state()` and anyone may `check()`,
because neither of those can distort the record — but being able to retire a
statement is authority over history.

---

## Unparseable output is not the same as "none"

`parse_indices()` returns an empty list for `none`, and *also* for `"maybe"`,
`"-1"`, `"3.5"`, `"3|3"` and anything else malformed.

The validator distinguishes them. A leader whose answer was unparseable is
rejected; a leader who said `none` is not. Without that distinction, a model
returning garbage would quietly **clear** every statement it was given, and the
contract would report perfect consistency for a record full of contradictions.

That is the worst possible failure mode for this contract: silently confident,
in the safe direction.

---

## The scope is capped at 24, and the cap is documented

An unbounded prompt is an unbounded cost and an eventual hard failure. Capping
is not optional.

Quietly truncating would be worse than the cap, because a caller with a
hundred-statement record would believe it had been checked against all of them.
So the cap is stated in the README, in the specification, and in the contract
docstring: a long record is checked against its **recent** history.

---

## Why the tests are built the way they are

### The simulator gives each node its own world

`tests/glsim.py` runs the block twice — once as the leader, once as a validator
— with **independent** mock answers:

```python
self.mocks(says("0"), v_prompts=says("1"))
```

Feeding both nodes the same data is the default in every mocking framework, and
it is exactly why a contract that quietly assumes both nodes see identical bytes
passes its suite and fails on a real network.

### The unit tests load the real contract source

A contract file cannot be imported: it starts with the GenVM dependency header
and does `from genlayer import *`. So `tests/test_logic.py` reads the real file
and executes the helper section with a stub.

Copying the rules into the test file would create a second copy that drifts.
Here, a change to the contract is a change to what the tests run.

### Mutation testing, because passing tests prove nothing

Every safety property was broken on purpose. The table is generated by
`python scripts/mutate.py`, which applies each mutation to a scratch copy and
records which test caught it, so the count in [README.md](README.md#the-tests-have-teeth)
is measured rather than typed. `scripts/measure.py --write` refuses to update
the README at all if the suite is red or a mutation escapes.

**Three mutations escaped the first time the pass ran, and two of them were real
gaps.**

The scope cap had no test: removing `out[-MAX_SCOPE:]` changed nothing, because
no other test built a record long enough to reach it. An unbounded prompt is an
unbounded cost, so the cap matters and now has a test of its own.

The second was worse. Adding `"found": len(idx) > 0` to the block's return value
passed **both** defences: the static shape test rejects a literal `True` but
`len(idx) > 0` is a Compare node rather than a constant, and glsim had no
runtime check on the boundary at all. That is exactly the failure this
repository warns about in the section above -- the one that produces
`Result Code <unknown>` with no traceback. It is now caught from both sides: the
static test rejects boolean expressions, and glsim raises at the boundary.

The third stays uncaught on purpose. By the time the deterministic half runs,
`leader_fn` has already clamped an out-of-range answer to empty and the
validator's layer 1 has rejected one that arrived out of range anyway, so
removing the post-consensus range check changes no outcome. It stays in the
contract as defence in depth, and it is **not** in the mutation table, because a
test that cannot fail is worse than no test -- it reports coverage it does not
provide.


### The deploy script did not run

Three things in `scripts/deploy.sh`, none of them in the contract, each of which
kills the script before it reaches the network:

`genlayer network studionet` answers *unknown command* and exits 1, because
`network` is a command group -- it is `network set`. `genvm-lint <file>` takes a
legacy path and dies on a traceback; it needs its `lint` subcommand, and
`PYTHONIOENCODING=utf-8`, because the linter prints a U+2713 on success and
cannot encode it under the cp1252 stdout Windows hands a child process, which
reports a *passing* contract as failed.

The third is the one worth remembering. `--args` is **variadic**: the parser
JSON-decodes each token and appends an array or object as ONE argument. So
`--args '[0,"text"]'` passes a single two-item array where the method wanted two
parameters, and `--args '[]'` passes an empty array to a constructor that takes
nothing. Every call in the script was written that way. They are now separate
tokens, verified by running the script against a stub that prints its argv
rather than by reading it.

---

## GenVM constraints this contract obeys

Each of these cost a failed deployment or a failed transaction in a previous
project in this line. None produce a helpful error. One produces no error at
all.

- **No collection inside a storage dataclass.** `DynArray[Check]()` fails with
  `this class can't be instantiated by user`, and
  `gl.storage.inmem_allocate(DynArray[T])` does not rescue it — that function is
  for generic dataclasses and fails with `_GenericAlias.__init__() missing 1
  required positional argument`. Everything here is flat; children carry a
  parent id.
- **No `int`, `list`, `dict` or `tuple` as a storage field type.** Rejected at
  deploy.
- **Every persistent field declared in the class body.** `self.x = value` on an
  undeclared name is silently discarded after execution.
- **The block returns a flat dict of `str`.** A nested mapping or a bool fails
  inside the calldata encoder, which is *outside* the contract, producing
  `Result Code: <unknown>` with **no stderr and no traceback**. That one cost an
  evening to diagnose, and only by comparing against a sibling contract whose
  block returned flat strings and worked first time.
- **The block closes over plain values only.** Blocks cannot read storage.
- **No `list[str]` parameters.** All method parameters are `str` / `u256` /
  `bool` / `Address`.
- **Every view bounds-checks its id.** An id past the end raises a raw
  `IndexError`; worse, Python accepts `-1` and **silently returns the newest
  record**, correctly formatted, with nothing failing anywhere.
- **Every `raise` is `gl.vm.UserError`.** Anything else surfaces as a contract
  error with a raw traceback.

All of it is checked by static analysis in `TestStorageShape`, so a regression
fails on the workstation rather than after a deployment.

---

## Honest limits

### It cannot see a contradiction with something outside the record

Only statements registered here are in scope. An organisation that says one
thing here and the opposite in a blog post is consistent as far as this contract
can tell. It measures self-consistency **within a record**, not truthfulness.

### The cap is a real blind spot

Past twenty-four statements, a contradiction with something very old will not be
found. For a long-running record, the honest mitigation is a fresh author
record per era, or accepting that ancient statements age out of scope.

### Contradiction is a judgment, not a fact

Whether "we share data with partners" contradicts "we never sell data" depends
on whether sharing is selling. Reasonable readers differ. The contract makes
that judgment reproducible and auditable — the stored reason says why — but it
does not make it objective.

### The reason string is leader-supplied

`why` is chosen by whichever node led, and is deliberately outside consensus:
two honest readers describe the same contradiction differently, and comparing
prose would stall every check. It is sanitised on the way into storage and
flagged in `latest()`, but **nothing should build logic on it**.

### Not upgradable

No admin method, no pause, no owner beyond the per-record registrar. Deliberate
for a primitive whose value is that its rules cannot move after somebody depends
on them, and it means a bug found later requires a new deployment.
