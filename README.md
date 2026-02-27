# Freelance Marketplace DApp

A decentralized freelance marketplace on Ethereum where employers post jobs, freelancers bid, and milestone-based escrow releases payment as work is completed.

## Status

Design phase. The canonical system design lives in [design.md](./design.md).

## Core Features

- Multi-milestone escrow per job
- Bid submission with expiry
- 2-of-3 multisig dispute resolution with timeout fallback
- On-chain freelancer ratings and profiles
- Category filter and search on the job board
- Non-custodial transaction signing with MetaMask

## Architecture (Signing and Trust)

- All state-changing transactions are signed by user wallets in MetaMask.
- The backend (Flask) never stores private keys and never signs transactions.
- Smart contracts are the source of truth.
- Flask provides read/index/config APIs for frontend UX.

Who signs what:

- Employer wallet: `postJob`, `acceptBid`, `releaseMilestonePayment`, `cancelJob`, `rateFreelancer`
- Freelancer wallet: `submitBid`, `markMilestoneComplete`, `withdrawExpiredBid`
- Either party: `raiseDispute`
- Arbitrator wallets: `submitVote` (2-of-3 required)

## Security Model

Contract implementation requirements:

- Checks-Effects-Interactions (CEI)
- OpenZeppelin `ReentrancyGuard` on payment paths
- OpenZeppelin `Pausable` for emergency stop
- Deterministic escrow invariants:
  - `msg.value == sum(milestoneAmounts)` on `postJob`
  - milestone ownership check before any milestone operation
  - no release before completion
  - no double payment
  - no payment while disputed
  - accepted bid must satisfy `bid.amount <= job.totalBudget`

## Tech Stack

- Solidity `0.8.20`
- Truffle `5.x`
- Ganache `7.x` (chainId `1337`)
- Python `3.10+`
- Flask `3.x`
- web3.py `6.x`
- web3.js `1.x`
- OpenZeppelin `5.x`

## Planned API Surface

- `GET /api/config` -> `{ chainIdHex, contractAddress, abi, deploymentBlock, abiVersion }`
- Read routes for jobs, job details, profiles, disputes
- SIWE-style auth routes (`/api/auth/challenge`, `/api/auth/verify`)
- Optional preflight route (`POST /api/tx/validate`)

## Testing Scope

- Escrow invariants
- Authorization negative tests
- Dispute edge cases (2-of-3 and timeout split)
- Event correctness for indexer/UI sync

## Project Milestones

1. Environment setup (Truffle, Ganache, Python deps, MetaMask)
2. Main escrow contract
3. Multisig arbitration contract
4. Flask config/read/indexing layer
5. Frontend + MetaMask integration
6. Feature completion + full test pass
7. Polish + demo artifacts

## Notes

- Default MVP setting: `platformFeeBps = 0`
- Optional later enhancements: IPFS for attachments, frontend framework migration

For full contract/API detail, see [design.md](./design.md).
