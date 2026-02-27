"""
Harsh tests for the job/bid/milestone state machine.

Covers: illegal state transitions, double operations, boundary conditions,
bid expiry, cancel refunds, multi-milestone edge cases, pause/unpause,
and cross-role authorization.
"""
import pytest
from web3 import Web3
from conftest import post_test_job, submit_and_accept_bid


class TestJobStateMachine:
    """Test that only valid state transitions are allowed."""

    def test_cannot_raise_dispute_on_open_job(self, w3, marketplace_contract, accounts):
        """Dispute requires InProgress status."""
        employer, freelancer = accounts[1], accounts[2]
        amounts = [Web3.to_wei(1, "ether")]
        job_id, _ = post_test_job(w3, marketplace_contract, employer, amounts)

        with pytest.raises(Exception):
            marketplace_contract.functions.raiseDispute(job_id).transact({"from": employer})

    def test_cannot_raise_dispute_on_completed_job(self, w3, marketplace_contract, accounts):
        """Cannot dispute a Completed job."""
        employer, freelancer = accounts[1], accounts[2]
        amounts = [Web3.to_wei(1, "ether")]

        job_id, ms_ids = post_test_job(w3, marketplace_contract, employer, amounts)
        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)

        marketplace_contract.functions.markMilestoneComplete(job_id, ms_ids[0]).transact({"from": freelancer})
        marketplace_contract.functions.releaseMilestonePayment(job_id, ms_ids[0]).transact({"from": employer})

        job = marketplace_contract.functions.getJob(job_id).call()
        assert job[6] == 2  # Completed

        with pytest.raises(Exception):
            marketplace_contract.functions.raiseDispute(job_id).transact({"from": employer})

    def test_cannot_raise_dispute_on_cancelled_job(self, w3, marketplace_contract, accounts):
        """Cannot dispute a Cancelled job."""
        employer = accounts[1]
        amounts = [Web3.to_wei(1, "ether")]
        job_id, _ = post_test_job(w3, marketplace_contract, employer, amounts)

        marketplace_contract.functions.cancelJob(job_id).transact({"from": employer})

        with pytest.raises(Exception):
            marketplace_contract.functions.raiseDispute(job_id).transact({"from": employer})

    def test_cannot_cancel_inprogress_job(self, w3, marketplace_contract, accounts):
        """Only Open jobs can be cancelled."""
        employer, freelancer = accounts[1], accounts[2]
        amounts = [Web3.to_wei(1, "ether")]

        job_id, _ = post_test_job(w3, marketplace_contract, employer, amounts)
        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)

        with pytest.raises(Exception):
            marketplace_contract.functions.cancelJob(job_id).transact({"from": employer})

    def test_cannot_accept_bid_on_inprogress_job(self, w3, marketplace_contract, accounts):
        """Once a bid is accepted (InProgress), no more bids can be accepted."""
        employer = accounts[1]
        freelancer1, freelancer2 = accounts[2], accounts[3]
        amounts = [Web3.to_wei(1, "ether")]

        job_id, _ = post_test_job(w3, marketplace_contract, employer, amounts)

        # Submit two bids
        tx1 = marketplace_contract.functions.submitBid(
            job_id, Web3.to_wei(1, "ether"), "Bid 1", 86400
        ).transact({"from": freelancer1})
        r1 = w3.eth.wait_for_transaction_receipt(tx1)
        bid1_id = marketplace_contract.events.BidSubmitted().process_receipt(r1)[0]["args"]["bidId"]

        tx2 = marketplace_contract.functions.submitBid(
            job_id, Web3.to_wei(1, "ether"), "Bid 2", 86400
        ).transact({"from": freelancer2})
        r2 = w3.eth.wait_for_transaction_receipt(tx2)
        bid2_id = marketplace_contract.events.BidSubmitted().process_receipt(r2)[0]["args"]["bidId"]

        # Accept first bid
        marketplace_contract.functions.acceptBid(job_id, bid1_id).transact({"from": employer})

        # Second bid acceptance must revert (job is InProgress)
        with pytest.raises(Exception):
            marketplace_contract.functions.acceptBid(job_id, bid2_id).transact({"from": employer})

    def test_mark_complete_requires_inprogress(self, w3, marketplace_contract, accounts):
        """Cannot mark milestone on a Disputed job."""
        employer, freelancer = accounts[1], accounts[2]
        amounts = [Web3.to_wei(1, "ether"), Web3.to_wei(1, "ether")]

        job_id, ms_ids = post_test_job(w3, marketplace_contract, employer, amounts)
        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)
        marketplace_contract.functions.raiseDispute(job_id).transact({"from": freelancer})

        with pytest.raises(Exception):
            marketplace_contract.functions.markMilestoneComplete(job_id, ms_ids[0]).transact({"from": freelancer})

    def test_stranger_cannot_raise_dispute(self, w3, marketplace_contract, accounts):
        """Only employer or freelancer can raise a dispute."""
        employer, freelancer, stranger = accounts[1], accounts[2], accounts[5]
        amounts = [Web3.to_wei(1, "ether")]

        job_id, _ = post_test_job(w3, marketplace_contract, employer, amounts)
        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)

        with pytest.raises(Exception):
            marketplace_contract.functions.raiseDispute(job_id).transact({"from": stranger})


class TestMilestoneEdgeCases:
    """Milestone completion and payment edge cases."""

    def test_double_mark_complete_reverts(self, w3, marketplace_contract, accounts):
        """Cannot mark the same milestone complete twice."""
        employer, freelancer = accounts[1], accounts[2]
        amounts = [Web3.to_wei(1, "ether")]

        job_id, ms_ids = post_test_job(w3, marketplace_contract, employer, amounts)
        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)

        marketplace_contract.functions.markMilestoneComplete(job_id, ms_ids[0]).transact({"from": freelancer})

        with pytest.raises(Exception):
            marketplace_contract.functions.markMilestoneComplete(job_id, ms_ids[0]).transact({"from": freelancer})

    def test_double_payment_reverts(self, w3, marketplace_contract, accounts):
        """Cannot pay the same milestone twice."""
        employer, freelancer = accounts[1], accounts[2]
        amounts = [Web3.to_wei(1, "ether")]

        job_id, ms_ids = post_test_job(w3, marketplace_contract, employer, amounts)
        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)

        marketplace_contract.functions.markMilestoneComplete(job_id, ms_ids[0]).transact({"from": freelancer})
        marketplace_contract.functions.releaseMilestonePayment(job_id, ms_ids[0]).transact({"from": employer})

        with pytest.raises(Exception):
            marketplace_contract.functions.releaseMilestonePayment(job_id, ms_ids[0]).transact({"from": employer})

    def test_pay_uncompleted_milestone_reverts(self, w3, marketplace_contract, accounts):
        """Cannot release payment for a milestone that hasn't been marked complete."""
        employer, freelancer = accounts[1], accounts[2]
        amounts = [Web3.to_wei(1, "ether")]

        job_id, ms_ids = post_test_job(w3, marketplace_contract, employer, amounts)
        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)

        with pytest.raises(Exception):
            marketplace_contract.functions.releaseMilestonePayment(job_id, ms_ids[0]).transact({"from": employer})

    def test_release_all_only_pays_completed(self, w3, marketplace_contract, accounts):
        """releaseAllPayments only pays completed milestones, skips others."""
        employer, freelancer = accounts[1], accounts[2]
        amounts = [Web3.to_wei(1, "ether"), Web3.to_wei(2, "ether"), Web3.to_wei(3, "ether")]

        job_id, ms_ids = post_test_job(w3, marketplace_contract, employer, amounts)
        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)

        # Only complete first two
        marketplace_contract.functions.markMilestoneComplete(job_id, ms_ids[0]).transact({"from": freelancer})
        marketplace_contract.functions.markMilestoneComplete(job_id, ms_ids[1]).transact({"from": freelancer})

        freelancer_before = w3.eth.get_balance(freelancer)
        marketplace_contract.functions.releaseAllPayments(job_id).transact({"from": employer})
        freelancer_after = w3.eth.get_balance(freelancer)

        # Should receive 1 + 2 = 3 ETH, not 6 ETH
        assert freelancer_after - freelancer_before == Web3.to_wei(3, "ether")

        # Job should NOT be completed (ms_ids[2] still unpaid)
        job = marketplace_contract.functions.getJob(job_id).call()
        assert job[6] == 1  # still InProgress

    def test_milestone_cross_job_reverts(self, w3, marketplace_contract, accounts):
        """Cannot mark/pay a milestone that belongs to a different job."""
        employer, freelancer = accounts[1], accounts[2]

        job1_id, ms1_ids = post_test_job(w3, marketplace_contract, employer, [Web3.to_wei(1, "ether")])
        job2_id, ms2_ids = post_test_job(w3, marketplace_contract, employer, [Web3.to_wei(1, "ether")])

        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job1_id)
        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job2_id)

        # Try to mark job2's milestone under job1
        with pytest.raises(Exception):
            marketplace_contract.functions.markMilestoneComplete(job1_id, ms2_ids[0]).transact({"from": freelancer})

    def test_auto_complete_on_last_milestone_payment(self, w3, marketplace_contract, accounts):
        """Job automatically transitions to Completed when all milestones are paid."""
        employer, freelancer = accounts[1], accounts[2]
        amounts = [Web3.to_wei(1, "ether"), Web3.to_wei(1, "ether")]

        job_id, ms_ids = post_test_job(w3, marketplace_contract, employer, amounts)
        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)

        # Complete and pay first
        marketplace_contract.functions.markMilestoneComplete(job_id, ms_ids[0]).transact({"from": freelancer})
        marketplace_contract.functions.releaseMilestonePayment(job_id, ms_ids[0]).transact({"from": employer})

        # Still InProgress
        job = marketplace_contract.functions.getJob(job_id).call()
        assert job[6] == 1

        # Complete and pay second
        marketplace_contract.functions.markMilestoneComplete(job_id, ms_ids[1]).transact({"from": freelancer})
        marketplace_contract.functions.releaseMilestonePayment(job_id, ms_ids[1]).transact({"from": employer})

        # Now Completed
        job = marketplace_contract.functions.getJob(job_id).call()
        assert job[6] == 2


class TestBidEdgeCases:
    """Bid submission, expiry, and withdrawal."""

    def test_employer_cannot_bid_on_own_job(self, w3, marketplace_contract, accounts):
        """Employer bidding on their own job must revert."""
        employer = accounts[1]
        amounts = [Web3.to_wei(1, "ether")]
        job_id, _ = post_test_job(w3, marketplace_contract, employer, amounts)

        with pytest.raises(Exception):
            marketplace_contract.functions.submitBid(
                job_id, Web3.to_wei(1, "ether"), "Self bid", 86400
            ).transact({"from": employer})

    def test_zero_amount_bid_reverts(self, w3, marketplace_contract, accounts):
        """Bid with 0 amount must revert."""
        employer, freelancer = accounts[1], accounts[2]
        amounts = [Web3.to_wei(1, "ether")]
        job_id, _ = post_test_job(w3, marketplace_contract, employer, amounts)

        with pytest.raises(Exception):
            marketplace_contract.functions.submitBid(
                job_id, 0, "Free work", 86400
            ).transact({"from": freelancer})

    def test_bid_on_cancelled_job_reverts(self, w3, marketplace_contract, accounts):
        """Cannot bid on a Cancelled job."""
        employer, freelancer = accounts[1], accounts[2]
        amounts = [Web3.to_wei(1, "ether")]
        job_id, _ = post_test_job(w3, marketplace_contract, employer, amounts)

        marketplace_contract.functions.cancelJob(job_id).transact({"from": employer})

        with pytest.raises(Exception):
            marketplace_contract.functions.submitBid(
                job_id, Web3.to_wei(1, "ether"), "Late bid", 86400
            ).transact({"from": freelancer})

    def test_accept_expired_bid_reverts(self, w3, marketplace_contract, accounts):
        """Cannot accept a bid after its expiry time."""
        employer, freelancer = accounts[1], accounts[2]
        amounts = [Web3.to_wei(1, "ether")]
        job_id, _ = post_test_job(w3, marketplace_contract, employer, amounts)

        # Submit bid with 1-second duration
        tx = marketplace_contract.functions.submitBid(
            job_id, Web3.to_wei(1, "ether"), "Quick bid", 1
        ).transact({"from": freelancer})
        receipt = w3.eth.wait_for_transaction_receipt(tx)
        bid_id = marketplace_contract.events.BidSubmitted().process_receipt(receipt)[0]["args"]["bidId"]

        # Advance time past expiry
        w3.provider.make_request("evm_increaseTime", [10])
        w3.provider.make_request("evm_mine", [])

        with pytest.raises(Exception):
            marketplace_contract.functions.acceptBid(job_id, bid_id).transact({"from": employer})

    def test_withdraw_non_expired_bid_reverts(self, w3, marketplace_contract, accounts):
        """Cannot withdraw a bid that hasn't expired yet."""
        employer, freelancer = accounts[1], accounts[2]
        amounts = [Web3.to_wei(1, "ether")]
        job_id, _ = post_test_job(w3, marketplace_contract, employer, amounts)

        tx = marketplace_contract.functions.submitBid(
            job_id, Web3.to_wei(1, "ether"), "My bid", 86400
        ).transact({"from": freelancer})
        receipt = w3.eth.wait_for_transaction_receipt(tx)
        bid_id = marketplace_contract.events.BidSubmitted().process_receipt(receipt)[0]["args"]["bidId"]

        with pytest.raises(Exception):
            marketplace_contract.functions.withdrawExpiredBid(bid_id).transact({"from": freelancer})

    def test_stranger_cannot_withdraw_bid(self, w3, marketplace_contract, accounts):
        """Only the bid owner can withdraw their expired bid."""
        employer, freelancer, stranger = accounts[1], accounts[2], accounts[5]
        amounts = [Web3.to_wei(1, "ether")]
        job_id, _ = post_test_job(w3, marketplace_contract, employer, amounts)

        tx = marketplace_contract.functions.submitBid(
            job_id, Web3.to_wei(1, "ether"), "My bid", 1
        ).transact({"from": freelancer})
        receipt = w3.eth.wait_for_transaction_receipt(tx)
        bid_id = marketplace_contract.events.BidSubmitted().process_receipt(receipt)[0]["args"]["bidId"]

        w3.provider.make_request("evm_increaseTime", [10])
        w3.provider.make_request("evm_mine", [])

        with pytest.raises(Exception):
            marketplace_contract.functions.withdrawExpiredBid(bid_id).transact({"from": stranger})

    def test_reject_bid_only_by_employer(self, w3, marketplace_contract, accounts):
        """Only the employer can reject bids."""
        employer, freelancer, stranger = accounts[1], accounts[2], accounts[5]
        amounts = [Web3.to_wei(1, "ether")]
        job_id, _ = post_test_job(w3, marketplace_contract, employer, amounts)

        tx = marketplace_contract.functions.submitBid(
            job_id, Web3.to_wei(1, "ether"), "My bid", 86400
        ).transact({"from": freelancer})
        receipt = w3.eth.wait_for_transaction_receipt(tx)
        bid_id = marketplace_contract.events.BidSubmitted().process_receipt(receipt)[0]["args"]["bidId"]

        with pytest.raises(Exception):
            marketplace_contract.functions.rejectBid(bid_id).transact({"from": stranger})


class TestCancelAndRefund:
    """Cancel job returns exact escrow amount."""

    def test_cancel_refunds_exact_amount(self, w3, marketplace_contract, accounts):
        """Employer receives back the exact totalBudget on cancel."""
        employer = accounts[1]
        amounts = [Web3.to_wei(2, "ether"), Web3.to_wei(3, "ether")]
        total = sum(amounts)

        balance_before = w3.eth.get_balance(employer)
        job_id, _ = post_test_job(w3, marketplace_contract, employer, amounts)
        balance_after_post = w3.eth.get_balance(employer)

        marketplace_contract.functions.cancelJob(job_id).transact({"from": employer})
        balance_after_cancel = w3.eth.get_balance(employer)

        # Employer paid total + gas for postJob, then got total back - gas for cancel
        # The net difference from before-post to after-cancel should only be gas costs
        gas_spent = balance_before - balance_after_cancel
        assert gas_spent < Web3.to_wei(0.01, "ether")  # just gas, not escrow loss

    def test_double_cancel_reverts(self, w3, marketplace_contract, accounts):
        """Cannot cancel a job twice."""
        employer = accounts[1]
        amounts = [Web3.to_wei(1, "ether")]
        job_id, _ = post_test_job(w3, marketplace_contract, employer, amounts)

        marketplace_contract.functions.cancelJob(job_id).transact({"from": employer})

        with pytest.raises(Exception):
            marketplace_contract.functions.cancelJob(job_id).transact({"from": employer})

    def test_non_employer_cannot_cancel(self, w3, marketplace_contract, accounts):
        """Only the employer can cancel their job."""
        employer, stranger = accounts[1], accounts[5]
        amounts = [Web3.to_wei(1, "ether")]
        job_id, _ = post_test_job(w3, marketplace_contract, employer, amounts)

        with pytest.raises(Exception):
            marketplace_contract.functions.cancelJob(job_id).transact({"from": stranger})


class TestPostJobValidation:
    """postJob input validation."""

    def test_zero_milestones_reverts(self, w3, marketplace_contract, accounts):
        """Must have at least one milestone."""
        employer = accounts[1]
        deadline = w3.eth.get_block("latest")["timestamp"] + 86400 * 30

        with pytest.raises(Exception):
            marketplace_contract.functions.postJob(
                "Empty Job", "Web Dev", deadline, [], []
            ).transact({"from": employer, "value": 0})

    def test_mismatched_milestone_arrays_reverts(self, w3, marketplace_contract, accounts):
        """Descriptions and amounts arrays must be same length."""
        employer = accounts[1]
        deadline = w3.eth.get_block("latest")["timestamp"] + 86400 * 30

        with pytest.raises(Exception):
            marketplace_contract.functions.postJob(
                "Bad Job", "Web Dev", deadline,
                ["M1", "M2"], [Web3.to_wei(1, "ether")]
            ).transact({"from": employer, "value": Web3.to_wei(1, "ether")})

    def test_past_deadline_reverts(self, w3, marketplace_contract, accounts):
        """Deadline must be in the future."""
        employer = accounts[1]
        past_deadline = w3.eth.get_block("latest")["timestamp"] - 1

        with pytest.raises(Exception):
            marketplace_contract.functions.postJob(
                "Past Job", "Web Dev", past_deadline,
                ["M1"], [Web3.to_wei(1, "ether")]
            ).transact({"from": employer, "value": Web3.to_wei(1, "ether")})

    def test_zero_milestone_amount_reverts(self, w3, marketplace_contract, accounts):
        """Each milestone must have amount > 0."""
        employer = accounts[1]
        deadline = w3.eth.get_block("latest")["timestamp"] + 86400 * 30

        with pytest.raises(Exception):
            marketplace_contract.functions.postJob(
                "Zero MS", "Web Dev", deadline,
                ["M1"], [0]
            ).transact({"from": employer, "value": 0})


class TestPauseUnpause:
    """Contract pause functionality."""

    def test_pause_blocks_post_job(self, w3, marketplace_contract, accounts):
        """Cannot post a job when contract is paused."""
        owner = accounts[0]
        employer = accounts[1]
        deadline = w3.eth.get_block("latest")["timestamp"] + 86400 * 30

        marketplace_contract.functions.pause().transact({"from": owner})

        with pytest.raises(Exception):
            marketplace_contract.functions.postJob(
                "Paused Job", "Web Dev", deadline,
                ["M1"], [Web3.to_wei(1, "ether")]
            ).transact({"from": employer, "value": Web3.to_wei(1, "ether")})

        # Unpause for subsequent tests
        marketplace_contract.functions.unpause().transact({"from": owner})

    def test_non_owner_cannot_pause(self, w3, marketplace_contract, accounts):
        """Only owner can pause the contract."""
        stranger = accounts[5]

        with pytest.raises(Exception):
            marketplace_contract.functions.pause().transact({"from": stranger})

    def test_unpause_restores_functionality(self, w3, marketplace_contract, accounts):
        """After unpausing, operations work normally."""
        owner = accounts[0]
        employer = accounts[1]
        deadline = w3.eth.get_block("latest")["timestamp"] + 86400 * 30

        marketplace_contract.functions.pause().transact({"from": owner})
        marketplace_contract.functions.unpause().transact({"from": owner})

        # Should work now
        tx = marketplace_contract.functions.postJob(
            "Unpaused Job", "Web Dev", deadline,
            ["M1"], [Web3.to_wei(1, "ether")]
        ).transact({"from": employer, "value": Web3.to_wei(1, "ether")})
        receipt = w3.eth.wait_for_transaction_receipt(tx)
        assert receipt.status == 1


class TestResolveDisputeDirectCalls:
    """Direct calls to resolveDispute / resolveDisputeWithSplit."""

    def test_resolve_dispute_only_by_arbitration_contract(self, w3, marketplace_contract, accounts):
        """resolveDispute can only be called by the arbitration contract address."""
        employer, freelancer = accounts[1], accounts[2]
        amounts = [Web3.to_wei(1, "ether")]

        job_id, _ = post_test_job(w3, marketplace_contract, employer, amounts)
        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)
        marketplace_contract.functions.raiseDispute(job_id).transact({"from": employer})

        # Owner tries to call directly — should revert
        with pytest.raises(Exception):
            marketplace_contract.functions.resolveDispute(
                job_id, employer
            ).transact({"from": accounts[0]})

    def test_resolve_dispute_with_split_only_by_arbitration_contract(self, w3, marketplace_contract, accounts):
        """resolveDisputeWithSplit can only be called by the arbitration contract."""
        employer, freelancer = accounts[1], accounts[2]
        amounts = [Web3.to_wei(2, "ether")]

        job_id, _ = post_test_job(w3, marketplace_contract, employer, amounts)
        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)
        marketplace_contract.functions.raiseDispute(job_id).transact({"from": employer})

        with pytest.raises(Exception):
            marketplace_contract.functions.resolveDisputeWithSplit(
                job_id, employer, Web3.to_wei(1, "ether"),
                freelancer, Web3.to_wei(1, "ether")
            ).transact({"from": accounts[0]})


class TestRatingEdgeCases:
    """Rating system edge cases."""

    def test_cannot_rate_open_job(self, w3, marketplace_contract, accounts):
        """Cannot rate unless job is Completed."""
        employer = accounts[1]
        amounts = [Web3.to_wei(1, "ether")]
        job_id, _ = post_test_job(w3, marketplace_contract, employer, amounts)

        with pytest.raises(Exception):
            marketplace_contract.functions.rateFreelancer(job_id, 5).transact({"from": employer})

    def test_rating_out_of_range_reverts(self, w3, marketplace_contract, accounts):
        """Rating must be 1-5."""
        employer, freelancer = accounts[1], accounts[2]
        amounts = [Web3.to_wei(1, "ether")]

        job_id, ms_ids = post_test_job(w3, marketplace_contract, employer, amounts)
        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)
        marketplace_contract.functions.markMilestoneComplete(job_id, ms_ids[0]).transact({"from": freelancer})
        marketplace_contract.functions.releaseMilestonePayment(job_id, ms_ids[0]).transact({"from": employer})

        with pytest.raises(Exception):
            marketplace_contract.functions.rateFreelancer(job_id, 0).transact({"from": employer})

        with pytest.raises(Exception):
            marketplace_contract.functions.rateFreelancer(job_id, 6).transact({"from": employer})

    def test_freelancer_cannot_rate(self, w3, marketplace_contract, accounts):
        """Only employer can rate."""
        employer, freelancer = accounts[1], accounts[2]
        amounts = [Web3.to_wei(1, "ether")]

        job_id, ms_ids = post_test_job(w3, marketplace_contract, employer, amounts)
        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)
        marketplace_contract.functions.markMilestoneComplete(job_id, ms_ids[0]).transact({"from": freelancer})
        marketplace_contract.functions.releaseMilestonePayment(job_id, ms_ids[0]).transact({"from": employer})

        with pytest.raises(Exception):
            marketplace_contract.functions.rateFreelancer(job_id, 5).transact({"from": freelancer})

    def test_rating_accumulates_correctly(self, w3, marketplace_contract, accounts):
        """Multiple ratings from different jobs accumulate in the profile."""
        employer, freelancer = accounts[1], accounts[2]

        # Create a profile for the freelancer
        marketplace_contract.functions.createProfile("Alice", "Developer").transact({"from": freelancer})

        # Complete two jobs and rate
        for rating in [5, 3]:
            amounts = [Web3.to_wei(1, "ether")]
            job_id, ms_ids = post_test_job(w3, marketplace_contract, employer, amounts)
            submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)
            marketplace_contract.functions.markMilestoneComplete(job_id, ms_ids[0]).transact({"from": freelancer})
            marketplace_contract.functions.releaseMilestonePayment(job_id, ms_ids[0]).transact({"from": employer})
            marketplace_contract.functions.rateFreelancer(job_id, rating).transact({"from": employer})

        profile = marketplace_contract.functions.getProfile(freelancer).call()
        assert profile[4] == 8   # reputationScore: 5 + 3
        assert profile[5] == 2   # ratingCount
