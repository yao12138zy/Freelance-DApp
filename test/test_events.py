import pytest
from web3 import Web3
from conftest import post_test_job, submit_and_accept_bid


class TestEvents:
    """Test that events are emitted correctly."""

    def test_job_posted_event(self, w3, marketplace_contract, accounts):
        """JobPosted event should contain correct args."""
        employer = accounts[1]
        amounts = [Web3.to_wei(1, "ether"), Web3.to_wei(2, "ether")]
        total = sum(amounts)
        deadline = w3.eth.get_block("latest")["timestamp"] + 86400 * 30

        tx = marketplace_contract.functions.postJob(
            "Event Test Job", "Blockchain", deadline,
            ["M1", "M2"], amounts
        ).transact({"from": employer, "value": total})
        receipt = w3.eth.wait_for_transaction_receipt(tx)

        events = marketplace_contract.events.JobPosted().process_receipt(receipt)
        assert len(events) == 1
        evt = events[0]["args"]
        assert evt["employer"] == employer
        assert evt["category"] == "Blockchain"
        assert evt["totalBudget"] == total

    def test_payment_released_event(self, w3, marketplace_contract, accounts):
        """PaymentReleased event should contain correct amount."""
        employer = accounts[1]
        freelancer = accounts[2]
        amount = Web3.to_wei(1.5, "ether")
        amounts = [amount]

        job_id, ms_ids = post_test_job(w3, marketplace_contract, employer, amounts)
        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)
        marketplace_contract.functions.markMilestoneComplete(job_id, ms_ids[0]).transact({"from": freelancer})

        tx = marketplace_contract.functions.releaseMilestonePayment(job_id, ms_ids[0]).transact({"from": employer})
        receipt = w3.eth.wait_for_transaction_receipt(tx)

        events = marketplace_contract.events.PaymentReleased().process_receipt(receipt)
        assert len(events) == 1
        evt = events[0]["args"]
        assert evt["jobId"] == job_id
        assert evt["milestoneId"] == ms_ids[0]
        assert evt["freelancer"] == freelancer
        assert evt["amount"] == amount

    def test_bid_withdrawn_event(self, w3, marketplace_contract, accounts):
        """BidWithdrawn event should be emitted when expired bid is withdrawn."""
        employer = accounts[1]
        freelancer = accounts[2]
        amounts = [Web3.to_wei(1, "ether")]

        job_id, _ = post_test_job(w3, marketplace_contract, employer, amounts)

        # Submit bid with 1 second expiry
        tx = marketplace_contract.functions.submitBid(
            job_id, amounts[0], "Quick bid", 1  # expires in 1 second
        ).transact({"from": freelancer})
        receipt = w3.eth.wait_for_transaction_receipt(tx)
        bid_events = marketplace_contract.events.BidSubmitted().process_receipt(receipt)
        bid_id = bid_events[0]["args"]["bidId"]

        # Advance time to expire the bid
        w3.provider.make_request("evm_increaseTime", [2])
        w3.provider.make_request("evm_mine", [])

        # Withdraw expired bid
        tx = marketplace_contract.functions.withdrawExpiredBid(bid_id).transact({"from": freelancer})
        receipt = w3.eth.wait_for_transaction_receipt(tx)

        events = marketplace_contract.events.BidWithdrawn().process_receipt(receipt)
        assert len(events) == 1
        evt = events[0]["args"]
        assert evt["bidId"] == bid_id
        assert evt["freelancer"] == freelancer

    def test_dispute_resolved_event(self, w3, marketplace_contract, arbitration_contract, accounts):
        """DisputeResolved event should contain winner and amount."""
        employer = accounts[1]
        freelancer = accounts[2]
        arb1, arb2 = accounts[8], accounts[9]
        amount = Web3.to_wei(2, "ether")
        amounts = [amount]

        job_id, _ = post_test_job(w3, marketplace_contract, employer, amounts)
        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)
        marketplace_contract.functions.raiseDispute(job_id).transact({"from": employer})

        # Two votes resolve it
        arbitration_contract.functions.submitVote(job_id, freelancer).transact({"from": arb1})
        tx = arbitration_contract.functions.submitVote(job_id, freelancer).transact({"from": arb2})
        receipt = w3.eth.wait_for_transaction_receipt(tx)

        # Check DisputeResolved event on the marketplace contract
        # Need to get events from the marketplace contract, not the arbitration contract
        block = receipt["blockNumber"]
        events = marketplace_contract.events.DisputeResolved().get_logs(
            fromBlock=block, toBlock=block
        )
        assert len(events) >= 1
        evt = events[0]["args"]
        assert evt["jobId"] == job_id
        assert evt["winner"] == freelancer
        assert evt["amount"] == amount

    def test_job_status_changed_events(self, w3, marketplace_contract, accounts):
        """JobStatusChanged should fire on each status transition."""
        employer = accounts[1]
        freelancer = accounts[2]
        amounts = [Web3.to_wei(1, "ether")]

        # Post job (status: Open, no transition event expected from post)
        job_id, ms_ids = post_test_job(w3, marketplace_contract, employer, amounts)

        # Accept bid: Open -> InProgress
        tx1 = marketplace_contract.functions.submitBid(
            job_id, amounts[0], "Bid", 86400
        ).transact({"from": freelancer})
        receipt1 = w3.eth.wait_for_transaction_receipt(tx1)
        bid_events = marketplace_contract.events.BidSubmitted().process_receipt(receipt1)
        bid_id = bid_events[0]["args"]["bidId"]

        tx2 = marketplace_contract.functions.acceptBid(job_id, bid_id).transact({"from": employer})
        receipt2 = w3.eth.wait_for_transaction_receipt(tx2)
        status_events = marketplace_contract.events.JobStatusChanged().process_receipt(receipt2)
        assert len(status_events) >= 1
        assert status_events[0]["args"]["oldStatus"] == 0  # Open
        assert status_events[0]["args"]["newStatus"] == 1  # InProgress

        # Complete and release: InProgress -> Completed
        marketplace_contract.functions.markMilestoneComplete(job_id, ms_ids[0]).transact({"from": freelancer})
        tx3 = marketplace_contract.functions.releaseMilestonePayment(job_id, ms_ids[0]).transact({"from": employer})
        receipt3 = w3.eth.wait_for_transaction_receipt(tx3)
        status_events2 = marketplace_contract.events.JobStatusChanged().process_receipt(receipt3)
        assert len(status_events2) >= 1
        assert status_events2[0]["args"]["oldStatus"] == 1  # InProgress
        assert status_events2[0]["args"]["newStatus"] == 2  # Completed
