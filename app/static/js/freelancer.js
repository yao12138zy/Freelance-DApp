// freelancer.js — Freelancer and shared transaction methods

async function createProfile(name, bio) {
    if (!marketplaceContract || !userAccount) {
        showTxError("Please connect your wallet first.");
        return;
    }
    try {
        await marketplaceContract.methods.createProfile(name, bio)
            .estimateGas({ from: userAccount });
        const tx = await marketplaceContract.methods.createProfile(name, bio)
            .send({ from: userAccount });
        showTxSuccess("Profile created! TX: " + tx.transactionHash);
        return tx;
    } catch (err) {
        showTxError("Failed to create profile: " + err.message);
        throw err;
    }
}

async function submitBid(jobId, amountEth, proposal, bidDurationSeconds) {
    if (!marketplaceContract || !userAccount) {
        showTxError("Please connect your wallet first.");
        return;
    }
    try {
        const amountWei = Web3.utils.toWei(amountEth, "ether");
        showTxStatus("Estimating gas...");
        await marketplaceContract.methods
            .submitBid(jobId, amountWei, proposal, bidDurationSeconds)
            .estimateGas({ from: userAccount });

        showTxStatus("Please confirm in MetaMask...");
        const tx = await marketplaceContract.methods
            .submitBid(jobId, amountWei, proposal, bidDurationSeconds)
            .send({ from: userAccount });

        showTxSuccess("Bid submitted! TX: " + tx.transactionHash);
        return tx;
    } catch (err) {
        showTxError("Failed to submit bid: " + err.message);
        throw err;
    }
}

async function markMilestoneComplete(jobId, milestoneId) {
    if (!marketplaceContract || !userAccount) {
        showTxError("Please connect your wallet first.");
        return;
    }
    try {
        await marketplaceContract.methods.markMilestoneComplete(jobId, milestoneId)
            .estimateGas({ from: userAccount });
        const tx = await marketplaceContract.methods.markMilestoneComplete(jobId, milestoneId)
            .send({ from: userAccount });
        showTxSuccess("Milestone marked complete! TX: " + tx.transactionHash);
        return tx;
    } catch (err) {
        showTxError("Failed to mark milestone complete: " + err.message);
        throw err;
    }
}

async function withdrawExpiredBid(bidId) {
    if (!marketplaceContract || !userAccount) {
        showTxError("Please connect your wallet first.");
        return;
    }
    try {
        await marketplaceContract.methods.withdrawExpiredBid(bidId)
            .estimateGas({ from: userAccount });
        const tx = await marketplaceContract.methods.withdrawExpiredBid(bidId)
            .send({ from: userAccount });
        showTxSuccess("Expired bid withdrawn. TX: " + tx.transactionHash);
        return tx;
    } catch (err) {
        showTxError("Failed to withdraw bid: " + err.message);
        throw err;
    }
}

async function raiseDispute(jobId) {
    if (!marketplaceContract || !userAccount) {
        showTxError("Please connect your wallet first.");
        return;
    }
    try {
        await marketplaceContract.methods.raiseDispute(jobId)
            .estimateGas({ from: userAccount });
        const tx = await marketplaceContract.methods.raiseDispute(jobId)
            .send({ from: userAccount });
        showTxSuccess("Dispute raised. TX: " + tx.transactionHash);
        return tx;
    } catch (err) {
        showTxError("Failed to raise dispute: " + err.message);
        throw err;
    }
}

// Arbitrator function (used on arbitrator.html)
async function submitVote(jobId, votedWinnerAddress) {
    if (!arbitrationContract || !userAccount) {
        showTxError("Please connect your wallet first.");
        return;
    }
    try {
        await arbitrationContract.methods.submitVote(jobId, votedWinnerAddress)
            .estimateGas({ from: userAccount });
        const tx = await arbitrationContract.methods.submitVote(jobId, votedWinnerAddress)
            .send({ from: userAccount });
        showTxSuccess("Vote submitted! TX: " + tx.transactionHash);
        return tx;
    } catch (err) {
        showTxError("Failed to submit vote: " + err.message);
        throw err;
    }
}

async function claimTimeout(jobId) {
    if (!arbitrationContract || !userAccount) {
        showTxError("Please connect your wallet first.");
        return;
    }
    try {
        await arbitrationContract.methods.claimTimeout(jobId)
            .estimateGas({ from: userAccount });
        const tx = await arbitrationContract.methods.claimTimeout(jobId)
            .send({ from: userAccount });
        showTxSuccess("Timeout split claimed! TX: " + tx.transactionHash);
        return tx;
    } catch (err) {
        showTxError("Failed to claim timeout: " + err.message);
        throw err;
    }
}
