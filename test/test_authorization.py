import pytest
from web3 import Web3
from conftest import post_test_job, submit_and_accept_bid


class TestAuthorization:
    """Test that unauthorized callers are rejected."""

    def test_non_employer_cannot_release_payment(self, w3, marketplace_contract, accounts):
        """Only the employer can release milestone payments."""
        employer = accounts[1]
        freelancer = accounts[2]
        stranger = accounts[3]
        amounts = [Web3.to_wei(1, "ether")]

        job_id, ms_ids = post_test_job(w3, marketplace_contract, employer, amounts)
        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)
        marketplace_contract.functions.markMilestoneComplete(job_id, ms_ids[0]).transact({"from": freelancer})

        # Stranger tries to release payment
        with pytest.raises(Exception):
            marketplace_contract.functions.releaseMilestonePayment(job_id, ms_ids[0]).transact({"from": stranger})

    def test_non_freelancer_cannot_mark_complete(self, w3, marketplace_contract, accounts):
        """Only the accepted freelancer can mark milestones complete."""
        employer = accounts[1]
        freelancer = accounts[2]
        stranger = accounts[3]
        amounts = [Web3.to_wei(1, "ether")]

        job_id, ms_ids = post_test_job(w3, marketplace_contract, employer, amounts)
        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)

        # Stranger tries to mark complete
        with pytest.raises(Exception):
            marketplace_contract.functions.markMilestoneComplete(job_id, ms_ids[0]).transact({"from": stranger})

    def test_non_arbitrator_cannot_resolve_dispute(self, w3, marketplace_contract, accounts):
        """Only the arbitration contract can call resolveDispute."""
        employer = accounts[1]
        freelancer = accounts[2]
        stranger = accounts[3]
        amounts = [Web3.to_wei(1, "ether")]

        job_id, _ = post_test_job(w3, marketplace_contract, employer, amounts)
        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)

        # Stranger tries to resolve dispute directly on marketplace
        with pytest.raises(Exception):
            marketplace_contract.functions.resolveDispute(job_id, stranger).transact({"from": stranger})

    def test_employer_cannot_rate_twice(self, w3, marketplace_contract, accounts):
        """Employer can only rate a freelancer once per job."""
        employer = accounts[1]
        freelancer = accounts[2]
        amounts = [Web3.to_wei(1, "ether")]

        job_id, ms_ids = post_test_job(w3, marketplace_contract, employer, amounts)
        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)

        # Complete the job
        marketplace_contract.functions.markMilestoneComplete(job_id, ms_ids[0]).transact({"from": freelancer})
        marketplace_contract.functions.releaseMilestonePayment(job_id, ms_ids[0]).transact({"from": employer})

        # First rating succeeds
        marketplace_contract.functions.rateFreelancer(job_id, 5).transact({"from": employer})

        # Second rating must revert
        with pytest.raises(Exception):
            marketplace_contract.functions.rateFreelancer(job_id, 4).transact({"from": employer})

    def test_cancel_job_reverts_after_bid_accepted(self, w3, marketplace_contract, accounts):
        """Cannot cancel a job once a bid has been accepted (status is InProgress)."""
        employer = accounts[1]
        freelancer = accounts[2]
        amounts = [Web3.to_wei(1, "ether")]

        job_id, _ = post_test_job(w3, marketplace_contract, employer, amounts)
        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)

        # Job is now InProgress, cancel must revert
        with pytest.raises(Exception):
            marketplace_contract.functions.cancelJob(job_id).transact({"from": employer})
