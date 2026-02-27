# Freelance Marketplace DApp — Design Document

## Overview

A decentralized freelance marketplace built on Ethereum where employers post jobs, freelancers bid, and payments are released via milestone-based escrow. Built with Solidity, Python (Flask + web3.py), and Ganache for local blockchain development.

---

## Team

- 2 members
- Option A: Non-tutorial programming project (40% of grade)
- Due: April 10, 2026

---

## Tech Stack

| Layer | Technology |
|---|---|
| Smart Contract | Solidity 0.8.x |
| Compiler / Migration | Truffle |
| Local Blockchain | Ganache |
| Backend | Python 3.10+, Flask, web3.py |
| Frontend | HTML, CSS, JavaScript (no framework) |
| Wallet | MetaMask (non-custodial, all writes signed in browser) |

---

## Architecture: Trust Model

This DApp uses a **non-custodial frontend-signing model**. Flask never holds private keys or sends transactions. The contract is the single source of truth; Flask is a read/index/config layer only.

| Who | Signs What |
|---|---|
| Employer wallet | `postJob`, `acceptBid`, `releaseMilestonePayment`, `cancelJob`, `rateFreelancer` |
| Freelancer wallet | `submitBid`, `markMilestoneComplete`, `withdrawExpiredBid` |
| Either party | `raiseDispute` |
| Arbitrator wallet(s) | `submitVote` (2-of-3 multisig required to resolve) |

**Transaction flow:**
1. Frontend fetches `chainIdHex`, `contractAddress`, and ABI from Flask config endpoint
2. User connects MetaMask; frontend validates chain matches expected network
3. Frontend validates inputs and calls `estimateGas` to simulate before sending
4. Frontend sends tx via `eth_sendTransaction` through web3.js / MetaMask
5. Frontend stores tx hash, shows pending UI
6. Flask indexer replays events from a persisted block cursor (`last_processed_block`) and updates read models
7. UI polls receipt or listens for confirmation

---

## Project Structure

```
freelance-marketplace/
├── contracts/
│   ├── FreelanceMarketplace.sol      # Main contract
│   ├── MultiSigArbitration.sol       # 2-of-3 arbitrator contract
│   └── Migrations.sol
├── migrations/
│   ├── 1_initial_migration.js
│   └── 2_deploy_marketplace.js
├── test/
│   ├── test_escrow_invariants.py     # Escrow math invariant tests
│   ├── test_authorization.py         # Auth negative tests
│   ├── test_dispute.py               # Dispute edge cases
│   └── test_events.py                # Event correctness checks
├── app/
│   ├── static/
│   │   ├── css/style.css
│   │   └── js/
│   │       ├── web3_connect.js       # MetaMask + chain validation
│   │       ├── employer.js           # Employer write calls
│   │       └── freelancer.js         # Freelancer write calls
│   ├── templates/
│   │   ├── index.html                # Job board
│   │   ├── post_job.html
│   │   ├── job_detail.html
│   │   ├── dashboard_employer.html
│   │   ├── dashboard_freelancer.html
│   │   └── arbitrator.html           # Arbitrator vote dashboard
│   └── app.py
├── truffle-config.js
├── requirements.txt
└── design.md
```

---

## Smart Contract Design

### `FreelanceMarketplace.sol`

#### Security Requirements

The following patterns are **mandatory** in the implementation:

- **Checks-Effects-Interactions (CEI):** All state changes must occur before any external `.transfer()` or `.call()` to prevent reentrancy.
- **Reentrancy guard:** Use OpenZeppelin `ReentrancyGuard` on all payment-releasing functions (`releaseMilestonePayment`, `releaseAllPayments`, `resolveDispute`).
- **Emergency pause:** Implement OpenZeppelin `Pausable`. Owner can pause the contract to freeze fund movement in case of a critical bug.
- **External call failure handling:** Payment transfers use the low-level `.call{value: ...}("")` pattern with explicit revert on failure rather than `.transfer()` (which has a fixed gas stipend that can fail).

#### Data Structures

```solidity
enum JobStatus    { Open, InProgress, Completed, Disputed, Cancelled }
enum BidStatus    { Pending, Accepted, Rejected, Expired }

struct Milestone {
    uint256 jobId;           // INVARIANT: must match parent job
    string  description;     // store short string or URI for long content (gas)
    uint256 amount;          // in wei
    bool    completed;       // set by acceptedFreelancer only
    bool    paid;            // set by employer only, after completed == true
}

struct Job {
    uint256   jobId;
    address   employer;
    string    title;         // keep short; use URI for full description (gas)
    string    category;
    uint256   totalBudget;   // INVARIANT: must equal sum(milestone.amount for all milestones)
    uint256   deadline;      // Unix timestamp
    JobStatus status;
    address   acceptedFreelancer;
    uint256[] milestoneIds;
}

struct Bid {
    uint256   bidId;
    uint256   jobId;
    address   freelancer;
    uint256   amount;        // proposed total, in wei — employer verifies vs totalBudget
    string    proposal;      // keep short or URI (gas)
    uint256   expiresAt;     // block.timestamp + bidDuration
    BidStatus status;
}

struct Profile {
    address wallet;
    string  name;
    string  bio;             // consider URI for long bios (gas)
    uint256 totalJobsCompleted;
    uint256 reputationScore; // cumulative sum; divide by ratingCount for average
    uint256 ratingCount;     // number of ratings received
    bool    exists;
}
```

#### Escrow Invariants

These invariants **must be enforced in code** and verified in tests:

1. **`postJob` deposit check:** `require(msg.value == sum(milestoneAmounts), "deposit must equal sum of milestones")`
2. **Milestone ownership check:** Before any milestone operation, verify `milestones[milestoneId].jobId == jobId`
3. **No double-payment:** `require(!milestones[milestoneId].paid, "already paid")`
4. **No release before completion:** `require(milestones[milestoneId].completed, "not marked complete")`
5. **Disputed jobs locked:** No payment release while `job.status == Disputed`
6. **Accepted bid amount never changes escrow math:** `job.totalBudget` is set from `msg.value` at `postJob`. Accepting a bid does not modify escrow balances.
7. **Budget compatibility check on acceptance:** enforce `require(bid.amount <= job.totalBudget, "bid exceeds escrowed budget")` in `acceptBid` so accepted terms never exceed locked funds.

#### State Variables

```solidity
uint256 public jobCount;
uint256 public bidCount;
uint256 public milestoneCount;

mapping(uint256 => Job)       public jobs;
mapping(uint256 => Bid)       public bids;
mapping(uint256 => Milestone) public milestones;
mapping(address => Profile)   public profiles;
mapping(uint256 => uint256[]) public jobBids;        // jobId => bidId[]
mapping(address => uint256[]) public employerJobs;   // address => jobId[]
mapping(address => uint256[]) public freelancerBids; // address => bidId[]
mapping(uint256 => bool)      public jobRated;       // jobId => rated (one-time gate)

address public owner;
address public arbitrationContract;  // MultiSigArbitration.sol address
uint256 public platformFeeBps;       // e.g. 250 = 2.5%
```

#### Authorization Rules

Every state-changing function enforces strict caller constraints:

| Function | Allowed Caller | Key Checks |
|---|---|---|
| `postJob` | Any address | `msg.value == sum(milestoneAmounts)` |
| `cancelJob` | `job.employer` only | `status == Open` (no accepted bid yet) |
| `submitBid` | Any address except employer | `status == Open`, bid not already submitted by same address |
| `acceptBid` | `job.employer` only | `status == Open`, `bid.jobId == jobId`, `bid.status == Pending`, `block.timestamp < bid.expiresAt`, `bid.amount <= job.totalBudget` |
| `rejectBid` | `job.employer` only | `bid.jobId` must belong to employer's job |
| `withdrawExpiredBid` | `bid.freelancer` only | `block.timestamp >= bid.expiresAt`, `bid.status == Pending` |
| `markMilestoneComplete` | `job.acceptedFreelancer` only | `milestones[id].jobId == jobId`, `!completed`, `status == InProgress` |
| `releaseMilestonePayment` | `job.employer` only | `milestones[id].jobId == jobId`, `completed == true`, `paid == false`, `status != Disputed` |
| `releaseAllPayments` | `job.employer` only | All milestones completed, `status != Disputed` |
| `raiseDispute` | `job.employer` OR `job.acceptedFreelancer` | `status == InProgress` |
| `resolveDispute` | `arbitrationContract` address only | Called by `MultiSigArbitration` after 2-of-3 vote |
| `rateFreelancer` | `job.employer` only | `status == Completed`, `!jobRated[jobId]` (one-time gate), score 1–5 |

#### Core Functions

```solidity
// --- Profiles ---
function createProfile(string memory name, string memory bio) external;
function getProfile(address wallet) external view returns (Profile memory);

// --- Jobs ---
function postJob(
    string memory title,
    string memory category,
    uint256 deadline,
    string[] memory milestoneDescriptions,
    uint256[] memory milestoneAmounts   // INVARIANT: msg.value must equal sum of these
) external payable;

function cancelJob(uint256 jobId) external;  // employer only, status == Open
function getJob(uint256 jobId) external view returns (Job memory);

// --- Bidding ---
function submitBid(
    uint256 jobId,
    uint256 amount,
    string memory proposal,
    uint256 bidDuration
) external;

function acceptBid(uint256 jobId, uint256 bidId) external;   // employer only
function rejectBid(uint256 bidId) external;                  // employer only
function withdrawExpiredBid(uint256 bidId) external;         // freelancer only, after expiry

// --- Milestones & Payments ---
function markMilestoneComplete(uint256 jobId, uint256 milestoneId) external;   // freelancer only
function releaseMilestonePayment(uint256 jobId, uint256 milestoneId) external; // employer only
function releaseAllPayments(uint256 jobId) external;                           // employer only

// --- Disputes ---
function raiseDispute(uint256 jobId) external;  // employer or freelancer
// resolveDispute called exclusively by MultiSigArbitration.sol, not directly by users

// --- Ratings ---
function rateFreelancer(uint256 jobId, uint256 score) external; // employer only, one-time per job

// --- Emergency ---
function pause() external;    // owner only
function unpause() external;  // owner only
```

#### Events (Complete)

```solidity
// Jobs
event JobPosted(uint256 indexed jobId, address indexed employer, string category, uint256 totalBudget);
event JobCancelled(uint256 indexed jobId, address indexed employer);
event JobStatusChanged(uint256 indexed jobId, JobStatus oldStatus, JobStatus newStatus);

// Bids
event BidSubmitted(uint256 indexed bidId, uint256 indexed jobId, address indexed freelancer, uint256 amount);
event BidAccepted(uint256 indexed bidId, uint256 indexed jobId, address indexed freelancer);
event BidRejected(uint256 indexed bidId, uint256 indexed jobId);
event BidWithdrawn(uint256 indexed bidId, address indexed freelancer);

// Milestones & Payments
event MilestoneCompleted(uint256 indexed jobId, uint256 indexed milestoneId, address freelancer);
event PaymentReleased(uint256 indexed jobId, uint256 indexed milestoneId, address indexed freelancer, uint256 amount);

// Disputes
event DisputeRaised(uint256 indexed jobId, address indexed raisedBy);
event ArbitratorVoted(uint256 indexed jobId, address indexed arbitrator, address votedFor);
event DisputeResolved(uint256 indexed jobId, address indexed winner, uint256 amount);

// Profiles & Ratings
event ProfileCreated(address indexed wallet);
event ProfileUpdated(address indexed wallet);
event FreelancerRated(uint256 indexed jobId, address indexed freelancer, uint256 score, address ratedBy);

// Emergency
event ContractPaused(address by);
event ContractUnpaused(address by);
```

---

### `MultiSigArbitration.sol`

Handles 2-of-3 arbitrator dispute resolution. Decoupled from the main contract so arbitrators can be rotated without redeploying the marketplace.

```solidity
struct DisputeVote {
    uint256 jobId;
    mapping(address => address) votes; // arbitrator => voted winner
    uint8   voteCount;
    bool    resolved;
    uint256 raisedAt; // timestamp, for timeout enforcement
}

address[3] public arbitrators;  // set at deploy, replaceable by owner
mapping(uint256 => DisputeVote) public disputes;

// Arbitrator submits their vote for who should receive the escrowed funds
function submitVote(uint256 jobId, address payable votedWinner) external; // arbitrator only

// Called internally once 2 arbitrators agree on the same winner
function _executeResolution(uint256 jobId, address payable winner) internal;

// If no 2-of-3 consensus within 7 days, either party can trigger deterministic 50/50 fallback:
// fee = floor(remainingEscrow * platformFeeBps / 10000)
// distributable = remainingEscrow - fee
// employerShare = floor(distributable / 2)
// freelancerShare = distributable - employerShare   // odd-wei remainder goes to freelancer
function claimTimeout(uint256 jobId) external; // employer or freelancer, after 7 days

// Owner can replace an inactive or compromised arbitrator
function replaceArbitrator(uint256 index, address newArbitrator) external; // owner only

event VoteSubmitted(uint256 indexed jobId, address indexed arbitrator, address votedFor);
event DisputeResolutionExecuted(uint256 indexed jobId, address winner);
event TimeoutSplitExecuted(uint256 indexed jobId, uint256 amountEach);
```

---

## Flask Backend Design

Flask is a **read-only / config / indexing** layer. It never signs transactions or holds private keys.

### `app.py` — Routes

```python
# --- Page rendering ---
GET  /                              # Job board
GET  /post-job                      # Post job form
GET  /job/<job_id>                  # Job detail
GET  /dashboard/employer            # Employer dashboard
GET  /dashboard/freelancer          # Freelancer dashboard
GET  /arbitrator                    # Arbitrator vote panel

# --- Config (served to frontend for chain + contract validation) ---
GET  /api/config                    # Returns { chainIdHex, contractAddress, abi, deploymentBlock, abiVersion }

# --- Read-only contract queries (via web3.py .call()) ---
GET  /api/jobs                      # All open jobs (indexed from events)
GET  /api/jobs/category/<cat>       # Filter by category
GET  /api/job/<job_id>              # Single job + bids + milestones
GET  /api/profile/<address>         # Fetch profile
GET  /api/disputes                  # Open disputes (arbitrator view)

# --- SIWE-style wallet auth ---
POST /api/auth/challenge            # Returns nonce for wallet to sign
POST /api/auth/verify               # Verifies signed nonce, issues session

# --- Optional: server-side preflight (no signing, no tx) ---
POST /api/tx/validate               # Validates inputs before user hits MetaMask
```

> **Note:** All write routes (`POST /api/job/post`, `POST /api/bid/submit`, etc.) from the original design have been **removed**. All state-changing operations are performed exclusively via MetaMask on the frontend. Flask never builds or signs transactions.

### web3.py — Read Pattern

```python
from web3 import Web3
import json

w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:7545"))  # Ganache

with open("build/contracts/FreelanceMarketplace.json") as f:
    abi = json.load(f)["abi"]

contract = w3.eth.contract(
    address=Web3.to_checksum_address(CONTRACT_ADDRESS),
    abi=abi
)

# Read (free, no gas, no signing)
job     = contract.functions.getJob(job_id).call()
profile = contract.functions.getProfile(Web3.to_checksum_address(address)).call()

# Event indexing with durable cursor (background thread or APScheduler)
# Prevents missing historical events after backend restarts
last_processed_block = load_cursor_from_db()   # persisted integer; init with deploymentBlock - 1
latest_block = w3.eth.block_number
confirmations = 2                               # small finality buffer for local dev
safe_to_block = max(last_processed_block, latest_block - confirmations)

for evt in contract.events.JobPosted.get_logs(
    from_block=last_processed_block + 1,
    to_block=safe_to_block
):
    upsert_job_from_event(evt)  # idempotent upsert keyed by (txHash, logIndex)

save_cursor_to_db(safe_to_block)
```

---

## Frontend Design

### Pages

| Page | Description |
|---|---|
| `index.html` | Job board — open jobs with category filter, budget range slider, keyword search |
| `post_job.html` | Employer form — title, category, milestones + wei amounts, deadline |
| `job_detail.html` | Job info, bids list, milestone tracker, dispute/rating buttons |
| `dashboard_employer.html` | Posted jobs, active contracts, pending milestone releases |
| `dashboard_freelancer.html` | Submitted bids, active jobs, milestones to mark complete |
| `arbitrator.html` | Open disputes, vote submission panel, resolution history |

### MetaMask Integration (JavaScript)

```javascript
// web3_connect.js — chain validation before any write
// Use /api/config as single source of truth (no hardcoded chain id in frontend)

async function connectWallet() {
    if (typeof window.ethereum === "undefined") {
        alert("Please install MetaMask.");
        return;
    }
    const config   = await fetch("/api/config").then(r => r.json());
    const accounts = await window.ethereum.request({ method: "eth_requestAccounts" });
    const chainId  = await window.ethereum.request({ method: "eth_chainId" });

    if (chainId !== config.chainIdHex) {
        alert(`Wrong network. Please switch MetaMask to chainId ${config.chainIdHex}.`);
        return;
    }

    window.userAccount = accounts[0];
    window.web3        = new Web3(window.ethereum);

    // Fetch ABI and contract address from Flask config endpoint
    window.contract = new web3.eth.Contract(config.abi, config.contractAddress);
}
```

```javascript
// employer.js — safe wei math using BigInt (never JS float for ETH values)
async function postJob(title, category, deadline, milestoneDescs, milestoneAmountsWei) {
    // milestoneAmountsWei must be BigInt[] — convert ETH strings before calling this function
    const totalWei = milestoneAmountsWei.reduce((a, b) => a + b, 0n); // BigInt addition

    // Simulate first to catch revert before prompting user
    await window.contract.methods
        .postJob(title, category, deadline, milestoneDescs, milestoneAmountsWei.map(String))
        .estimateGas({ from: window.userAccount, value: totalWei.toString() });

    // Send — MetaMask prompts user to review and sign
    const tx = await window.contract.methods
        .postJob(title, category, deadline, milestoneDescs, milestoneAmountsWei.map(String))
        .send({ from: window.userAccount, value: totalWei.toString() });

    return tx.transactionHash;
}

// Helper: convert ETH input string to wei as BigInt (no float precision loss)
function ethToWeiBigInt(ethString) {
    return BigInt(web3.utils.toWei(ethString, "ether"));
}
```

> **Wei math rule:** All ETH/wei values in JavaScript **must** use `BigInt` or `web3.utils.toBN()`. Never use regular JS `number` or `float` for wei arithmetic — floating point precision loss will cause escrow sum mismatches and failed `require` checks in the contract.

---

## The 6 Major Modifications

| # | Feature | Solidity Changes | Frontend/Backend Changes |
|---|---|---|---|
| 1 | **Multi-milestone escrow** | `Milestone` struct with `jobId` ownership field, per-milestone release with CEI + reentrancy guard, `msg.value == sum(milestoneAmounts)` invariant in `postJob` | Milestone creation form, visual progress tracker, per-milestone release buttons |
| 2 | **Bid expiry system** | `expiresAt` on `Bid`, expiry check in `acceptBid`, `withdrawExpiredBid` for freelancer | Countdown timer on bids, expired badge, auto-disable accept button after expiry |
| 3 | **2-of-3 multisig dispute resolution** | Separate `MultiSigArbitration.sol`, `raiseDispute` locks job, `submitVote` tallies, 7-day timeout 50/50 fallback | Dispute button, arbitrator dashboard, vote UI, resolution status indicator |
| 4 | **Reputation & ratings** | `rateFreelancer` with one-time gate (`jobRated` mapping), cumulative `reputationScore` + `ratingCount` on `Profile` | Star rating widget post-completion, average score on profile cards and bid listings |
| 5 | **User profiles** | `Profile` struct, `createProfile`, `getProfile`, `ProfileCreated`/`ProfileUpdated` events | Profile creation/edit form, profile cards shown on bids and job detail pages |
| 6 | **Job category filter & search** | `category` field on `Job`, emitted in `JobPosted` for Flask event indexing | Filter bar, category badges, budget range slider — filtering done client-side from Flask read index |

---

## Security & Invariants Summary

| Invariant | Where Enforced |
|---|---|
| `msg.value == sum(milestoneAmounts)` | `postJob` require statement |
| `milestone.jobId == jobId` before any payment op | All milestone functions |
| No payment while `status == Disputed` | `releaseMilestonePayment`, `releaseAllPayments` |
| No double-payment (`!milestone.paid`) | `releaseMilestonePayment` |
| No release before completion (`milestone.completed`) | `releaseMilestonePayment` |
| Accepted bid must fit escrow (`bid.amount <= totalBudget`) | `acceptBid` |
| One rating per job (`!jobRated[jobId]`) | `rateFreelancer` |
| Only accepted freelancer marks complete | `markMilestoneComplete` modifier |
| Only employer releases payment | `releaseMilestonePayment` modifier |
| 2-of-3 arbitrators required for resolution | `MultiSigArbitration._executeResolution` |
| Timeout split is deterministic, including odd-wei remainder | `MultiSigArbitration.claimTimeout` |
| Reentrancy blocked on all payment functions | OpenZeppelin `ReentrancyGuard` |
| Contract pausable in emergency | OpenZeppelin `Pausable` on payment functions |
| All wei math uses BigInt/BN (frontend) | Enforced in JS helpers, never JS float |
| Checksummed addresses everywhere | `Web3.to_checksum_address()` in Flask |
| Indexing cursor is durable and idempotent | Flask indexer with persisted cursor + `(txHash, logIndex)` key |

---

## Testing Plan

Tests are organized into four categories covering the critical paths of a money-moving contract.

**Escrow invariant tests (`test_escrow_invariants.py`)**
- `postJob` with mismatched `msg.value` reverts
- Sum of milestone payments equals total deposited after all releases
- Contract ETH balance reaches zero after all milestones paid out on a completed job
- Partial release leaves correct remainder in contract

**Authorization negative tests (`test_authorization.py`)**
- Non-employer cannot call `releaseMilestonePayment` (expect revert)
- Non-freelancer cannot call `markMilestoneComplete` (expect revert)
- Non-arbitrator cannot call `resolveDispute` directly (expect revert)
- Employer cannot rate freelancer twice on same job (expect revert)
- `cancelJob` reverts if a bid has already been accepted

**Dispute edge cases (`test_dispute.py`)**
- Funds locked when dispute raised; no payment release possible
- 1-of-3 arbitrator vote does not resolve dispute
- 2-of-3 vote releases funds to winner correctly
- 7-day timeout fallback splits funds 50/50
- Arbitrator replacement still allows pending dispute to resolve

**Event correctness tests (`test_events.py`)**
- `JobPosted` emitted with correct `jobId`, `employer`, `category`, `totalBudget`
- `PaymentReleased` emitted with correct `amount` per milestone
- `BidWithdrawn` emitted when expired bid is withdrawn
- `DisputeResolved` emitted with correct `winner` and `amount`
- `JobStatusChanged` emitted on every status transition

---

## Development Milestones

| Phase | Tasks |
|---|---|
| **1 — Setup** | Install Truffle, Ganache, Python deps, scaffold project, connect MetaMask to local Ganache chain |
| **2 — Core Contract** | Write `FreelanceMarketplace.sol` with escrow invariants, auth modifiers, CEI pattern, reentrancy guard, pause |
| **3 — Arbitration Contract** | Write `MultiSigArbitration.sol`, connect to main contract, test 2-of-3 vote flow and timeout fallback |
| **4 — Flask + web3.py** | Config endpoint, read routes, SIWE auth, event indexing background thread |
| **5 — Frontend Core** | Job board, post job form, job detail with MetaMask integration and BigInt wei math |
| **6 — Modifications** | Implement each of the 6 features one by one, run full test suite after each |
| **7 — Polish** | UI cleanup, setup instructions with version numbers, demo video, executive summary |

---

## Version Targets

```
Python          3.10+
Flask           3.x
web3 (Python)   6.x
Solidity        0.8.20
Truffle         5.x
Ganache         7.x (chainId 1337)
web3.js         1.x (frontend)
OpenZeppelin    5.x (ReentrancyGuard, Pausable)
```

---

## Executive Summary Outline (1 page, single spaced)

1. What the DApp is — a trustless, non-custodial freelance marketplace on Ethereum
2. What it does — job posting, milestone-based escrow, bidding, 2-of-3 arbitrated dispute resolution, on-chain reputation
3. Why it is relevant — eliminates platform middlemen (Upwork/Fiverr fees), transparent and enforceable payment release, tamper-proof on-chain reputation
4. Seed DApp used and source attribution
5. List of 6 major modifications with brief justification for each

---

## Open Questions

- IPFS for profile images / job attachments? (nice to have, not required for passing)
- Platform fee on payment release? (strengthens executive summary argument, minor to implement)
- Default for MVP: set `platformFeeBps = 0`; add fee later only if demo scope allows.
- Frontend framework? (plain JS is fine; React only if team is comfortable with it)
