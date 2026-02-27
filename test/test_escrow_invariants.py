import pytest
from web3 import Web3
from conftest import post_test_job, submit_and_accept_bid


class TestEscrowInvariants:
    """Test escrow math invariants."""

    def test_postjob_mismatched_value_reverts(self, w3, marketplace_contract, accounts):
        """postJob with msg.value != sum(milestoneAmounts) must revert."""
        employer = accounts[1]
        milestone_amounts = [Web3.to_wei(1, "ether"), Web3.to_wei(2, "ether")]
        wrong_value = Web3.to_wei(5, "ether")  # should be 3 ETH
        deadline = w3.eth.get_block("latest")["timestamp"] + 86400 * 30

        with pytest.raises(Exception):
            marketplace_contract.functions.postJob(
                "Bad Job", "Web Dev", deadline,
                ["M1", "M2"], milestone_amounts
            ).transact({"from": employer, "value": wrong_value})

    def test_sum_milestone_payments_equals_deposit(self, w3, marketplace_contract, accounts):
        """Sum of all PaymentReleased amounts must equal the original deposit."""
        employer = accounts[1]
        freelancer = accounts[2]
        amounts = [Web3.to_wei(1, "ether"), Web3.to_wei(2, "ether"), Web3.to_wei(0.5, "ether")]
        total_deposit = sum(amounts)

        job_id, ms_ids = post_test_job(w3, marketplace_contract, employer, amounts)
        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)

        # Complete and release all milestones
        total_released = 0
        for ms_id in ms_ids:
            marketplace_contract.functions.markMilestoneComplete(job_id, ms_id).transact({"from": freelancer})
            tx = marketplace_contract.functions.releaseMilestonePayment(job_id, ms_id).transact({"from": employer})
            receipt = w3.eth.wait_for_transaction_receipt(tx)
            events = marketplace_contract.events.PaymentReleased().process_receipt(receipt)
            total_released += events[0]["args"]["amount"]

        assert total_released == total_deposit

    def test_contract_balance_zero_after_full_payout(self, w3, marketplace_contract, accounts):
        """Contract balance should decrease by totalBudget after all milestones paid."""
        employer = accounts[1]
        freelancer = accounts[2]
        amounts = [Web3.to_wei(1, "ether"), Web3.to_wei(1, "ether")]
        total = sum(amounts)

        balance_before = w3.eth.get_balance(marketplace_contract.address)
        job_id, ms_ids = post_test_job(w3, marketplace_contract, employer, amounts)
        balance_after_post = w3.eth.get_balance(marketplace_contract.address)
        assert balance_after_post == balance_before + total

        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)

        for ms_id in ms_ids:
            marketplace_contract.functions.markMilestoneComplete(job_id, ms_id).transact({"from": freelancer})
            marketplace_contract.functions.releaseMilestonePayment(job_id, ms_id).transact({"from": employer})

        balance_after_release = w3.eth.get_balance(marketplace_contract.address)
        assert balance_after_release == balance_before  # Back to original

    def test_partial_release_leaves_correct_remainder(self, w3, marketplace_contract, accounts):
        """Releasing 1 of 3 milestones should leave the other 2 amounts in the contract."""
        employer = accounts[1]
        freelancer = accounts[2]
        amounts = [Web3.to_wei(1, "ether"), Web3.to_wei(2, "ether"), Web3.to_wei(3, "ether")]

        balance_before = w3.eth.get_balance(marketplace_contract.address)
        job_id, ms_ids = post_test_job(w3, marketplace_contract, employer, amounts)
        submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id)

        # Complete and release only the first milestone
        marketplace_contract.functions.markMilestoneComplete(job_id, ms_ids[0]).transact({"from": freelancer})
        marketplace_contract.functions.releaseMilestonePayment(job_id, ms_ids[0]).transact({"from": employer})

        balance_after = w3.eth.get_balance(marketplace_contract.address)
        expected_remaining = balance_before + amounts[1] + amounts[2]  # amounts[0] was released
        assert balance_after == expected_remaining
