// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

interface IFreelanceMarketplace {
    function resolveDispute(uint256 jobId, address payable winner) external;
    function resolveDisputeWithSplit(
        uint256 jobId,
        address payable party1, uint256 amount1,
        address payable party2, uint256 amount2
    ) external;
    function getRemainingEscrow(uint256 jobId) external view returns (uint256);
    function jobs(uint256 jobId) external view returns (
        uint256, address, string memory, string memory,
        uint256, uint256, uint8, address
    );
    function platformFeeBps() external view returns (uint256);
}

/**
 * @title MultiSigArbitration
 * @notice 2-of-3 arbitrator dispute resolution for the Freelance Marketplace.
 *         Three designated arbitrators vote on dispute outcomes. If two agree
 *         on a winner the resolution is executed immediately. If no consensus
 *         is reached within the timeout period either party may claim a 50/50
 *         split of the remaining escrow.
 */
contract MultiSigArbitration is Ownable, ReentrancyGuard {
    // -----------------------------------------------------------------------
    // State
    // -----------------------------------------------------------------------

    struct DisputeVote {
        uint256 jobId;
        uint8 voteCount;
        bool resolved;
        uint256 raisedAt;
    }

    // Can't have mapping inside struct that's returned, so separate the votes:
    mapping(uint256 => DisputeVote) public disputes;
    mapping(uint256 => mapping(address => address)) public disputeVotes; // jobId => arbitrator => votedWinner

    address[3] public arbitrators;
    IFreelanceMarketplace public marketplace;
    uint256 public constant TIMEOUT_PERIOD = 7 days;

    // -----------------------------------------------------------------------
    // Events
    // -----------------------------------------------------------------------

    event VoteSubmitted(
        uint256 indexed jobId,
        address indexed arbitrator,
        address votedFor
    );

    event DisputeResolutionExecuted(
        uint256 indexed jobId,
        address winner
    );

    event TimeoutSplitExecuted(
        uint256 indexed jobId,
        uint256 employerShare,
        uint256 freelancerShare
    );

    event ArbitratorReplaced(
        uint256 index,
        address oldArbitrator,
        address newArbitrator
    );

    // -----------------------------------------------------------------------
    // Constructor
    // -----------------------------------------------------------------------

    constructor(
        address _marketplace,
        address[3] memory _arbitrators
    ) Ownable(msg.sender) {
        require(_marketplace != address(0), "Invalid marketplace address");
        marketplace = IFreelanceMarketplace(_marketplace);
        arbitrators = _arbitrators;
    }

    // -----------------------------------------------------------------------
    // External / Public Functions
    // -----------------------------------------------------------------------

    /**
     * @notice Submit a vote for a dispute. If 2-of-3 arbitrators agree on the
     *         same winner the resolution is executed immediately.
     * @param jobId   The job ID that is in dispute.
     * @param votedWinner The address the arbitrator believes should win.
     */
    function submitVote(uint256 jobId, address payable votedWinner) external {
        require(_isArbitrator(msg.sender), "Caller is not an arbitrator");
        require(!disputes[jobId].resolved, "Dispute already resolved");
        require(
            disputeVotes[jobId][msg.sender] == address(0),
            "Arbitrator already voted"
        );

        // If this is the first vote for this jobId, initialise the dispute
        if (disputes[jobId].voteCount == 0) {
            disputes[jobId].raisedAt = block.timestamp;
            disputes[jobId].jobId = jobId;
        }

        // Record the vote
        disputeVotes[jobId][msg.sender] = votedWinner;
        disputes[jobId].voteCount++;

        emit VoteSubmitted(jobId, msg.sender, votedWinner);

        // Check for 2-of-3 consensus on votedWinner
        uint8 agreeing = 0;
        for (uint256 i = 0; i < 3; i++) {
            if (disputeVotes[jobId][arbitrators[i]] == votedWinner) {
                agreeing++;
            }
        }
        if (agreeing >= 2) {
            _executeResolution(jobId, votedWinner);
        }
    }

    /**
     * @notice If the arbitrators fail to reach consensus within TIMEOUT_PERIOD
     *         either the employer or the freelancer may claim a 50/50 split of
     *         the remaining escrow (minus platform fee).
     * @param jobId The job ID that is in dispute.
     */
    function claimTimeout(uint256 jobId) external nonReentrant {
        require(disputes[jobId].raisedAt > 0, "Dispute does not exist");
        require(!disputes[jobId].resolved, "Dispute already resolved");
        require(
            block.timestamp >= disputes[jobId].raisedAt + TIMEOUT_PERIOD,
            "Timeout period not yet elapsed"
        );

        // Retrieve employer and freelancer from the marketplace
        (, address employer, , , , , , address freelancer) = marketplace.jobs(jobId);
        require(
            msg.sender == employer || msg.sender == freelancer,
            "Caller is not employer or freelancer"
        );

        // Calculate the 50/50 split after platform fee
        uint256 remaining = marketplace.getRemainingEscrow(jobId);
        uint256 fee = remaining * marketplace.platformFeeBps() / 10000;
        uint256 distributable = remaining - fee;
        uint256 employerShare = distributable / 2;
        uint256 freelancerShare = distributable - employerShare; // odd wei goes to freelancer

        // Mark resolved and execute
        disputes[jobId].resolved = true;

        marketplace.resolveDisputeWithSplit(
            jobId,
            payable(employer), employerShare,
            payable(freelancer), freelancerShare
        );

        emit TimeoutSplitExecuted(jobId, employerShare, freelancerShare);
    }

    /**
     * @notice Owner can replace one of the three arbitrators.
     * @param index          The index (0, 1, or 2) of the arbitrator to replace.
     * @param newArbitrator  The address of the replacement arbitrator.
     */
    function replaceArbitrator(uint256 index, address newArbitrator) external onlyOwner {
        require(index < 3, "Index out of bounds");
        require(newArbitrator != address(0), "Invalid arbitrator address");

        address oldArbitrator = arbitrators[index];
        emit ArbitratorReplaced(index, oldArbitrator, newArbitrator);

        arbitrators[index] = newArbitrator;
    }

    /**
     * @notice View helper: get the vote an arbitrator cast for a given dispute.
     * @param jobId      The job ID.
     * @param arbitrator The arbitrator address.
     * @return The address the arbitrator voted for (address(0) if not voted).
     */
    function getVote(uint256 jobId, address arbitrator) external view returns (address) {
        return disputeVotes[jobId][arbitrator];
    }

    // -----------------------------------------------------------------------
    // Internal Functions
    // -----------------------------------------------------------------------

    /**
     * @dev Execute the dispute resolution by forwarding the winning address to
     *      the marketplace contract.
     */
    function _executeResolution(uint256 jobId, address payable winner) internal {
        disputes[jobId].resolved = true;
        marketplace.resolveDispute(jobId, winner);
        emit DisputeResolutionExecuted(jobId, winner);
    }

    /**
     * @dev Check whether an address is one of the three arbitrators.
     */
    function _isArbitrator(address addr) internal view returns (bool) {
        for (uint256 i = 0; i < 3; i++) {
            if (arbitrators[i] == addr) {
                return true;
            }
        }
        return false;
    }
}
