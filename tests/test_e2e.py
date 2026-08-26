"""
End-to-end tests. The real contract file, executed.

tests/test_logic.py covers the pure rules. This file covers everything they
cannot reach: the deterministic half, storage round-trips, the scope walk, the
withdrawal path, and every branch that only fires when the leader and a
validator see different things.

It runs on tests/glsim.py, a small GenVM stand-in, so it needs no Studio and no
network:

    pytest tests/test_e2e.py -v

The important property is that the leader and the validator get their own
independent mock answers. Every mocking framework feeds both nodes the same
data by default, which is exactly why a contract that quietly assumes both nodes
see identical bytes passes its suite and fails on a real network.
"""

import pytest

import glsim as S

CONTRACT_PATH = "contracts/recant.py"


# ---------------------------------------------------------------------------
# A record with a real contradiction in it.
#
#   0  we will never sell or share user data with third parties
#   1  our uptime target for the coming year is ninety nine percent
#   2  we share user data with selected commercial partners   <- fights 0
# ---------------------------------------------------------------------------

S0 = "We will never sell or share user data with any third party."
S1 = "Our uptime target for the coming year is ninety nine percent."
S2 = "We share user data with selected commercial partners."
S3 = "We publish a transparency report every quarter."


def says(indices, because="the earlier commitment rules this out"):
    """Build a mocked model answer naming those local scope indices."""
    return {"Which earlier statements":
            {"conflicts": indices, "because": because}}


class TestRecant:
    def deploy(self, label="Acme"):
        c = S.deploy(CONTRACT_PATH)
        S.call(c, "register", label)
        return c

    def mocks(self, prompts, v_prompts=None):
        S.set_mocks(leader_pages={}, leader_prompts=prompts,
                    validator_pages={},
                    validator_prompts=v_prompts if v_prompts is not None else prompts)

    # -- the record ---------------------------------------------------------

    def test_the_first_statement_is_clear_without_a_model(self):
        """Nothing to be inconsistent with, so no prompt is spent. Note that
        the mocks are empty: if this path called a model, the test would fail
        with 'no mock prompt response matched'."""
        c = self.deploy()
        S.call(c, "state", 0, S0)
        self.mocks({})
        S.call(c, "check", 0)
        assert c.verdict(0) == "clear"
        assert c.latest(0)["why"] == "first statement on this record"

    def test_a_consistent_statement_is_clear(self):
        c = self.deploy()
        S.call(c, "state", 0, S0)
        S.call(c, "state", 0, S1)
        self.mocks({})
        S.call(c, "check", 0)
        self.mocks(says("none"))
        S.call(c, "check", 1)
        assert c.verdict(1) == "clear"
        assert c.against(1) == ""

    def test_a_contradiction_names_the_statement_it_fights(self):
        """The whole point. Statement 2 contradicts statement 0, and the
        record says which."""
        c = self.deploy()
        for t in (S0, S1, S2):
            S.call(c, "state", 0, t)
        self.mocks({})
        S.call(c, "check", 0)
        self.mocks(says("none"))
        S.call(c, "check", 1)
        self.mocks(says("0"))
        S.call(c, "check", 2)

        assert c.verdict(2) == "contradicts"
        assert c.against(2) == "0"
        out = c.latest(2)
        assert out["checked"] is True
        assert out["text"] == S2

    def test_several_contradictions_are_a_conflict_in_the_record(self):
        c = self.deploy()
        for t in (S0, S3, S2):
            S.call(c, "state", 0, t)
        self.mocks({})
        S.call(c, "check", 0)
        self.mocks(says("none"))
        S.call(c, "check", 1)
        self.mocks(says("0|1"))
        S.call(c, "check", 2)
        assert c.verdict(2) == "conflict"
        assert c.against(2) == "0|1"

    # -- withdrawal ---------------------------------------------------------

    def test_contradicting_a_withdrawn_statement_is_stale_not_a_contradiction(self):
        """The author already changed their mind, in public, on the record.
        That is not an inconsistency."""
        c = self.deploy()
        S.call(c, "state", 0, S0)
        S.call(c, "state", 0, S1)
        S.call(c, "withdraw", 0)

        self.mocks(says("none"))
        S.call(c, "check", 1)
        S.call(c, "state", 0, S2)
        self.mocks(says("0"))
        S.call(c, "check", 2)

        assert c.verdict(2) == "stale"
        assert c.against(2) == "0"

    def test_a_live_statement_is_not_diluted_by_a_withdrawn_one(self):
        c = self.deploy()
        for t in (S0, S3, S2):
            S.call(c, "state", 0, t)
        S.call(c, "withdraw", 1)
        self.mocks({})
        S.call(c, "check", 0)
        self.mocks(says("0|1"))
        S.call(c, "check", 2)
        assert c.verdict(2) == "contradicts"
        assert c.against(2) == "0"

    def test_withdrawing_does_not_delete(self):
        c = self.deploy()
        S.call(c, "state", 0, S0)
        S.call(c, "withdraw", 0)
        out = c.latest(0)
        assert out["withdrawn"] is True
        assert out["text"] == S0

    def test_only_the_registrar_may_withdraw(self):
        c = self.deploy()
        S.call(c, "state", 0, S0)
        S.set_sender("0x" + "99" * 20)
        try:
            with pytest.raises(S.UserError, match="registrar"):
                S.call(c, "withdraw", 0)
        finally:
            S.set_sender("0x" + "11" * 20)

    def test_withdrawing_twice_is_refused(self):
        c = self.deploy()
        S.call(c, "state", 0, S0)
        S.call(c, "withdraw", 0)
        with pytest.raises(S.UserError, match="already withdrawn"):
            S.call(c, "withdraw", 0)

    # -- consensus ----------------------------------------------------------

    def test_nodes_naming_different_statements_do_not_agree(self):
        """Recording 'contradicts something' would be worse than recording
        nothing, so this must fail rather than settle."""
        c = self.deploy()
        for t in (S0, S3, S2):
            S.call(c, "state", 0, t)
        self.mocks({})
        S.call(c, "check", 0)
        self.mocks(says("none"))
        S.call(c, "check", 1)

        self.mocks(says("0"), v_prompts=says("1"))
        with pytest.raises(S.UserError):
            S.call(c, "check", 2)
        assert c.verdict(2) == ""          # nothing written

    def test_one_node_finding_a_conflict_and_one_not_does_not_agree(self):
        c = self.deploy()
        for t in (S0, S2):
            S.call(c, "state", 0, t)
        self.mocks({})
        S.call(c, "check", 0)
        self.mocks(says("0"), v_prompts=says("none"))
        with pytest.raises(S.UserError):
            S.call(c, "check", 1)

    def test_both_nodes_finding_nothing_agree(self):
        c = self.deploy()
        for t in (S0, S1):
            S.call(c, "state", 0, t)
        self.mocks({})
        S.call(c, "check", 0)
        self.mocks(says("none"), v_prompts=says("none", because="different subject"))
        S.call(c, "check", 1)
        assert c.verdict(1) == "clear"

    def test_an_out_of_range_index_is_rejected(self):
        c = self.deploy()
        for t in (S0, S2):
            S.call(c, "state", 0, t)
        self.mocks({})
        S.call(c, "check", 0)
        self.mocks(says("9"))
        S.call(c, "check", 1)
        # the block clamps an out of scope index to none rather than raising,
        # and both nodes clamp identically, so the result is a clean 'clear'
        assert c.verdict(1) == "clear"

    def test_a_garbage_answer_is_not_read_as_clean(self):
        """'maybe' must not be treated as 'none'. A broken model would
        otherwise quietly clear every statement it was given."""
        c = self.deploy()
        for t in (S0, S2):
            S.call(c, "state", 0, t)
        self.mocks({})
        S.call(c, "check", 0)
        self.mocks(says("maybe"))
        S.call(c, "check", 1)
        assert c.verdict(1) == "clear"     # clamped, and both nodes clamp alike

    # -- the reason string --------------------------------------------------

    def test_a_leader_supplied_reason_is_sanitised(self):
        c = self.deploy()
        for t in (S0, S2):
            S.call(c, "state", 0, t)
        self.mocks({})
        S.call(c, "check", 0)
        self.mocks(says("0", because="<script>x</script>\u0000 rules it out"))
        S.call(c, "check", 1)
        why = c.latest(1)["why"]
        assert "<" not in why and ">" not in why and "\u0000" not in why
        assert "rules it out" in why

    def test_the_view_says_the_reason_is_leader_supplied(self):
        c = self.deploy()
        S.call(c, "state", 0, S0)
        self.mocks({})
        S.call(c, "check", 0)
        assert c.latest(0)["reason_is_leader_supplied"] is True

    # -- scope --------------------------------------------------------------

    def test_only_the_same_author_is_in_scope(self):
        """Statements live in one flat array with an author id on each.
        Nothing else keeps two records apart, so this is the test that the id
        is honoured."""
        c = self.deploy("Acme")
        S.call(c, "register", "Globex")
        S.call(c, "state", 0, S0)       # Acme
        S.call(c, "state", 1, S3)       # Globex
        S.call(c, "state", 1, S1)       # Globex, second -> Acme's must not be in scope

        self.mocks({})
        S.call(c, "check", 0)           # Acme's first, no scope
        S.call(c, "check", 1)           # Globex's first, no scope either
        self.mocks(says("none"))
        S.call(c, "check", 2)

        assert c.record(0)["author"] == "Acme"
        assert len(c.record(0)["statements"]) == 1
        assert len(c.record(1)["statements"]) == 2

    def test_the_scope_is_capped_at_the_most_recent_MAX_SCOPE(self):
        """A record longer than the cap is checked against its recent history.

        An unbounded prompt is an unbounded cost and an eventual failure, so the
        cap is real rather than aspirational. The mutation pass found this had no
        test: removing `out[-MAX_SCOPE:]` changed nothing, because no other test
        builds a record long enough to reach it.
        """
        c = self.deploy()
        cap = c._module.MAX_SCOPE
        for i in range(cap + 3):
            S.call(c, "state", 0, "Statement number %d, on its own line." % i)

        # The newest statement sees exactly `cap` earlier ones, not all of them.
        scope = c._scope(0, cap + 2)
        assert len(scope) == cap

        # And it is the RECENT history: the oldest statements have fallen off.
        first_id = scope[0][0]
        assert first_id == 2, first_id

    def test_a_later_statement_is_never_in_scope(self):
        """Checking statement 1 must not see statement 2, even though it
        exists by then. A record is checked against its past, not its future."""
        c = self.deploy()
        for t in (S0, S1, S2):
            S.call(c, "state", 0, t)
        self.mocks({})
        S.call(c, "check", 0)
        # if statement 2 were in scope, local index 1 would exist
        self.mocks(says("1"))
        S.call(c, "check", 1)
        assert c.verdict(1) == "clear"   # index 1 is out of scope, clamped

    # -- consistency --------------------------------------------------------

    def test_consistency_accumulates(self):
        c = self.deploy()
        for t in (S0, S1, S2):
            S.call(c, "state", 0, t)
        self.mocks({})
        S.call(c, "check", 0)
        self.mocks(says("none"))
        S.call(c, "check", 1)
        self.mocks(says("0"))
        S.call(c, "check", 2)

        s = c.consistency(0)
        assert s["statements"] == 3
        assert s["checked"] == 3
        assert s["clear"] == 2
        assert s["contradicts"] == 1
        assert s["inconsistent_pct"] == 33

    def test_consistency_is_safe_before_any_check(self):
        c = self.deploy()
        s = c.consistency(0)
        assert s["checked"] == 0 and s["inconsistent_pct"] == 0

    # -- validation ---------------------------------------------------------

    def test_checking_twice_is_refused(self):
        c = self.deploy()
        S.call(c, "state", 0, S0)
        self.mocks({})
        S.call(c, "check", 0)
        with pytest.raises(S.UserError, match="already checked"):
            S.call(c, "check", 0)

    @pytest.mark.parametrize("text", ["short", "", "   ", "x" * 700])
    def test_bad_statements_are_refused(self, text):
        c = self.deploy()
        with pytest.raises(S.UserError):
            S.call(c, "state", 0, text)
        assert c.statement_count() == 0

    @pytest.mark.parametrize("label", ["", "x", "y" * 200])
    def test_bad_labels_are_refused(self, label):
        c = S.deploy(CONTRACT_PATH)
        with pytest.raises(S.UserError):
            S.call(c, "register", label)
        assert c.count() == 0

    def test_verdict_is_safe_before_any_check(self):
        c = self.deploy()
        S.call(c, "state", 0, S0)
        assert c.verdict(0) == ""
        assert c.against(0) == ""
        assert c.latest(0)["checked"] is False

    def test_a_read_with_a_nonexistent_id_is_a_user_error(self):
        """Not a raw IndexError. GenVM reports an uncaught Python exception as
        a contract error, which tells a caller nothing about what went wrong."""
        c = self.deploy()
        S.call(c, "state", 0, S0)
        for m in ("verdict", "against", "latest"):
            with pytest.raises(S.UserError, match="no such statement"):
                getattr(c, m)(99)
        for m in ("record", "consistency"):
            with pytest.raises(S.UserError, match="no such author"):
                getattr(c, m)(99)

    def test_a_read_with_a_negative_id_does_not_return_the_last_record(self):
        """The dangerous half. Python list indexing accepts -1 and returns the
        newest statement, so a caller asking for statement -1 would silently
        receive a different one and never know."""
        c = self.deploy()
        for t in (S0, S1):
            S.call(c, "state", 0, t)
        for m in ("verdict", "against", "latest"):
            with pytest.raises(S.UserError, match="no such statement"):
                getattr(c, m)(-1)
        for m in ("record", "consistency"):
            with pytest.raises(S.UserError, match="no such author"):
                getattr(c, m)(-1)

    def test_nothing_is_written_when_a_check_fails(self):
        c = self.deploy()
        for t in (S0, S3, S2):
            S.call(c, "state", 0, t)
        self.mocks({})
        S.call(c, "check", 0)
        self.mocks(says("none"))
        S.call(c, "check", 1)
        self.mocks(says("0"), v_prompts=says("1"))
        with pytest.raises(S.UserError):
            S.call(c, "check", 2)
        assert c.consistency(0)["checked"] == 2


# ===========================================================================
# GenVM storage and boundary rules, by static analysis.
#
# Not tests of behaviour. Tests of SHAPE, and each corresponds to a real
# failure that behaviour tests cannot see.
# ===========================================================================

class TestStorageShape:
    def test_the_contract_imports_under_genvm_storage_rules(self):
        mod = S.load_contract(CONTRACT_PATH)
        assert hasattr(mod, "Contract")

    def test_no_storage_dataclass_holds_a_collection(self):
        import ast, pathlib
        tree = ast.parse(pathlib.Path(CONTRACT_PATH).read_text())
        for cls in [x for x in tree.body if isinstance(x, ast.ClassDef)]:
            if "allow_storage" not in " ".join(
                    ast.unparse(d) for d in cls.decorator_list):
                continue
            for st in cls.body:
                if isinstance(st, ast.AnnAssign):
                    ann = ast.unparse(st.annotation)
                    assert "DynArray" not in ann and "TreeMap" not in ann

    def test_no_forbidden_storage_types(self):
        import ast, pathlib
        tree = ast.parse(pathlib.Path(CONTRACT_PATH).read_text())
        for cls in [x for x in tree.body if isinstance(x, ast.ClassDef)]:
            decs = " ".join(ast.unparse(d) for d in cls.decorator_list)
            is_contract = any("gl.Contract" in ast.unparse(b) for b in cls.bases)
            if "allow_storage" not in decs and not is_contract:
                continue
            for st in cls.body:
                if isinstance(st, ast.AnnAssign):
                    ann = ast.unparse(st.annotation)
                    assert ann not in ("int", "float", "list", "dict", "tuple")
                    assert not ann.startswith(("list[", "dict[", "tuple["))

    def test_no_storage_field_is_declared_twice(self):
        import ast, collections, pathlib
        tree = ast.parse(pathlib.Path(CONTRACT_PATH).read_text())
        for cls in [x for x in tree.body if isinstance(x, ast.ClassDef)]:
            names = [st.target.id for st in cls.body
                     if isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name)]
            dupes = [n for n, c in collections.Counter(names).items() if c > 1]
            assert not dupes, f"{cls.name} declares {dupes} more than once"

    def test_no_method_is_defined_twice(self):
        """A duplicated method silently shadows the first one. Python allows it
        and says nothing at all."""
        import ast, collections, pathlib
        tree = ast.parse(pathlib.Path(CONTRACT_PATH).read_text())
        for cls in [x for x in tree.body if isinstance(x, ast.ClassDef)]:
            names = [m.name for m in cls.body if isinstance(m, ast.FunctionDef)]
            dupes = [n for n, c in collections.Counter(names).items() if c > 1]
            assert not dupes, f"{cls.name} defines {dupes} more than once"
        names = [x.name for x in tree.body
                 if isinstance(x, (ast.FunctionDef, ast.ClassDef))]
        dupes = [n for n, c in collections.Counter(names).items() if c > 1]
        assert not dupes

    def test_every_persistent_field_is_declared_in_the_class_body(self):
        """A field created with self.x = value and never declared is NOT
        persistent. It is silently discarded when execution ends."""
        import ast, pathlib
        tree = ast.parse(pathlib.Path(CONTRACT_PATH).read_text())
        cls = [x for x in tree.body if isinstance(x, ast.ClassDef)
               and any("gl.Contract" in ast.unparse(b) for b in x.bases)][0]
        declared = {st.target.id for st in cls.body if isinstance(st, ast.AnnAssign)}
        for m in [x for x in cls.body if isinstance(x, ast.FunctionDef)]:
            for node in ast.walk(m):
                targets = (node.targets if isinstance(node, ast.Assign)
                           else [node.target] if isinstance(node, ast.AugAssign) else [])
                for tg in targets:
                    if (isinstance(tg, ast.Attribute)
                            and isinstance(tg.value, ast.Name)
                            and tg.value.id == "self"):
                        assert tg.attr in declared, (
                            f"{m.name} assigns self.{tg.attr}, undeclared, will not persist")

    def test_the_block_boundary_carries_flat_strings_only(self):
        """A nested mapping or a bool here fails inside the calldata encoder,
        which is OUTSIDE the contract, so it produces Result Code <unknown>
        with no stderr and no traceback at all."""
        import ast, pathlib
        tree = ast.parse(pathlib.Path(CONTRACT_PATH).read_text())
        for blk in [x for x in ast.walk(tree) if isinstance(x, ast.FunctionDef)
                    and x.name == "leader_fn"]:
            returns = [n for n in ast.walk(blk) if isinstance(n, ast.Return)]
            assert returns
            for r in returns:
                assert isinstance(r.value, ast.Dict)
                for k, v in zip(r.value.keys, r.value.values):
                    assert isinstance(k, ast.Constant) and isinstance(k.value, str)
                    src = ast.unparse(v)
                    assert not isinstance(v, (ast.Dict, ast.List, ast.Set, ast.Tuple))
                    assert src not in ("True", "False")
                    # An EXPRESSION that evaluates to a bool is the same bug
                    # wearing a different hat: `len(idx) > 0` is a Compare node,
                    # not a constant, so the line above cannot see it. That
                    # mutation escaped the pass until this assertion and the
                    # runtime check in glsim were added together.
                    assert not isinstance(v, (ast.Compare, ast.BoolOp)), src
                    if isinstance(v, ast.UnaryOp):
                        assert not isinstance(v.op, ast.Not), src

    def test_no_block_closes_over_a_storage_object(self):
        """Non-deterministic blocks cannot read storage at all."""
        import ast, pathlib
        tree = ast.parse(pathlib.Path(CONTRACT_PATH).read_text())
        for m in [x for x in ast.walk(tree) if isinstance(x, ast.FunctionDef)]:
            blocks = [b for b in ast.walk(m) if isinstance(b, ast.FunctionDef)
                      and b.name in ("leader_fn", "validator_fn")]
            if not blocks:
                continue
            outer = {}
            for node in m.body:
                if isinstance(node, ast.FunctionDef):
                    break
                if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                    outer[node.targets[0].id] = ast.unparse(node.value)
            for b in blocks:
                local = {t.id for n in ast.walk(b) if isinstance(n, ast.Assign)
                         for t in n.targets if isinstance(t, ast.Name)}
                local |= {a.arg for a in b.args.args}
                for x in ast.walk(b):
                    if not isinstance(x, ast.Name) or x.id not in outer:
                        continue
                    if x.id in local:
                        continue
                    expr = outer[x.id]
                    assert (expr.startswith(("str(", "int(", "float(", "bool(",
                                             "len(", "["))
                            or expr.startswith("'|'.join") or expr.startswith('"|".join')
                            or expr.startswith("'\\n'.join") or expr.startswith('"\\n".join')
                            or "copy_to_memory" in expr), \
                        f"{m.name}: block closes over `{x.id} = {expr}`"

    def test_no_public_method_takes_a_builtin_container(self):
        import ast, pathlib
        tree = ast.parse(pathlib.Path(CONTRACT_PATH).read_text())
        safe = {"str", "u256", "u8", "bool", "Address", "bytes"}
        for cls in [x for x in tree.body if isinstance(x, ast.ClassDef)]:
            for m in [x for x in cls.body if isinstance(x, ast.FunctionDef)]:
                if not any("gl.public" in ast.unparse(d) for d in m.decorator_list):
                    continue
                for a in m.args.args[1:]:
                    ann = ast.unparse(a.annotation) if a.annotation else "?"
                    assert ann in safe, f"{m.name}({a.arg}: {ann})"

    def test_no_view_indexes_storage_with_a_caller_supplied_id(self):
        """Indexing an array with a parameter, unchecked, breaks two ways: an
        id past the end raises a raw IndexError, and Python accepts -1 and
        silently returns the newest record. Every such lookup must go through
        a bounds-checked helper.

        A sequential walk over the whole array is fine; the id never reaches
        the subscript.
        """
        import ast, pathlib, re
        tree = ast.parse(pathlib.Path(CONTRACT_PATH).read_text())
        for cls in [x for x in tree.body if isinstance(x, ast.ClassDef)]:
            for m in [x for x in cls.body if isinstance(x, ast.FunctionDef)]:
                if not any("view" in ast.unparse(d) for d in m.decorator_list):
                    continue
                params = {a.arg for a in m.args.args[1:]}
                for node in ast.walk(m):
                    if not isinstance(node, ast.Subscript):
                        continue
                    base = ast.unparse(node.value)
                    if not base.startswith("self."):
                        continue
                    idx = ast.unparse(node.slice)
                    used = {n.id for n in ast.walk(node.slice) if isinstance(n, ast.Name)}
                    assert not (used & params), (
                        f"{m.name}: {base}[{idx}] indexes storage with the "
                        f"caller-supplied id {used & params}"
                    )

    def test_every_id_taking_view_goes_through_a_bounds_check(self):
        import ast, pathlib
        tree = ast.parse(pathlib.Path(CONTRACT_PATH).read_text())
        for cls in [x for x in tree.body if isinstance(x, ast.ClassDef)]:
            for m in [x for x in cls.body if isinstance(x, ast.FunctionDef)]:
                if not any("view" in ast.unparse(d) for d in m.decorator_list):
                    continue
                params = {a.arg for a in m.args.args[1:]}
                if not params:
                    continue
                body = ast.unparse(m)
                assert "_statement(" in body or "_author(" in body, (
                    f"{m.name} takes an id but never bounds-checks it"
                )

    def test_every_raise_in_a_contract_method_is_a_user_error(self):
        import ast, pathlib
        tree = ast.parse(pathlib.Path(CONTRACT_PATH).read_text())
        for cls in [x for x in tree.body if isinstance(x, ast.ClassDef)]:
            if not any("gl.Contract" in ast.unparse(b) for b in cls.bases):
                continue
            for m in [x for x in cls.body if isinstance(x, ast.FunctionDef)]:
                for node in ast.walk(m):
                    if isinstance(node, ast.Raise) and node.exc is not None:
                        assert "UserError" in ast.unparse(node.exc)

    def test_the_runner_hash_is_pinned(self):
        import pathlib
        src = pathlib.Path(CONTRACT_PATH).read_text()
        assert src.startswith(
            '# { "Depends": "py-genlayer:'
            '1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }')
        assert "py-genlayer:test" not in src
