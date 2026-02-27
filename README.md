# Freelance Marketplace DApp

A decentralized freelance marketplace on Ethereum where employers post jobs, freelancers bid, and milestone-based escrow releases payment as work is completed.

## Core Features

- Multi-milestone escrow per job
- Bid submission with expiry
- 2-of-3 multisig dispute resolution with 7-day timeout fallback
- On-chain freelancer ratings and profiles
- Category filter and search on the job board
- Non-custodial transaction signing with MetaMask

## Tech Stack

| Layer | Technology |
|---|---|
| Smart Contracts | Solidity 0.8.20, OpenZeppelin 5.x |
| Compiler / Migration | Truffle 5.x |
| Local Blockchain | Ganache 7.x (chainId 1337) |
| Backend | Python 3.10+, Flask 3.x, web3.py 6.x |
| Frontend | HTML, CSS, JavaScript, web3.js 1.x |
| Wallet | MetaMask |
| Testing | pytest, web3.py |

## Architecture

- All state-changing transactions are signed by user wallets in MetaMask.
- The backend (Flask) never stores private keys and never signs transactions.
- Smart contracts are the source of truth.
- Flask provides read/index/config APIs for the frontend.

## Prerequisites

Before starting, make sure you have the following installed:

- **Node.js** (v18 or later) — [nodejs.org](https://nodejs.org)
- **Python** (3.10 or later) — [python.org](https://python.org)
- **pip** (comes with Python)
- **MetaMask** browser extension — [metamask.io](https://metamask.io)
- **Git** — [git-scm.com](https://git-scm.com)

## Setup Instructions

### 1. Clone the Repository

```bash
git clone git@github.com:kevinlin29/Freelance-DApp.git
cd Freelance-DApp
```

### 2. Install Node.js Dependencies

This installs Truffle (Solidity compiler/deployer) and OpenZeppelin contracts.

```bash
npm install
```

### 3. Install Python Dependencies

```bash
pip install -r requirements.txt
```

This installs Flask, web3.py, and python-dotenv.

### 4. Start Ganache (Local Blockchain)

Open a **separate terminal** and run:

```bash
npx ganache --port 7545 --chain.chainId 1337
```

Keep this terminal open — it runs the local Ethereum blockchain. You will see 10 accounts printed, each funded with 1000 ETH. You will need the private keys later for MetaMask.

### 5. Compile Smart Contracts

```bash
npx truffle compile
```

Expected output: `Compiled successfully using solc 0.8.20`

### 6. Deploy Contracts to Ganache

```bash
npx truffle migrate --network development
```

This deploys:
- `Migrations` contract
- `FreelanceMarketplace` contract (main escrow contract)
- `MultiSigArbitration` contract (2-of-3 dispute resolution)

It also wires the arbitration contract into the marketplace automatically.

### 7. Configure MetaMask

1. Open MetaMask in your browser
2. **Add the Ganache network:**
   - Settings → Networks → Add a network → Add a network manually
   - **Network Name:** `Ganache`
   - **New RPC URL:** `http://127.0.0.1:7545`
   - **Chain ID:** `1337`
   - **Currency Symbol:** `ETH`
   - Click Save and switch to this network
3. **Import a Ganache account:**
   - Click the account icon → Import Account
   - Paste a private key from the Ganache terminal output
   - Recommended: import at least two accounts to test employer/freelancer flows

The Ganache accounts and their roles for testing:

| Account Index | Suggested Role | Notes |
|---|---|---|
| 0 | Contract Owner | Deployed the contracts |
| 1 | Employer | Posts jobs, accepts bids, releases payments |
| 2 | Freelancer | Submits bids, marks milestones complete |
| 3-6 | Additional users | For testing multiple bids, etc. |
| 7, 8, 9 | Arbitrators | Can vote on disputes |

### 8. Start the Flask Backend

```bash
cd app
python app.py
```

The server starts on **http://localhost:5001**.

### 9. Open the App

Navigate to **http://localhost:5001** in your browser (the same browser with MetaMask installed).

Click **Connect Wallet** in the top-right corner to connect MetaMask.

## Running the Test Suite

The test suite contains 19 tests across 4 categories. Ganache must be running.

```bash
# Make sure Ganache is running on port 7545, then:
python -m pytest test/ -v
```

### Test Categories

| File | Tests | Description |
|---|---|---|
| `test_escrow_invariants.py` | 4 | Deposit/withdrawal math, contract balance correctness |
| `test_authorization.py` | 5 | Unauthorized callers are rejected on every function |
| `test_dispute.py` | 5 | Funds lock on dispute, 2-of-3 voting, 7-day timeout 50/50 split |
| `test_events.py` | 5 | Correct event emission for indexer and UI sync |

### What the Tests Cover

**Escrow Invariants:**
- `postJob` reverts if `msg.value` does not match the sum of milestone amounts
- Sum of all `PaymentReleased` event amounts equals the original deposit
- Contract ETH balance returns to zero after all milestones are paid
- Partial release leaves the correct remaining balance

**Authorization:**
- Non-employer cannot release milestone payments
- Non-freelancer cannot mark milestones complete
- Non-arbitrator cannot call `resolveDispute` directly
- Employer cannot rate a freelancer twice on the same job
- `cancelJob` reverts after a bid has been accepted

**Disputes:**
- Payments are locked while a job is in Disputed status
- A single arbitrator vote does not resolve the dispute
- Two arbitrators voting for the same winner resolves the dispute and transfers funds
- After 7 days with no consensus, `claimTimeout` splits funds 50/50
- A replaced arbitrator can participate in voting

**Events:**
- `JobPosted` emits correct employer, category, and totalBudget
- `PaymentReleased` emits correct milestone ID, freelancer, and amount
- `BidWithdrawn` fires when an expired bid is withdrawn
- `DisputeResolved` emits correct winner and amount after 2-of-3 vote
- `JobStatusChanged` fires on every status transition (Open → InProgress → Completed)

## End-to-End Manual Testing Walkthrough

Once the app is running at http://localhost:5001 with MetaMask connected, follow this workflow to test every feature:

### Step 1: Create Profiles

1. Switch MetaMask to the **Employer** account (e.g., Account index 1)
2. Go to **Freelancer** dashboard → fill in Name and Bio → click **Create Profile**
3. Switch MetaMask to the **Freelancer** account (e.g., Account index 2)
4. Repeat: create a profile for the freelancer

### Step 2: Post a Job (Employer)

1. Switch MetaMask to the **Employer** account
2. Click **Post Job** in the nav bar
3. Fill in:
   - **Title:** "Build a Landing Page"
   - **Category:** Web Dev
   - **Deadline:** any future date
   - **Milestone 1:** "Design mockup" — 1 ETH
   - **Milestone 2:** "Implement frontend" — 2 ETH
   - Click **Add Milestone** to add more rows if needed
4. Click **Post Job** — MetaMask will prompt to send 3 ETH (sum of milestones)
5. Confirm the transaction in MetaMask
6. The job should appear on the **Jobs** board (homepage)

### Step 3: Submit a Bid (Freelancer)

1. Switch MetaMask to the **Freelancer** account
2. Go to the homepage, click the job you just posted
3. In the **Submit Bid** section:
   - **Amount:** 3 (ETH)
   - **Proposal:** "I can build this in a week"
   - **Duration:** 7 (days before bid expires)
4. Click **Submit Bid** — confirm in MetaMask
5. The bid should appear in the Bids section

### Step 4: Accept the Bid (Employer)

1. Switch MetaMask back to the **Employer** account
2. On the job detail page, find the freelancer's bid
3. Click **Accept** — confirm in MetaMask
4. Job status changes from Open → InProgress

### Step 5: Complete Milestones (Freelancer)

1. Switch to the **Freelancer** account
2. On the job detail page, click **Mark Complete** on the first milestone
3. Confirm in MetaMask
4. The milestone shows as "Completed" (but not yet paid)

### Step 6: Release Payment (Employer)

1. Switch to the **Employer** account
2. On the job detail page, click **Release Payment** for the completed milestone
3. Confirm in MetaMask — 1 ETH is sent to the freelancer
4. Repeat for remaining milestones, or click **Release All Payments**
5. After all milestones are paid, job status becomes Completed

### Step 7: Rate the Freelancer (Employer)

1. Still on the job detail page (status: Completed)
2. Select a star rating (1-5) and click **Rate**
3. Confirm in MetaMask
4. The rating updates the freelancer's on-chain profile

### Step 8: Test Dispute Resolution

1. Post a new job and accept a bid (repeat Steps 2-4)
2. Either the employer or freelancer clicks **Raise Dispute**
3. Job status becomes Disputed — payments are locked
4. Switch MetaMask to an **Arbitrator** account (Account index 7, 8, or 9)
5. Go to the **Arbitrator** page
6. Select who should win the dispute and click **Submit Vote**
7. Switch to a second arbitrator account and vote the same way
8. After 2-of-3 votes agree, the dispute resolves and funds go to the winner

### Step 9: Test Timeout Split (Optional)

This requires advancing Ganache's clock. In a terminal:

```bash
# Advance Ganache time by 7 days (604800 seconds)
curl -X POST http://127.0.0.1:7545 \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"evm_increaseTime","params":[604801],"id":1}'

curl -X POST http://127.0.0.1:7545 \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"evm_mine","params":[],"id":2}'
```

Then on the Arbitrator page, click **Claim Timeout** to trigger a 50/50 split.

## Project Structure

```
Freelance-DApp/
├── contracts/
│   ├── FreelanceMarketplace.sol    # Main escrow contract
│   ├── MultiSigArbitration.sol     # 2-of-3 dispute resolution
│   └── Migrations.sol              # Truffle migrations
├── migrations/
│   ├── 1_initial_migration.js
│   └── 2_deploy_marketplace.js     # Deploys and wires both contracts
├── test/
│   ├── conftest.py                 # Shared test fixtures
│   ├── test_escrow_invariants.py   # Escrow math tests
│   ├── test_authorization.py       # Auth negative tests
│   ├── test_dispute.py             # Dispute edge cases
│   └── test_events.py              # Event correctness tests
├── app/
│   ├── app.py                      # Flask backend
│   ├── static/
│   │   ├── css/style.css
│   │   └── js/
│   │       ├── web3_connect.js     # MetaMask connection + helpers
│   │       ├── employer.js         # Employer transaction methods
│   │       └── freelancer.js       # Freelancer transaction methods
│   └── templates/
│       ├── index.html              # Job board
│       ├── post_job.html           # Post job form
│       ├── job_detail.html         # Job detail + actions
│       ├── dashboard_employer.html # Employer dashboard
│       ├── dashboard_freelancer.html # Freelancer dashboard
│       └── arbitrator.html         # Arbitrator vote panel
├── package.json
├── truffle-config.js
├── requirements.txt
├── design.md                       # Full system design document
└── README.md
```

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/config` | GET | Chain ID, contract address, ABI |
| `/api/jobs` | GET | All jobs |
| `/api/jobs/category/<cat>` | GET | Jobs filtered by category |
| `/api/job/<id>` | GET | Job detail with bids and milestones |
| `/api/profile/<address>` | GET | User profile |
| `/api/disputes` | GET | Jobs with Disputed status |
| `/api/auth/challenge` | POST | Generate auth nonce |
| `/api/auth/verify` | POST | Verify wallet signature |
| `/api/tx/validate` | POST | Preflight transaction validation |

## Security Model

- **Checks-Effects-Interactions (CEI):** All state changes occur before external transfers
- **ReentrancyGuard:** Applied to all payment-releasing functions
- **Pausable:** Owner can freeze the contract in an emergency
- **Escrow invariants:** Enforced in code and verified by 19 automated tests
- **Non-custodial:** Flask never holds private keys; all writes go through MetaMask

For the complete system design, see [design.md](./design.md).
