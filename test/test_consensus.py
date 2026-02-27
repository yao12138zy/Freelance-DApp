"""
Harsh tests for the 2-of-3 arbitration consensus mechanism.

Covers: split votes, tie-breaking, double voting, non-arbitrator voting,
vote after resolution, timeout edge cases, odd-wei splits, and
consensus for either party (employer or freelancer).
"""
import pytest
from web3 import Web3
from conftest import post_test_job, submit_and_accept_bid


def _setup_disputed_job(w3, marketplace_contract, employer, freelancer, eth_amount=2):
    """Helper: post a job, accept a bid, raise a dispute. Returns job_id."""
    amounts = [Web3.to_wei(eth_amount, "ether")]
    job_id, _ = post_test_job(w3, marketplace_contract, employer, amounts)
    submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)
    marketplace_contract.functions.raiseDispute(job_id).transact({"from": employer})
    return job_id


class TestConsensus:
    """Core consensus logic."""

    def test_three_way_split_no_consensus(self, w3, marketplace_contract, arbitration_contract, accounts):
        """Three arbitrators each vote for a different address — no resolution."""
        employer, freelancer = accounts[1], accounts[2]
        arb1, arb2, arb3 = accounts[7], accounts[8], accounts[9]
        job_id = _setup_disputed_job(w3, marketplace_contract, employer, freelancer)

        # All three vote for different parties
        arbitration_contract.functions.submitVote(job_id, freelancer).transact({"from": arb1})
        arbitration_contract.functions.submitVote(job_id, employer).transact({"from": arb2})
        # arb3 votes for a third-party address (neither employer nor freelancer)
        arbitration_contract.functions.submitVote(job_id, accounts[5]).transact({"from": arb3})

        dispute = arbitration_contract.functions.disputes(job_id).call()
        assert dispute[1] == 3   # voteCount == 3
        assert dispute[2] is False  # NOT resolved

        job = marketplace_contract.functions.getJob(job_id).call()
        assert job[6] == 3  # still Disputed

    def test_tiebreaker_second_vote_resolves(self, w3, marketplace_contract, arbitration_contract, accounts):
        """First vote for employer, second for freelancer, third for employer — employer wins."""
        employer, freelancer = accounts[1], accounts[2]
        arb1, arb2, arb3 = accounts[7], accounts[8], accounts[9]
        job_id = _setup_disputed_job(w3, marketplace_contract, employer, freelancer)

        employer_before = w3.eth.get_balance(employer)

        arbitration_contract.functions.submitVote(job_id, employer).transact({"from": arb1})
        arbitration_contract.functions.submitVote(job_id, freelancer).transact({"from": arb2})
        # Third vote breaks the tie — employer gets 2-of-3
        arbitration_contract.functions.submitVote(job_id, employer).transact({"from": arb3})

        dispute = arbitration_contract.functions.disputes(job_id).call()
        assert dispute[2] is True  # resolved

        # Employer should have received funds
        employer_after = w3.eth.get_balance(employer)
        assert employer_after > employer_before

    def test_consensus_on_second_vote(self, w3, marketplace_contract, arbitration_contract, accounts):
        """Two votes for same party triggers immediate resolution — no need for third."""
        employer, freelancer = accounts[1], accounts[2]
        arb1, arb2 = accounts[7], accounts[8]
        job_id = _setup_disputed_job(w3, marketplace_contract, employer, freelancer)

        freelancer_before = w3.eth.get_balance(freelancer)

        arbitration_contract.functions.submitVote(job_id, freelancer).transact({"from": arb1})
        arbitration_contract.functions.submitVote(job_id, freelancer).transact({"from": arb2})

        dispute = arbitration_contract.functions.disputes(job_id).call()
        assert dispute[1] == 2  # only 2 votes needed
        assert dispute[2] is True

        freelancer_after = w3.eth.get_balance(freelancer)
        assert freelancer_after > freelancer_before

    def test_consensus_for_employer(self, w3, marketplace_contract, arbitration_contract, accounts):
        """Consensus in employer's favor sends escrowed ETH to employer."""
        employer, freelancer = accounts[1], accounts[2]
        arb1, arb2 = accounts[7], accounts[8]
        amounts = [Web3.to_wei(5, "ether")]

        job_id, _ = post_test_job(w3, marketplace_contract, employer, amounts)
        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)
        marketplace_contract.functions.raiseDispute(job_id).transact({"from": freelancer})

        employer_before = w3.eth.get_balance(employer)

        arbitration_contract.functions.submitVote(job_id, employer).transact({"from": arb1})
        arbitration_contract.functions.submitVote(job_id, employer).transact({"from": arb2})

        employer_after = w3.eth.get_balance(employer)
        # 5 ETH should be returned to employer
        assert employer_after - employer_before == Web3.to_wei(5, "ether")

        job = marketplace_contract.functions.getJob(job_id).call()
        assert job[6] == 2  # Completed

    def test_dispute_winner_gets_exact_remaining_escrow(self, w3, marketplace_contract, arbitration_contract, accounts):
        """Winner receives exactly getRemainingEscrow() amount."""
        employer, freelancer = accounts[1], accounts[2]
        arb1, arb2 = accounts[7], accounts[8]
        amounts = [Web3.to_wei(1, "ether"), Web3.to_wei(3, "ether")]

        job_id, ms_ids = post_test_job(w3, marketplace_contract, employer, amounts)
        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)

        # Pay first milestone, then dispute
        marketplace_contract.functions.markMilestoneComplete(job_id, ms_ids[0]).transact({"from": freelancer})
        marketplace_contract.functions.releaseMilestonePayment(job_id, ms_ids[0]).transact({"from": employer})
        marketplace_contract.functions.raiseDispute(job_id).transact({"from": employer})

        remaining = marketplace_contract.functions.getRemainingEscrow(job_id).call()
        assert remaining == Web3.to_wei(3, "ether")

        freelancer_before = w3.eth.get_balance(freelancer)

        arbitration_contract.functions.submitVote(job_id, freelancer).transact({"from": arb1})
        arbitration_contract.functions.submitVote(job_id, freelancer).transact({"from": arb2})

        freelancer_after = w3.eth.get_balance(freelancer)
        assert freelancer_after - freelancer_before == remaining


class TestConsensusGuards:
    """Revert conditions on voting."""

    def test_double_vote_reverts(self, w3, marketplace_contract, arbitration_contract, accounts):
        """Same arbitrator voting twice on the same dispute must revert."""
        employer, freelancer = accounts[1], accounts[2]
        arb1 = accounts[7]
        job_id = _setup_disputed_job(w3, marketplace_contract, employer, freelancer)

        arbitration_contract.functions.submitVote(job_id, freelancer).transact({"from": arb1})

        with pytest.raises(Exception):
            arbitration_contract.functions.submitVote(job_id, employer).transact({"from": arb1})

    def test_non_arbitrator_vote_reverts(self, w3, marketplace_contract, arbitration_contract, accounts):
        """Random address cannot submit a vote."""
        employer, freelancer = accounts[1], accounts[2]
        stranger = accounts[5]
        job_id = _setup_disputed_job(w3, marketplace_contract, employer, freelancer)

        with pytest.raises(Exception):
            arbitration_contract.functions.submitVote(job_id, freelancer).transact({"from": stranger})

    def test_employer_cannot_vote(self, w3, marketplace_contract, arbitration_contract, accounts):
        """Employer is not an arbitrator and cannot vote."""
        employer, freelancer = accounts[1], accounts[2]
        job_id = _setup_disputed_job(w3, marketplace_contract, employer, freelancer)

        with pytest.raises(Exception):
            arbitration_contract.functions.submitVote(job_id, employer).transact({"from": employer})

    def test_freelancer_cannot_vote(self, w3, marketplace_contract, arbitration_contract, accounts):
        """Freelancer is not an arbitrator and cannot vote."""
        employer, freelancer = accounts[1], accounts[2]
        job_id = _setup_disputed_job(w3, marketplace_contract, employer, freelancer)

        with pytest.raises(Exception):
            arbitration_contract.functions.submitVote(job_id, freelancer).transact({"from": freelancer})

    def test_vote_on_resolved_dispute_reverts(self, w3, marketplace_contract, arbitration_contract, accounts):
        """Cannot vote on an already-resolved dispute."""
        employer, freelancer = accounts[1], accounts[2]
        arb1, arb2, arb3 = accounts[7], accounts[8], accounts[9]
        job_id = _setup_disputed_job(w3, marketplace_contract, employer, freelancer)

        # Resolve it with 2 votes
        arbitration_contract.functions.submitVote(job_id, freelancer).transact({"from": arb1})
        arbitration_contract.functions.submitVote(job_id, freelancer).transact({"from": arb2})

        # Third arbitrator tries to vote — already resolved
        with pytest.raises(Exception):
            arbitration_contract.functions.submitVote(job_id, freelancer).transact({"from": arb3})

    def test_replaced_arbitrator_cannot_vote(self, w3, marketplace_contract, arbitration_contract, accounts):
        """An arbitrator who was replaced loses voting power."""
        employer, freelancer = accounts[1], accounts[2]
        old_arb = accounts[7]
        new_arb = accounts[6]
        job_id = _setup_disputed_job(w3, marketplace_contract, employer, freelancer)

        # Replace arb1 (accounts[7]) with accounts[6]
        arbitration_contract.functions.replaceArbitrator(0, new_arb).transact({"from": accounts[0]})

        # Old arbitrator should no longer be able to vote
        with pytest.raises(Exception):
            arbitration_contract.functions.submitVote(job_id, employer).transact({"from": old_arb})

        # Restore original arbitrator for other tests
        arbitration_contract.functions.replaceArbitrator(0, old_arb).transact({"from": accounts[0]})

    def test_only_owner_can_replace_arbitrator(self, w3, marketplace_contract, arbitration_contract, accounts):
        """Non-owner cannot replace arbitrators."""
        stranger = accounts[5]

        with pytest.raises(Exception):
            arbitration_contract.functions.replaceArbitrator(0, stranger).transact({"from": stranger})

    def test_replace_arbitrator_invalid_index_reverts(self, w3, marketplace_contract, arbitration_contract, accounts):
        """Index >= 3 reverts."""
        with pytest.raises(Exception):
            arbitration_contract.functions.replaceArbitrator(3, accounts[5]).transact({"from": accounts[0]})

    def test_replace_arbitrator_zero_address_reverts(self, w3, marketplace_contract, arbitration_contract, accounts):
        """Cannot set arbitrator to zero address."""
        with pytest.raises(Exception):
            arbitration_contract.functions.replaceArbitrator(
                0, "0x0000000000000000000000000000000000000000"
            ).transact({"from": accounts[0]})


class TestTimeout:
    """Timeout / 50-50 split edge cases."""

    def test_timeout_before_seven_days_reverts(self, w3, marketplace_contract, arbitration_contract, accounts):
        """Cannot claim timeout before 7 days have elapsed."""
        employer, freelancer = accounts[1], accounts[2]
        job_id = _setup_disputed_job(w3, marketplace_contract, employer, freelancer)

        # Need at least one vote to set raisedAt
        arbitration_contract.functions.submitVote(job_id, freelancer).transact({"from": accounts[7]})

        # Advance only 6 days
        w3.provider.make_request("evm_increaseTime", [6 * 86400])
        w3.provider.make_request("evm_mine", [])

        with pytest.raises(Exception):
            arbitration_contract.functions.claimTimeout(job_id).transact({"from": employer})

    def test_timeout_at_exactly_seven_days(self, w3, marketplace_contract, arbitration_contract, accounts):
        """Timeout claim should succeed at exactly 7 days."""
        employer, freelancer = accounts[1], accounts[2]
        amounts = [Web3.to_wei(2, "ether")]
        job_id, _ = post_test_job(w3, marketplace_contract, employer, amounts)
        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)
        marketplace_contract.functions.raiseDispute(job_id).transact({"from": employer})

        arbitration_contract.functions.submitVote(job_id, freelancer).transact({"from": accounts[7]})

        # Advance exactly 7 days (604800 seconds)
        w3.provider.make_request("evm_increaseTime", [7 * 86400])
        w3.provider.make_request("evm_mine", [])

        # Should succeed
        arbitration_contract.functions.claimTimeout(job_id).transact({"from": employer})

        dispute = arbitration_contract.functions.disputes(job_id).call()
        assert dispute[2] is True

    def test_stranger_cannot_claim_timeout(self, w3, marketplace_contract, arbitration_contract, accounts):
        """Only employer or freelancer can claim timeout."""
        employer, freelancer = accounts[1], accounts[2]
        stranger = accounts[5]
        amounts = [Web3.to_wei(2, "ether")]
        job_id, _ = post_test_job(w3, marketplace_contract, employer, amounts)
        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)
        marketplace_contract.functions.raiseDispute(job_id).transact({"from": employer})

        arbitration_contract.functions.submitVote(job_id, employer).transact({"from": accounts[7]})

        w3.provider.make_request("evm_increaseTime", [7 * 86400 + 1])
        w3.provider.make_request("evm_mine", [])

        with pytest.raises(Exception):
            arbitration_contract.functions.claimTimeout(job_id).transact({"from": stranger})

    def test_freelancer_can_claim_timeout(self, w3, marketplace_contract, arbitration_contract, accounts):
        """Freelancer (not just employer) can trigger the timeout split."""
        employer, freelancer = accounts[1], accounts[2]
        amounts = [Web3.to_wei(4, "ether")]
        job_id, _ = post_test_job(w3, marketplace_contract, employer, amounts)
        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)
        marketplace_contract.functions.raiseDispute(job_id).transact({"from": freelancer})

        arbitration_contract.functions.submitVote(job_id, employer).transact({"from": accounts[7]})

        w3.provider.make_request("evm_increaseTime", [7 * 86400 + 1])
        w3.provider.make_request("evm_mine", [])

        employer_before = w3.eth.get_balance(employer)
        freelancer_before = w3.eth.get_balance(freelancer)

        # Freelancer claims the timeout
        arbitration_contract.functions.claimTimeout(job_id).transact({"from": freelancer})

        employer_after = w3.eth.get_balance(employer)
        freelancer_after = w3.eth.get_balance(freelancer)

        # Employer gets exact 2 ETH (no gas cost for receiving)
        assert employer_after - employer_before == Web3.to_wei(2, "ether")
        # Freelancer gets 2 ETH minus gas
        freelancer_gain = freelancer_after - freelancer_before
        assert freelancer_gain > 0
        assert freelancer_gain < Web3.to_wei(2, "ether")  # less due to gas

    def test_timeout_on_odd_wei_amount(self, w3, marketplace_contract, arbitration_contract, accounts):
        """Odd wei amount: freelancer gets the extra 1 wei."""
        employer, freelancer = accounts[1], accounts[2]
        odd_amount = Web3.to_wei(1, "ether") + 1  # 1 ETH + 1 wei
        amounts = [odd_amount]

        job_id, _ = post_test_job(w3, marketplace_contract, employer, amounts)
        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)
        marketplace_contract.functions.raiseDispute(job_id).transact({"from": employer})

        arbitration_contract.functions.submitVote(job_id, freelancer).transact({"from": accounts[7]})

        w3.provider.make_request("evm_increaseTime", [7 * 86400 + 1])
        w3.provider.make_request("evm_mine", [])

        employer_before = w3.eth.get_balance(employer)
        freelancer_before = w3.eth.get_balance(freelancer)

        arbitration_contract.functions.claimTimeout(job_id).transact({"from": employer})

        employer_after = w3.eth.get_balance(employer)
        freelancer_after = w3.eth.get_balance(freelancer)

        half = odd_amount // 2
        # Employer gets floor(amount/2)
        # (employer pays gas, so check approximate)
        employer_gain = employer_after - employer_before
        # Freelancer gets ceil(amount/2) = half + 1
        freelancer_gain = freelancer_after - freelancer_before
        assert freelancer_gain == half + 1  # freelancer receives, no gas cost

    def test_double_timeout_claim_reverts(self, w3, marketplace_contract, arbitration_contract, accounts):
        """Cannot claim timeout twice."""
        employer, freelancer = accounts[1], accounts[2]
        amounts = [Web3.to_wei(2, "ether")]
        job_id, _ = post_test_job(w3, marketplace_contract, employer, amounts)
        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)
        marketplace_contract.functions.raiseDispute(job_id).transact({"from": employer})

        arbitration_contract.functions.submitVote(job_id, freelancer).transact({"from": accounts[7]})

        w3.provider.make_request("evm_increaseTime", [7 * 86400 + 1])
        w3.provider.make_request("evm_mine", [])

        arbitration_contract.functions.claimTimeout(job_id).transact({"from": employer})

        # Second claim must revert (already resolved)
        with pytest.raises(Exception):
            arbitration_contract.functions.claimTimeout(job_id).transact({"from": freelancer})

    def test_timeout_after_partial_milestone_payments(self, w3, marketplace_contract, arbitration_contract, accounts):
        """Timeout split only applies to remaining (unpaid) escrow."""
        employer, freelancer = accounts[1], accounts[2]
        amounts = [Web3.to_wei(3, "ether"), Web3.to_wei(7, "ether")]

        job_id, ms_ids = post_test_job(w3, marketplace_contract, employer, amounts)
        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)

        # Pay the first 3 ETH milestone
        marketplace_contract.functions.markMilestoneComplete(job_id, ms_ids[0]).transact({"from": freelancer})
        marketplace_contract.functions.releaseMilestonePayment(job_id, ms_ids[0]).transact({"from": employer})

        # Now dispute — 7 ETH remains
        marketplace_contract.functions.raiseDispute(job_id).transact({"from": employer})

        remaining = marketplace_contract.functions.getRemainingEscrow(job_id).call()
        assert remaining == Web3.to_wei(7, "ether")

        arbitration_contract.functions.submitVote(job_id, employer).transact({"from": accounts[7]})

        w3.provider.make_request("evm_increaseTime", [7 * 86400 + 1])
        w3.provider.make_request("evm_mine", [])

        employer_before = w3.eth.get_balance(employer)
        freelancer_before = w3.eth.get_balance(freelancer)

        arbitration_contract.functions.claimTimeout(job_id).transact({"from": employer})

        employer_after = w3.eth.get_balance(employer)
        freelancer_after = w3.eth.get_balance(freelancer)

        # Each gets 3.5 ETH from the remaining 7 ETH
        freelancer_gain = freelancer_after - freelancer_before
        assert freelancer_gain == Web3.to_wei(3.5, "ether")
