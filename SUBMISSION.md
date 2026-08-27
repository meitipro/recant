# Submission

One submission, under **Builder -> Intelligent Contracts**. This repository is
one standalone primitive.

---

## Before you submit, in order

1. **Measure, do not estimate.**

   ```bash
   python scripts/measure.py --write
   ```

   Runs the suite, runs the full mutation pass, and writes both numbers into
   README.md. It refuses to write anything if the suite is red or a mutation
   escapes, so a number in the README is always one that was checked.

2. **Deploy and exercise.** Through the Studio web interface at
   studio.genlayer.com, or `./scripts/deploy.sh studionet` for the CLI route.
   Never put a private key into a file.

3. **Put a refusal on chain, not only a success.** The story the script tells is
   the submission: three statements where the third fights the first, then the
   author withdraws the original and says it again, so the same words come back
   `stale` instead of `contradicts`. A page showing only successes proves the
   file compiles and nothing else.

4. **Open the explorer page and check it.** It must show a Deploy transaction
   **and** method calls with a Consensus Result beside them, and no failed or
   abandoned transaction.

5. **Paste the address** into README.md and into this file, then push.

6. **Upload `brand/social.png`** under Settings → General → Social preview.
   GitHub has no API for this, so it is the one step that must be done by hand.

Steps 1 to 5 are done; the results are below. Step 6 is the only one left.

---

## On chain

Deployed and exercised on studionet at
[`0x2b4367c45ec6CD309BdEEE5eC7bFd2f20A63A3F7`](https://explorer-studio.genlayer.com/address/0x2b4367c45ec6CD309BdEEE5eC7bFd2f20A63A3F7).
Eleven transactions, every one `FINALIZED`, no failed or abandoned transaction
on the page. The values below were read back from the chain with view calls
after the fact, not copied from a local run.

| # | Transaction | Result |
|---|---|---|
| 1 | deploy | finalized |
| 2 | `register("Example Org")` | record 0 opens |
| 3 | `state(0, "We will never sell or share user data with any third party.")` | statement 0 |
| 4 | `state(0, "Our uptime target for the coming year is ninety nine percent.")` | statement 1 |
| 5 | `state(0, "We share user data with selected commercial partners.")` | statement 2 |
| 6 | `check(0)` | `clear` — no earlier statement, so no prompt was spent |
| 7 | `check(1)` | `clear` — unrelated subject |
| 8 | `check(2)` | **`contradicts`**, `against` = `0` |
| 9 | `withdraw(0)` | statement 0 marked withdrawn, still readable |
| 10 | `state(0, "We share user data with commercial partners under contract.")` | statement 3 |
| 11 | `check(3)` | **`stale`**, `against` = `0` |

The last two rows are the point. Statement 2 and statement 3 say the same thing;
between them the author withdrew the promise they both fight. The first is a
live contradiction, the second is a contradiction with something already
retracted, and the contract distinguishes them without being told which is
which. Only the withdrawal flag differs, and it is deterministic state the block
never sees.

`consistency(0)` now returns:

```json
{"statements": 4, "checked": 4, "clear": 2, "contradicts": 1,
 "conflict": 0, "stale": 1, "inconsistent_pct": 25}
```

### The second validator layer fired, visibly

On `check(3)` the votes were **3 agree, 2 disagree**, and every node reported
`SUCCESS`. Nothing crashed: two validators ran the same prompt, reached a
different set of indices, and layer 2 refused to call that agreement. The
transaction still finalized on the majority. That is the disagreement path
working on a real network rather than in `tests/glsim.py`, and it is the reason
layer 2 compares indices instead of "did you also find something" — under the
looser rule those two validators would have voted agree while naming something
else.

Contrast `check(0)`, which cost no inference at all: the first statement on a
record has nothing to be inconsistent with, so the contract answers `clear`
deterministically and never opens a block.

---

## Title

```
Recant: self-consistency across a record of statements
```

## Notes (915 characters, the box caps at 1000)

```
Recant checks a new statement against every earlier statement by the SAME author, and names the one it contradicts. In March an organisation says "we will never sell user data"; in October it says "we share data with partners". Each reads fine alone. Consensus makes this worse, not better: every validator sees only the new statement, so five nodes agree confidently on a claim that fights something the same contract recorded months ago. The block receives the new statement AND the numbered record, and returns ONE INTEGER: the index it contradicts, or none. The judgment is hard; the thing crossing consensus is a number. Two validator layers: a free structural check (in range, not self, no duplicate) before any prompt, then exact agreement on the indices, never on "both found something". Withdrawn statements yield stale, not contradicts. Deployed at 0x2b4367c45ec6CD309BdEEE5eC7bFd2f20A63A3F7 on studionet.
```

## Links

```
GitHub:   https://github.com/meitipro/recant
Contract: https://github.com/meitipro/recant/blob/main/contracts/recant.py
Spec:     https://github.com/meitipro/recant/blob/main/CONTRACTS.md
Decisions https://github.com/meitipro/recant/blob/main/DECISIONS.md
Tests:    https://github.com/meitipro/recant/tree/main/tests
Explorer: https://explorer-studio.genlayer.com/address/0x2b4367c45ec6CD309BdEEE5eC7bFd2f20A63A3F7
```

---

## What clears the bar, line by line

The category rejects "thin LLM wrappers" and "generic AI decides X demos".

- **The model never decides.** It points at a row in a list the contract owns.
  Which statements are in scope, whether the target is withdrawn, whether a
  multi-way conflict is reportable, and what the record then says are all
  deterministic.
- **The validator function is the contribution.** A free structural check before
  any prompt, then exact agreement on the indices. Explained in
  [CONTRACTS.md](CONTRACTS.md) with the code.
- **Refusing is designed.** `clear`, `stale`, and a failed consensus are all
  better than a confident wrong name.
- **The tests have teeth.** A passing count is a claim; the mutation table in
  the README is evidence, and it is generated by a script that refuses to emit
  a table if anything escapes.
- **It runs with nothing installed.** `pip install pytest && pytest tests/ -q`.
  A reviewer with two minutes can verify the whole thing.
- **The limits are stated.** [DECISIONS.md](DECISIONS.md) says what this cannot
  do, including the scope cap and the fact that it measures self-consistency
  rather than truth.

## One thing worth putting in the notes if there is room

The strongest single line for a reviewer is that **the judgment is hard and the
thing crossing consensus is a number**. Everything else in the design follows
from it.
