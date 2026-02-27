import pytest
from web3 import Web3
from conftest import post_test_job, submit_and_accept_bid


class TestDispute:
    """Test dispute resolution edge cases."""

    def test_funds_locked_during_dispute(self, w3, marketplace_contract, accounts):
        """Cannot release payments while job is Disputed."""
        employer = accounts[1]
        freelancer = accounts[2]
        amounts = [Web3.to_wei(1, "ether")]

        job_id, ms_ids = post_test_job(w3, marketplace_contract, employer, amounts)
        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)

        # Mark milestone complete
        marketplace_contract.functions.markMilestoneComplete(job_id, ms_ids[0]).transact({"from": freelancer})

        # Raise dispute
        marketplace_contract.functions.raiseDispute(job_id).transact({"from": freelancer})

        # Try to release payment — should revert (job is Disputed)
        with pytest.raises(Exception):
            marketplace_contract.functions.releaseMilestonePayment(job_id, ms_ids[0]).transact({"from": employer})

    def test_one_vote_does_not_resolve(self, w3, marketplace_contract, arbitration_contract, accounts):
        """A single arbitrator vote should not resolve the dispute."""
        employer = accounts[1]
        freelancer = accounts[2]
        arb1 = accounts[7]
        amounts = [Web3.to_wei(2, "ether")]

        job_id, _ = post_test_job(w3, marketplace_contract, employer, amounts)
        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)
        marketplace_contract.functions.raiseDispute(job_id).transact({"from": employer})

        # One arbitrator votes
        arbitration_contract.functions.submitVote(job_id, freelancer).transact({"from": arb1})

        # Dispute should NOT be resolved yet
        dispute = arbitration_contract.functions.disputes(job_id).call()
        assert dispute[2] == False  # resolved is at index 2

        # Job should still be Disputed
        job = marketplace_contract.functions.getJob(job_id).call()
        assert job[6] == 3  # JobStatus.Disputed == 3

    def test_two_votes_resolve_to_winner(self, w3, marketplace_contract, arbitration_contract, accounts):
        """Two arbitrators voting for the same winner should resolve the dispute."""
        employer = accounts[1]
        freelancer = accounts[2]
        arb1, arb2 = accounts[7], accounts[8]
        amounts = [Web3.to_wei(3, "ether")]

        job_id, _ = post_test_job(w3, marketplace_contract, employer, amounts)
        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)
        marketplace_contract.functions.raiseDispute(job_id).transact({"from": employer})

        freelancer_balance_before = w3.eth.get_balance(freelancer)

        # Two arbitrators vote for freelancer
        arbitration_contract.functions.submitVote(job_id, freelancer).transact({"from": arb1})
        arbitration_contract.functions.submitVote(job_id, freelancer).transact({"from": arb2})

        # Dispute should be resolved
        dispute = arbitration_contract.functions.disputes(job_id).call()
        assert dispute[2] == True  # resolved

        # Job should be Completed
        job = marketplace_contract.functions.getJob(job_id).call()
        assert job[6] == 2  # JobStatus.Completed == 2

        # Freelancer should have received funds
        freelancer_balance_after = w3.eth.get_balance(freelancer)
        assert freelancer_balance_after > freelancer_balance_before

    def test_timeout_splits_fifty_fifty(self, w3, marketplace_contract, arbitration_contract, accounts):
        """After 7 days with no consensus, funds split 50/50."""
        employer = accounts[1]
        freelancer = accounts[2]
        amounts = [Web3.to_wei(4, "ether")]

        job_id, _ = post_test_job(w3, marketplace_contract, employer, amounts)
        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)
        marketplace_contract.functions.raiseDispute(job_id).transact({"from": employer})

        # Need at least one vote so raisedAt is set in the arbitration contract
        arbitration_contract.functions.submitVote(job_id, freelancer).transact({"from": accounts[7]})

        # Advance time by 7 days + 1 second
        w3.provider.make_request("evm_increaseTime", [7 * 86400 + 1])
        w3.provider.make_request("evm_mine", [])

        employer_balance_before = w3.eth.get_balance(employer)
        freelancer_balance_before = w3.eth.get_balance(freelancer)

        # Claim timeout
        arbitration_contract.functions.claimTimeout(job_id).transact({"from": employer})

        employer_balance_after = w3.eth.get_balance(employer)
        freelancer_balance_after = w3.eth.get_balance(freelancer)

        # Both should have received approximately 2 ETH each (minus gas for employer)
        # Freelancer gets exact 2 ETH (no gas cost for receiving)
        freelancer_gain = freelancer_balance_after - freelancer_balance_before
        assert freelancer_gain == Web3.to_wei(2, "ether")

        # Job should be completed
        job = marketplace_contract.functions.getJob(job_id).call()
        assert job[6] == 2  # Completed

    def test_replaced_arbitrator_can_vote(self, w3, marketplace_contract, arbitration_contract, accounts):
        """A replaced arbitrator can participate in dispute resolution."""
        employer = accounts[1]
        freelancer = accounts[2]
        new_arb = accounts[6]
        arb2, arb3 = accounts[8], accounts[9]
        amounts = [Web3.to_wei(1, "ether")]

        job_id, _ = post_test_job(w3, marketplace_contract, employer, amounts)
        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)
        marketplace_contract.functions.raiseDispute(job_id).transact({"from": freelancer})

        # Replace arbitrator[0] (accounts[7]) with accounts[6]
        arbitration_contract.functions.replaceArbitrator(0, new_arb).transact({"from": accounts[0]})

        # New arbitrator and one original arbitrator vote
        arbitration_contract.functions.submitVote(job_id, employer).transact({"from": new_arb})
        arbitration_contract.functions.submitVote(job_id, employer).transact({"from": arb2})

        # Dispute should be resolved
        dispute = arbitration_contract.functions.disputes(job_id).call()
        assert dispute[2] == True  # resolved

        # Employer should be the winner (job completed)
        job = marketplace_contract.functions.getJob(job_id).call()
        assert job[6] == 2  # Completed
