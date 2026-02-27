"""
Freelance Marketplace DApp - Flask Backend (Read-Only)

This backend NEVER signs transactions or holds private keys.
All blockchain writes happen via MetaMask on the frontend.
The server only reads chain state and serves the UI.
"""

import json
import os
import hashlib
import secrets
import threading
import time
from flask import Flask, jsonify, render_template, request, session

from web3 import Web3

# ---------------------------------------------------------------------------
# App & Configuration
# ---------------------------------------------------------------------------

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-in-production")

# --- Web3 Setup ---
GANACHE_URL = os.environ.get("GANACHE_URL", "http://127.0.0.1:7545")
w3 = Web3(Web3.HTTPProvider(GANACHE_URL))

# Base directory (project root, one level up from /app)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# Contract Loading Helpers
# ---------------------------------------------------------------------------

def load_contract(artifact_name):
    """Load a Truffle artifact and return (abi, address, deployment_block)."""
    artifact_path = os.path.join(BASE_DIR, "build", "contracts", f"{artifact_name}.json")
    with open(artifact_path) as f:
        artifact = json.load(f)

    abi = artifact["abi"]

    # Get deployed address from networks (Ganache default chainId 1337)
    networks = artifact.get("networks", {})
    network_id = "1337"
    if network_id not in networks:
        # Fall back to whichever network entry exists
        network_id = list(networks.keys())[0] if networks else None

    address = None
    deployment_block = 0

    if network_id and network_id in networks:
        address = Web3.to_checksum_address(networks[network_id]["address"])
        # Determine the block in which the contract was deployed
        tx_hash = networks[network_id].get("transactionHash")
        if tx_hash:
            try:
                receipt = w3.eth.get_transaction_receipt(tx_hash)
                deployment_block = receipt["blockNumber"]
            except Exception:
                pass

    return abi, address, deployment_block


# These globals are initialised after Truffle has compiled & deployed.
marketplace_abi = None
marketplace_address = None
marketplace_deployment_block = 0
marketplace_contract = None

arbitration_abi = None
arbitration_address = None
arbitration_contract = None


def init_contracts():
    """Initialize contract connections. Call after truffle migrate."""
    global marketplace_abi, marketplace_address, marketplace_deployment_block, marketplace_contract
    global arbitration_abi, arbitration_address, arbitration_contract

    try:
        marketplace_abi, marketplace_address, marketplace_deployment_block = load_contract(
            "FreelanceMarketplace"
        )
        if marketplace_address:
            marketplace_contract = w3.eth.contract(
                address=marketplace_address, abi=marketplace_abi
            )

        arbitration_abi, arbitration_address, _ = load_contract("MultiSigArbitration")
        if arbitration_address:
            arbitration_contract = w3.eth.contract(
                address=arbitration_address, abi=arbitration_abi
            )
    except FileNotFoundError:
        print(
            "Warning: Contract artifacts not found. "
            "Run 'truffle compile' and 'truffle migrate' first."
        )


# Try to initialise on import (works if artifacts already exist)
try:
    init_contracts()
except Exception:
    pass

# ---------------------------------------------------------------------------
# Config API
# ---------------------------------------------------------------------------

@app.route("/api/config")
def api_config():
    """Return chain config, contract addresses, and ABIs for the frontend."""
    if not marketplace_abi or not marketplace_address:
        return jsonify({"error": "Contracts not deployed. Run truffle migrate."}), 503

    abi_hash = hashlib.md5(json.dumps(marketplace_abi).encode()).hexdigest()[:8]

    return jsonify({
        "chainIdHex": "0x539",              # 1337 in hex
        "contractAddress": marketplace_address,
        "abi": marketplace_abi,
        "arbitrationAddress": arbitration_address,
        "arbitrationAbi": arbitration_abi,
        "deploymentBlock": marketplace_deployment_block,
        "abiVersion": abi_hash,
    })

# ---------------------------------------------------------------------------
# Page-Rendering Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/post-job")
def post_job():
    return render_template("post_job.html")


@app.route("/job/<int:job_id>")
def job_detail(job_id):
    return render_template("job_detail.html", job_id=job_id)


@app.route("/dashboard/employer")
def dashboard_employer():
    return render_template("dashboard_employer.html")


@app.route("/dashboard/freelancer")
def dashboard_freelancer():
    return render_template("dashboard_freelancer.html")


@app.route("/arbitrator")
def arbitrator():
    return render_template("arbitrator.html")

# ---------------------------------------------------------------------------
# Read-Only API Routes
# ---------------------------------------------------------------------------

@app.route("/api/jobs")
def api_jobs():
    """Return all jobs."""
    if not marketplace_contract:
        return jsonify([])
    try:
        job_count = marketplace_contract.functions.jobCount().call()
        jobs_list = []
        for i in range(1, job_count + 1):
            job = marketplace_contract.functions.getJob(i).call()
            # getJob returns a tuple matching the Job struct
            jobs_list.append({
                "jobId": job[0],
                "employer": job[1],
                "title": job[2],
                "category": job[3],
                "totalBudget": str(job[4]),   # wei as string
                "deadline": job[5],
                "status": job[6],
                "acceptedFreelancer": job[7],
                "milestoneIds": list(job[8]),
            })
        return jsonify(jobs_list)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/jobs/category/<category>")
def api_jobs_by_category(category):
    """Return jobs filtered by category."""
    if not marketplace_contract:
        return jsonify([])
    try:
        job_count = marketplace_contract.functions.jobCount().call()
        jobs_list = []
        for i in range(1, job_count + 1):
            job = marketplace_contract.functions.getJob(i).call()
            if job[3].lower() == category.lower():
                jobs_list.append({
                    "jobId": job[0],
                    "employer": job[1],
                    "title": job[2],
                    "category": job[3],
                    "totalBudget": str(job[4]),
                    "deadline": job[5],
                    "status": job[6],
                    "acceptedFreelancer": job[7],
                    "milestoneIds": list(job[8]),
                })
        return jsonify(jobs_list)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/job/<int:job_id>")
def api_job_detail(job_id):
    """Return job details together with its bids and milestones."""
    if not marketplace_contract:
        return jsonify({"error": "Contract not connected"}), 503
    try:
        job = marketplace_contract.functions.getJob(job_id).call()

        # --- Bids ---
        bid_ids = marketplace_contract.functions.getJobBids(job_id).call()
        bids_list = []
        for bid_id in bid_ids:
            bid = marketplace_contract.functions.bids(bid_id).call()
            bids_list.append({
                "bidId": bid[0],
                "jobId": bid[1],
                "freelancer": bid[2],
                "amount": str(bid[3]),
                "proposal": bid[4],
                "expiresAt": bid[5],
                "status": bid[6],
            })

        # --- Milestones ---
        milestone_ids = list(job[8])
        milestones_list = []
        for ms_id in milestone_ids:
            ms = marketplace_contract.functions.milestones(ms_id).call()
            milestones_list.append({
                "milestoneId": ms_id,
                "jobId": ms[0],
                "description": ms[1],
                "amount": str(ms[2]),
                "completed": ms[3],
                "paid": ms[4],
            })

        return jsonify({
            "job": {
                "jobId": job[0],
                "employer": job[1],
                "title": job[2],
                "category": job[3],
                "totalBudget": str(job[4]),
                "deadline": job[5],
                "status": job[6],
                "acceptedFreelancer": job[7],
                "milestoneIds": milestone_ids,
            },
            "bids": bids_list,
            "milestones": milestones_list,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/profile/<address>")
def api_profile(address):
    """Return a user profile by wallet address."""
    if not marketplace_contract:
        return jsonify({"error": "Contract not connected"}), 503
    try:
        addr = Web3.to_checksum_address(address)
        profile = marketplace_contract.functions.getProfile(addr).call()
        return jsonify({
            "wallet": profile[0],
            "name": profile[1],
            "bio": profile[2],
            "totalJobsCompleted": profile[3],
            "reputationScore": profile[4],
            "ratingCount": profile[5],
            "exists": profile[6],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/disputes")
def api_disputes():
    """Return jobs whose status is Disputed (enum value 3)."""
    if not marketplace_contract:
        return jsonify([])
    try:
        job_count = marketplace_contract.functions.jobCount().call()
        disputes = []
        for i in range(1, job_count + 1):
            job = marketplace_contract.functions.getJob(i).call()
            if job[6] == 3:  # JobStatus.Disputed == 3
                disputes.append({
                    "jobId": job[0],
                    "employer": job[1],
                    "title": job[2],
                    "totalBudget": str(job[4]),
                    "acceptedFreelancer": job[7],
                })
        return jsonify(disputes)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------------------------------------------------------------------
# Authentication (simple nonce-based, no SIWE dependency)
# ---------------------------------------------------------------------------

@app.route("/api/auth/challenge", methods=["POST"])
def auth_challenge():
    """Generate a nonce for wallet signature verification."""
    nonce = secrets.token_hex(16)
    session["auth_nonce"] = nonce
    return jsonify({"nonce": nonce})


@app.route("/api/auth/verify", methods=["POST"])
def auth_verify():
    """Verify a signed message from the user's wallet."""
    data = request.get_json()
    if not data or "address" not in data or "signature" not in data:
        return jsonify({"error": "Missing address or signature"}), 400

    nonce = session.get("auth_nonce")
    if not nonce:
        return jsonify({"error": "No challenge issued"}), 400

    message = (
        "Sign this message to authenticate with Freelance Marketplace.\n\n"
        f"Nonce: {nonce}"
    )

    try:
        from eth_account.messages import encode_defunct

        msg = encode_defunct(text=message)
        recovered = w3.eth.account.recover_message(msg, signature=data["signature"])

        if recovered.lower() == data["address"].lower():
            session["authenticated_address"] = Web3.to_checksum_address(data["address"])
            session.pop("auth_nonce", None)
            return jsonify({
                "authenticated": True,
                "address": session["authenticated_address"],
            })
        else:
            return jsonify({"error": "Signature verification failed"}), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# ---------------------------------------------------------------------------
# Preflight Transaction Validation
# ---------------------------------------------------------------------------

@app.route("/api/tx/validate", methods=["POST"])
def tx_validate():
    """
    Server-side preflight validation before MetaMask prompt.

    The frontend sends { method, params, from, value } and this endpoint
    attempts to estimate gas.  If the call reverts, the frontend can show
    an error *before* the user sees a MetaMask popup.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    method = data.get("method")
    params = data.get("params", {})
    sender = data.get("from")
    value = data.get("value", 0)

    if not marketplace_contract or not method or not sender:
        return jsonify({"error": "Missing required fields"}), 400

    try:
        func = getattr(marketplace_contract.functions, method)

        # Build the contract function call with the supplied parameters
        if isinstance(params, dict):
            tx_func = func(**params)
        elif isinstance(params, list):
            tx_func = func(*params)
        else:
            tx_func = func(params)

        # estimate_gas will revert if the transaction would fail on-chain
        gas = tx_func.estimate_gas({
            "from": Web3.to_checksum_address(sender),
            "value": int(value),
        })
        return jsonify({"valid": True, "estimatedGas": gas})
    except Exception as e:
        return jsonify({"valid": False, "error": str(e)}), 400

# ---------------------------------------------------------------------------
# Background Event Indexer
# ---------------------------------------------------------------------------

# Simple in-memory event index for the MVP
event_index = {
    "jobs": {},
    "last_processed_block": 0,
}


def run_event_indexer():
    """Background thread that periodically indexes contract events."""
    global event_index

    while True:
        try:
            if not marketplace_contract:
                time.sleep(5)
                continue

            latest_block = w3.eth.block_number
            from_block = event_index["last_processed_block"] + 1

            if from_block > latest_block:
                time.sleep(2)
                continue

            # Index JobPosted events
            events = marketplace_contract.events.JobPosted().get_logs(
                fromBlock=from_block,
                toBlock=latest_block,
            )
            for evt in events:
                job_id = evt["args"]["jobId"]
                event_index["jobs"][job_id] = {
                    "employer": evt["args"]["employer"],
                    "category": evt["args"]["category"],
                    "totalBudget": str(evt["args"]["totalBudget"]),
                    "blockNumber": evt["blockNumber"],
                }

            event_index["last_processed_block"] = latest_block
        except Exception as e:
            print(f"Indexer error: {e}")

        time.sleep(2)  # Poll every 2 seconds

# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Re-initialise contracts in case they weren't ready at import time
    init_contracts()

    # Start event indexer in a daemon background thread
    indexer_thread = threading.Thread(target=run_event_indexer, daemon=True)
    indexer_thread.start()

    app.run(debug=True, host="0.0.0.0", port=5001)
