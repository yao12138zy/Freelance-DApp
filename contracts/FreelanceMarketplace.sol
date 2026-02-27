// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/utils/Pausable.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract FreelanceMarketplace is ReentrancyGuard, Pausable, Ownable {

    // ──────────────────────────────────────────────
    //  Enums
    // ──────────────────────────────────────────────

    enum JobStatus { Open, InProgress, Completed, Disputed, Cancelled }
    enum BidStatus { Pending, Accepted, Rejected, Expired }

    // ──────────────────────────────────────────────
    //  Structs
    // ──────────────────────────────────────────────

    struct Milestone {
        uint256 jobId;
        string description;
        uint256 amount;    // in wei
        bool completed;
        bool paid;
    }

    struct Job {
        uint256 jobId;
        address employer;
        string title;
        string category;
        uint256 totalBudget;
        uint256 deadline;
        JobStatus status;
        address acceptedFreelancer;
        uint256[] milestoneIds;
    }

    struct Bid {
        uint256 bidId;
        uint256 jobId;
        address freelancer;
        uint256 amount;
        string proposal;
        uint256 expiresAt;
        BidStatus status;
    }

    struct Profile {
        address wallet;
        string name;
        string bio;
        uint256 totalJobsCompleted;
        uint256 reputationScore;
        uint256 ratingCount;
        bool exists;
    }

    // ──────────────────────────────────────────────
    //  State Variables
    // ──────────────────────────────────────────────

    uint256 public jobCount;
    uint256 public bidCount;
    uint256 public milestoneCount;

    mapping(uint256 => Job) public jobs;
    mapping(uint256 => Bid) public bids;
    mapping(uint256 => Milestone) public milestones;
    mapping(address => Profile) public profiles;
    mapping(uint256 => uint256[]) public jobBids;
    mapping(address => uint256[]) public employerJobs;
    mapping(address => uint256[]) public freelancerBids;
    mapping(uint256 => bool) public jobRated;

    address public arbitrationContract;
    uint256 public platformFeeBps;

    // ──────────────────────────────────────────────
    //  Events
    // ──────────────────────────────────────────────

    event JobPosted(uint256 indexed jobId, address indexed employer, string category, uint256 totalBudget);
    event JobCancelled(uint256 indexed jobId, address indexed employer);
    event JobStatusChanged(uint256 indexed jobId, JobStatus oldStatus, JobStatus newStatus);
    event BidSubmitted(uint256 indexed bidId, uint256 indexed jobId, address indexed freelancer, uint256 amount);
    event BidAccepted(uint256 indexed bidId, uint256 indexed jobId, address indexed freelancer);
    event BidRejected(uint256 indexed bidId, uint256 indexed jobId);
    event BidWithdrawn(uint256 indexed bidId, address indexed freelancer);
    event MilestoneCompleted(uint256 indexed jobId, uint256 indexed milestoneId, address freelancer);
    event PaymentReleased(uint256 indexed jobId, uint256 indexed milestoneId, address indexed freelancer, uint256 amount);
    event DisputeRaised(uint256 indexed jobId, address indexed raisedBy);
    event DisputeResolved(uint256 indexed jobId, address indexed winner, uint256 amount);
    event ProfileCreated(address indexed wallet);
    event ProfileUpdated(address indexed wallet);
    event FreelancerRated(uint256 indexed jobId, address indexed freelancer, uint256 score, address ratedBy);
    event ContractPaused(address by);
    event ContractUnpaused(address by);

    // ──────────────────────────────────────────────
    //  Constructor
    // ──────────────────────────────────────────────

    constructor(uint256 _platformFeeBps) Ownable(msg.sender) {
        platformFeeBps = _platformFeeBps;
    }

    // ──────────────────────────────────────────────
    //  Profile Functions
    // ──────────────────────────────────────────────

    function createProfile(string memory name, string memory bio) external {
        if (profiles[msg.sender].exists) {
            profiles[msg.sender].name = name;
            profiles[msg.sender].bio = bio;
            emit ProfileUpdated(msg.sender);
        } else {
            profiles[msg.sender] = Profile({
                wallet: msg.sender,
                name: name,
                bio: bio,
                totalJobsCompleted: 0,
                reputationScore: 0,
                ratingCount: 0,
                exists: true
            });
            emit ProfileCreated(msg.sender);
        }
    }

    function getProfile(address wallet) external view returns (Profile memory) {
        return profiles[wallet];
    }

    // ──────────────────────────────────────────────
    //  Job Functions
    // ──────────────────────────────────────────────

    function postJob(
        string memory title,
        string memory category,
        uint256 deadline,
        string[] memory milestoneDescriptions,
        uint256[] memory milestoneAmounts
    ) external payable whenNotPaused {
        require(milestoneDescriptions.length == milestoneAmounts.length, "Milestone arrays length mismatch");
        require(milestoneDescriptions.length > 0, "At least one milestone required");
        require(deadline > block.timestamp, "Deadline must be in the future");

        uint256 totalBudget = 0;
        for (uint256 i = 0; i < milestoneAmounts.length; i++) {
            require(milestoneAmounts[i] > 0, "Milestone amount must be > 0");
            totalBudget += milestoneAmounts[i];
        }
        require(msg.value == totalBudget, "msg.value must equal sum of milestone amounts");

        jobCount++;
        uint256 newJobId = jobCount;

        Job storage newJob = jobs[newJobId];
        newJob.jobId = newJobId;
        newJob.employer = msg.sender;
        newJob.title = title;
        newJob.category = category;
        newJob.totalBudget = totalBudget;
        newJob.deadline = deadline;
        newJob.status = JobStatus.Open;

        for (uint256 i = 0; i < milestoneDescriptions.length; i++) {
            milestoneCount++;
            uint256 newMilestoneId = milestoneCount;

            milestones[newMilestoneId] = Milestone({
                jobId: newJobId,
                description: milestoneDescriptions[i],
                amount: milestoneAmounts[i],
                completed: false,
                paid: false
            });

            newJob.milestoneIds.push(newMilestoneId);
        }

        employerJobs[msg.sender].push(newJobId);

        emit JobPosted(newJobId, msg.sender, category, totalBudget);
    }

    function cancelJob(uint256 jobId) external nonReentrant {
        Job storage job = jobs[jobId];
        require(job.employer == msg.sender, "Only employer can cancel");
        require(job.status == JobStatus.Open, "Job must be Open to cancel");

        // Effects first (CEI pattern)
        JobStatus oldStatus = job.status;
        job.status = JobStatus.Cancelled;

        emit JobCancelled(jobId, msg.sender);
        emit JobStatusChanged(jobId, oldStatus, JobStatus.Cancelled);

        // Interaction last — refund the totalBudget held in escrow
        (bool success, ) = payable(msg.sender).call{value: job.totalBudget}("");
        require(success, "Transfer failed");
    }

    function getJob(uint256 jobId) external view returns (Job memory) {
        return jobs[jobId];
    }

    // ──────────────────────────────────────────────
    //  Bid Functions
    // ──────────────────────────────────────────────

    function submitBid(
        uint256 jobId,
        uint256 amount,
        string memory proposal,
        uint256 bidDuration
    ) external whenNotPaused {
        Job storage job = jobs[jobId];
        require(job.status == JobStatus.Open, "Job is not open for bids");
        require(msg.sender != job.employer, "Employer cannot bid on own job");
        require(amount > 0, "Bid amount must be > 0");
        require(bidDuration > 0, "Bid duration must be > 0");

        bidCount++;
        uint256 newBidId = bidCount;

        bids[newBidId] = Bid({
            bidId: newBidId,
            jobId: jobId,
            freelancer: msg.sender,
            amount: amount,
            proposal: proposal,
            expiresAt: block.timestamp + bidDuration,
            status: BidStatus.Pending
        });

        jobBids[jobId].push(newBidId);
        freelancerBids[msg.sender].push(newBidId);

        emit BidSubmitted(newBidId, jobId, msg.sender, amount);
    }

    function acceptBid(uint256 jobId, uint256 bidId) external whenNotPaused {
        Job storage job = jobs[jobId];
        Bid storage bid = bids[bidId];

        require(job.employer == msg.sender, "Only employer can accept bids");
        require(job.status == JobStatus.Open, "Job must be Open");
        require(bid.status == BidStatus.Pending, "Bid must be Pending");
        require(bid.jobId == jobId, "Bid does not belong to this job");
        require(block.timestamp < bid.expiresAt, "Bid has expired");
        require(bid.amount <= job.totalBudget, "Bid amount exceeds budget");

        bid.status = BidStatus.Accepted;

        JobStatus oldStatus = job.status;
        job.status = JobStatus.InProgress;
        job.acceptedFreelancer = bid.freelancer;

        emit BidAccepted(bidId, jobId, bid.freelancer);
        emit JobStatusChanged(jobId, oldStatus, JobStatus.InProgress);
    }

    function rejectBid(uint256 bidId) external {
        Bid storage bid = bids[bidId];
        Job storage job = jobs[bid.jobId];

        require(job.employer == msg.sender, "Only employer can reject bids");

        bid.status = BidStatus.Rejected;

        emit BidRejected(bidId, bid.jobId);
    }

    function withdrawExpiredBid(uint256 bidId) external {
        Bid storage bid = bids[bidId];

        require(bid.freelancer == msg.sender, "Only bid owner can withdraw");
        require(block.timestamp >= bid.expiresAt, "Bid has not expired yet");
        require(bid.status == BidStatus.Pending, "Bid must be Pending");

        bid.status = BidStatus.Expired;

        emit BidWithdrawn(bidId, msg.sender);
    }

    // ──────────────────────────────────────────────
    //  Milestone Functions
    // ──────────────────────────────────────────────

    function markMilestoneComplete(uint256 jobId, uint256 milestoneId) external {
        Job storage job = jobs[jobId];
        Milestone storage milestone = milestones[milestoneId];

        require(job.acceptedFreelancer == msg.sender, "Only accepted freelancer");
        require(milestone.jobId == jobId, "Milestone does not belong to this job");
        require(!milestone.completed, "Milestone already completed");
        require(job.status == JobStatus.InProgress, "Job must be InProgress");

        milestone.completed = true;

        emit MilestoneCompleted(jobId, milestoneId, msg.sender);
    }

    function releaseMilestonePayment(
        uint256 jobId,
        uint256 milestoneId
    ) external nonReentrant whenNotPaused {
        Job storage job = jobs[jobId];
        Milestone storage milestone = milestones[milestoneId];

        require(job.employer == msg.sender, "Only employer can release payment");
        require(milestone.jobId == jobId, "Milestone does not belong to this job");
        require(milestone.completed, "Milestone not completed");
        require(!milestone.paid, "Milestone already paid");
        require(job.status != JobStatus.Disputed, "Job is disputed");

        // Effects first (CEI pattern)
        milestone.paid = true;

        uint256 paymentAmount = milestone.amount;

        emit PaymentReleased(jobId, milestoneId, job.acceptedFreelancer, paymentAmount);

        // Check if all milestones are paid — auto-complete the job
        bool allPaid = true;
        for (uint256 i = 0; i < job.milestoneIds.length; i++) {
            if (!milestones[job.milestoneIds[i]].paid) {
                allPaid = false;
                break;
            }
        }

        if (allPaid) {
            JobStatus oldStatus = job.status;
            job.status = JobStatus.Completed;

            if (profiles[job.acceptedFreelancer].exists) {
                profiles[job.acceptedFreelancer].totalJobsCompleted++;
            }

            emit JobStatusChanged(jobId, oldStatus, JobStatus.Completed);
        }

        // Interaction last
        (bool success, ) = payable(job.acceptedFreelancer).call{value: paymentAmount}("");
        require(success, "Transfer failed");
    }

    function releaseAllPayments(uint256 jobId) external nonReentrant whenNotPaused {
        Job storage job = jobs[jobId];

        require(job.employer == msg.sender, "Only employer can release payments");
        require(job.status != JobStatus.Disputed, "Job is disputed");

        uint256[] memory mIds = job.milestoneIds;
        uint256 totalReleased = 0;

        // Effects first — mark all completed+unpaid milestones as paid
        for (uint256 i = 0; i < mIds.length; i++) {
            Milestone storage milestone = milestones[mIds[i]];
            if (milestone.completed && !milestone.paid) {
                milestone.paid = true;
                totalReleased += milestone.amount;

                emit PaymentReleased(jobId, mIds[i], job.acceptedFreelancer, milestone.amount);
            }
        }

        // Check if all milestones are now paid — auto-complete the job
        bool allPaid = true;
        for (uint256 i = 0; i < mIds.length; i++) {
            if (!milestones[mIds[i]].paid) {
                allPaid = false;
                break;
            }
        }

        if (allPaid) {
            JobStatus oldStatus = job.status;
            job.status = JobStatus.Completed;

            if (profiles[job.acceptedFreelancer].exists) {
                profiles[job.acceptedFreelancer].totalJobsCompleted++;
            }

            emit JobStatusChanged(jobId, oldStatus, JobStatus.Completed);
        }

        // Interaction last
        if (totalReleased > 0) {
            (bool success, ) = payable(job.acceptedFreelancer).call{value: totalReleased}("");
            require(success, "Transfer failed");
        }
    }

    // ──────────────────────────────────────────────
    //  Dispute Functions
    // ──────────────────────────────────────────────

    function raiseDispute(uint256 jobId) external {
        Job storage job = jobs[jobId];

        require(
            msg.sender == job.employer || msg.sender == job.acceptedFreelancer,
            "Only employer or freelancer can raise dispute"
        );
        require(job.status == JobStatus.InProgress, "Job must be InProgress");

        JobStatus oldStatus = job.status;
        job.status = JobStatus.Disputed;

        emit DisputeRaised(jobId, msg.sender);
        emit JobStatusChanged(jobId, oldStatus, JobStatus.Disputed);
    }

    function resolveDispute(
        uint256 jobId,
        address payable winner
    ) external nonReentrant {
        require(msg.sender == arbitrationContract, "Only arbitration contract");

        Job storage job = jobs[jobId];
        require(job.status == JobStatus.Disputed, "Job must be Disputed");

        // Calculate remaining escrow
        uint256 remaining = 0;
        for (uint256 i = 0; i < job.milestoneIds.length; i++) {
            Milestone storage milestone = milestones[job.milestoneIds[i]];
            if (!milestone.paid) {
                remaining += milestone.amount;
                milestone.paid = true; // Effects first (CEI)
            }
        }

        // Effects
        JobStatus oldStatus = job.status;
        job.status = JobStatus.Completed;

        emit DisputeResolved(jobId, winner, remaining);
        emit JobStatusChanged(jobId, oldStatus, JobStatus.Completed);

        // Interaction last
        if (remaining > 0) {
            (bool success, ) = winner.call{value: remaining}("");
            require(success, "Transfer failed");
        }
    }

    function resolveDisputeWithSplit(
        uint256 jobId,
        address payable party1,
        uint256 amount1,
        address payable party2,
        uint256 amount2
    ) external nonReentrant {
        require(msg.sender == arbitrationContract, "Only arbitration contract");

        Job storage job = jobs[jobId];
        require(job.status == JobStatus.Disputed, "Job must be Disputed");

        // Calculate remaining escrow
        uint256 remaining = 0;
        for (uint256 i = 0; i < job.milestoneIds.length; i++) {
            Milestone storage milestone = milestones[job.milestoneIds[i]];
            if (!milestone.paid) {
                remaining += milestone.amount;
                milestone.paid = true; // Effects first (CEI)
            }
        }

        require(amount1 + amount2 == remaining, "Split must equal remaining escrow");

        // Effects
        JobStatus oldStatus = job.status;
        job.status = JobStatus.Completed;

        // Emit DisputeResolved for the larger share party
        if (amount1 >= amount2) {
            emit DisputeResolved(jobId, party1, amount1);
        } else {
            emit DisputeResolved(jobId, party2, amount2);
        }
        emit JobStatusChanged(jobId, oldStatus, JobStatus.Completed);

        // Interactions last
        if (amount1 > 0) {
            (bool success1, ) = party1.call{value: amount1}("");
            require(success1, "Transfer to party1 failed");
        }
        if (amount2 > 0) {
            (bool success2, ) = party2.call{value: amount2}("");
            require(success2, "Transfer to party2 failed");
        }
    }

    // ──────────────────────────────────────────────
    //  Rating Functions
    // ──────────────────────────────────────────────

    function rateFreelancer(uint256 jobId, uint256 score) external {
        Job storage job = jobs[jobId];

        require(job.employer == msg.sender, "Only employer can rate");
        require(job.status == JobStatus.Completed, "Job must be Completed");
        require(!jobRated[jobId], "Already rated for this job");
        require(score >= 1 && score <= 5, "Score must be between 1 and 5");

        jobRated[jobId] = true;

        Profile storage freelancerProfile = profiles[job.acceptedFreelancer];
        freelancerProfile.reputationScore += score;
        freelancerProfile.ratingCount++;

        emit FreelancerRated(jobId, job.acceptedFreelancer, score, msg.sender);
    }

    // ──────────────────────────────────────────────
    //  View / Helper Functions
    // ──────────────────────────────────────────────

    function getRemainingEscrow(uint256 jobId) external view returns (uint256) {
        Job storage job = jobs[jobId];
        uint256 remaining = 0;
        for (uint256 i = 0; i < job.milestoneIds.length; i++) {
            if (!milestones[job.milestoneIds[i]].paid) {
                remaining += milestones[job.milestoneIds[i]].amount;
            }
        }
        return remaining;
    }

    function setArbitrationContract(address _arb) external onlyOwner {
        arbitrationContract = _arb;
    }

    function pause() external onlyOwner {
        _pause();
        emit ContractPaused(msg.sender);
    }

    function unpause() external onlyOwner {
        _unpause();
        emit ContractUnpaused(msg.sender);
    }

    function getJobBids(uint256 jobId) external view returns (uint256[] memory) {
        return jobBids[jobId];
    }

    function getJobMilestones(uint256 jobId) external view returns (uint256[] memory) {
        return jobs[jobId].milestoneIds;
    }
}
