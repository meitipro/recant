"""Integration tests, run against GenLayer Studio with gltest.

    pip install genlayer-test
    gltest --network studionet tests/test_integration.py

These are slower than the other two suites and they prove something different:
that the contract deploys, that storage round-trips, that the deterministic
gates fire, and that the whole leader-plus-validator cycle completes against a
real runtime rather than against tests/glsim.py.

Everything here exercises the deterministic half, which needs no inference: a
record opens, statements are added, one is withdrawn, and the refusal paths are
checked. The judging path costs a prompt and belongs in a manual Studio run.
"""

import pytest

# gltest is only needed for this file. Skip cleanly when it is absent so that
# `pytest tests/` works out of the box on a machine with nothing installed but
# pytest, and still runs everything in test_logic.py and test_e2e.py.
gltest = pytest.importorskip(
    "gltest",
    reason="integration tests need genlayer-test and a running Studio: "
           "pip install genlayer-test, then gltest --network studionet",
)
from gltest import get_contract_factory                      # noqa: E402
from gltest.assertions import tx_execution_succeeded         # noqa: E402


S0 = "We will never sell user data to anyone, under any circumstances."
S1 = "We share aggregated data with a small number of selected partners."


class TestRecant:
    @pytest.fixture
    def contract(self):
        factory = get_contract_factory(contract_file_path="recant.py")
        return factory.deploy(args=[])

    def test_a_record_opens_and_counts(self, contract):
        tx = contract.register(args=["Acme"])
        assert tx_execution_succeeded(tx)
        assert contract.record(args=[0])["author"] == "Acme"

    def test_statements_land_on_the_record_before_they_are_judged(self, contract):
        contract.register(args=["Acme"])
        assert tx_execution_succeeded(contract.state(args=[0, S0]))
        assert tx_execution_succeeded(contract.state(args=[0, S1]))
        rec = contract.record(args=[0])
        assert len(rec["statements"]) == 2
        # Recording is not judging: neither has a verdict yet.
        assert contract.verdict(args=[0]) == ""
        assert contract.verdict(args=[1]) == ""

    def test_withdrawing_does_not_delete(self, contract):
        contract.register(args=["Acme"])
        contract.state(args=[0, S0])
        assert tx_execution_succeeded(contract.withdraw(args=[0]))
        rec = contract.record(args=[0])
        assert len(rec["statements"]) == 1
        assert rec["statements"][0]["withdrawn"] is True

    def test_withdrawing_twice_is_refused(self, contract):
        contract.register(args=["Acme"])
        contract.state(args=[0, S0])
        contract.withdraw(args=[0])
        with pytest.raises(Exception):
            contract.withdraw(args=[0])

    def test_a_view_is_safe_before_any_check(self, contract):
        contract.register(args=["Acme"])
        contract.state(args=[0, S0])
        # Empty rather than raising, so a consuming contract has one branch.
        assert contract.verdict(args=[0]) == ""
        assert contract.against(args=[0]) == ""

    def test_an_unknown_statement_is_refused(self, contract):
        contract.register(args=["Acme"])
        contract.state(args=[0, S0])
        with pytest.raises(Exception):
            contract.verdict(args=[9])

    def test_a_negative_id_does_not_return_the_newest_record(self, contract):
        # Python accepts -1 and hands back the last row, correctly formatted,
        # with nothing failing anywhere.
        contract.register(args=["Acme"])
        contract.state(args=[0, S0])
        with pytest.raises(Exception):
            contract.verdict(args=[-1])
