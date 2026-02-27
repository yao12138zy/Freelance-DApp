import pytest
import json
import os
from web3 import Web3

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="session")
def w3():
    """Connect to Ganache."""
    w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:7545"))
    assert w3.is_connected(), "Cannot connect to Ganache on port 7545"
    return w3


@pytest.fixture(scope="session")
def accounts(w3):
    """Return list of Ganache accounts."""
    return w3.eth.accounts


@pytest.fixture(scope="session")
def marketplace_contract(w3, accounts):
    """Deploy a fresh FreelanceMarketplace contract."""
    artifact_path = os.path.join(BASE_DIR, "build", "contracts", "FreelanceMarketplace.json")
    with open(artifact_path) as f:
        artifact = json.load(f)

    Contract = w3.eth.contract(abi=artifact["abi"], bytecode=artifact["bytecode"])
    tx_hash = Contract.constructor(0).transact({"from": accounts[0]})  # 0 platform fee
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    return w3.eth.contract(address=receipt.contractAddress, abi=artifact["abi"])


@pytest.fixture(scope="session")
def arbitration_contract(w3, accounts, marketplace_contract):
    """Deploy MultiSigArbitration and wire to marketplace."""
    artifact_path = os.path.join(BASE_DIR, "build", "contracts", "MultiSigArbitration.json")
    with open(artifact_path) as f:
        artifact = json.load(f)

    arbitrators = [accounts[7], accounts[8], accounts[9]]
    Contract = w3.eth.contract(abi=artifact["abi"], bytecode=artifact["bytecode"])
    tx_hash = Contract.constructor(
        marketplace_contract.address, arbitrators
    ).transact({"from": accounts[0]})
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    arb = w3.eth.contract(address=receipt.contractAddress, abi=artifact["abi"])

    # Wire arbitration into marketplace
    marketplace_contract.functions.setArbitrationContract(
        arb.address
    ).transact({"from": accounts[0]})

    return arb


def post_test_job(w3, marketplace_contract, employer, milestone_amounts, title="Test Job", category="Web Dev", deadline=None):
    """Helper to post a job with given milestones. Returns (jobId, milestoneIds)."""
    if deadline is None:
        deadline = w3.eth.get_block("latest")["timestamp"] + 86400 * 30  # 30 days from now

    descriptions = [f"Milestone {i+1}" for i in range(len(milestone_amounts))]
    total_value = sum(milestone_amounts)

    tx_hash = marketplace_contract.functions.postJob(
        title, category, deadline, descriptions, milestone_amounts
    ).transact({"from": employer, "value": total_value})
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    # Get jobId from event
    events = marketplace_contract.events.JobPosted().process_receipt(receipt)
    job_id = events[0]["args"]["jobId"]

    # Get milestone IDs
    job = marketplace_contract.functions.getJob(job_id).call()
    milestone_ids = job[8]  # milestoneIds is at index 8

    return job_id, milestone_ids


def submit_and_accept_bid(w3, marketplace_contract, employer, freelancer, job_id, bid_amount=None):
    """Helper to submit a bid and accept it. Returns bidId."""
    if bid_amount is None:
        job = marketplace_contract.functions.getJob(job_id).call()
        bid_amount = job[4]  # totalBudget

    # Submit bid
    tx = marketplace_contract.functions.submitBid(
        job_id, bid_amount, "I can do this!", 86400  # 1 day expiry
    ).transact({"from": freelancer})
    receipt = w3.eth.wait_for_transaction_receipt(tx)
    events = marketplace_contract.events.BidSubmitted().process_receipt(receipt)
    bid_id = events[0]["args"]["bidId"]

    # Accept bid
    marketplace_contract.functions.acceptBid(
        job_id, bid_id
    ).transact({"from": employer})

    return bid_id
