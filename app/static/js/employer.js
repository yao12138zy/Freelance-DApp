// employer.js — Employer transaction methods

async function postJob(title, category, deadline, milestoneDescs, milestoneAmountsEth) {
    if (!marketplaceContract || !userAccount) {
        showTxError("Please connect your wallet first.");
        return;
    }
    try {
        const milestoneAmountsWei = milestoneAmountsEth.map(eth => Web3.utils.toWei(eth, "ether"));
        const totalWei = milestoneAmountsWei.reduce((a, b) => {
            return (BigInt(a) + BigInt(b)).toString();
        }, "0");

        showTxStatus("Estimating gas...");
        await marketplaceContract.methods
            .postJob(title, category, deadline, milestoneDescs, milestoneAmountsWei)
            .estimateGas({ from: userAccount, value: totalWei });

        showTxStatus("Please confirm the transaction in MetaMask...");
        const tx = await marketplaceContract.methods
            .postJob(title, category, deadline, milestoneDescs, milestoneAmountsWei)
            .send({ from: userAccount, value: totalWei });

        showTxSuccess("Job posted successfully! TX: " + tx.transactionHash);
        return tx;
    } catch (err) {
        showTxError("Failed to post job: " + err.message);
        throw err;
    }
}

async function cancelJob(jobId) {
    if (!marketplaceContract || !userAccount) {
        showTxError("Please connect your wallet first.");
        return;
    }
    try {
        showTxStatus("Estimating gas...");
        await marketplaceContract.methods.cancelJob(jobId)
            .estimateGas({ from: userAccount });

        showTxStatus("Please confirm in MetaMask...");
        const tx = await marketplaceContract.methods.cancelJob(jobId)
            .send({ from: userAccount });

        showTxSuccess("Job cancelled. TX: " + tx.transactionHash);
        return tx;
    } catch (err) {
        showTxError("Failed to cancel job: " + err.message);
        throw err;
    }
}

async function acceptBid(jobId, bidId) {
    if (!marketplaceContract || !userAccount) {
        showTxError("Please connect your wallet first.");
        return;
    }
    try {
        showTxStatus("Estimating gas...");
        await marketplaceContract.methods.acceptBid(jobId, bidId)
            .estimateGas({ from: userAccount });

        showTxStatus("Please confirm in MetaMask...");
        const tx = await marketplaceContract.methods.acceptBid(jobId, bidId)
            .send({ from: userAccount });

        showTxSuccess("Bid accepted! TX: " + tx.transactionHash);
        return tx;
    } catch (err) {
        showTxError("Failed to accept bid: " + err.message);
        throw err;
    }
}

async function rejectBid(bidId) {
    if (!marketplaceContract || !userAccount) {
        showTxError("Please connect your wallet first.");
        return;
    }
    try {
        await marketplaceContract.methods.rejectBid(bidId)
            .estimateGas({ from: userAccount });
        const tx = await marketplaceContract.methods.rejectBid(bidId)
            .send({ from: userAccount });
        showTxSuccess("Bid rejected. TX: " + tx.transactionHash);
        return tx;
    } catch (err) {
        showTxError("Failed to reject bid: " + err.message);
        throw err;
    }
}

async function releaseMilestonePayment(jobId, milestoneId) {
    if (!marketplaceContract || !userAccount) {
        showTxError("Please connect your wallet first.");
        return;
    }
    try {
        showTxStatus("Estimating gas...");
        await marketplaceContract.methods.releaseMilestonePayment(jobId, milestoneId)
            .estimateGas({ from: userAccount });

        showTxStatus("Please confirm payment release in MetaMask...");
        const tx = await marketplaceContract.methods.releaseMilestonePayment(jobId, milestoneId)
            .send({ from: userAccount });

        showTxSuccess("Payment released! TX: " + tx.transactionHash);
        return tx;
    } catch (err) {
        showTxError("Failed to release payment: " + err.message);
        throw err;
    }
}

async function releaseAllPayments(jobId) {
    if (!marketplaceContract || !userAccount) {
        showTxError("Please connect your wallet first.");
        return;
    }
    try {
        showTxStatus("Estimating gas...");
        await marketplaceContract.methods.releaseAllPayments(jobId)
            .estimateGas({ from: userAccount });

        showTxStatus("Please confirm in MetaMask...");
        const tx = await marketplaceContract.methods.releaseAllPayments(jobId)
            .send({ from: userAccount });

        showTxSuccess("All payments released! TX: " + tx.transactionHash);
        return tx;
    } catch (err) {
        showTxError("Failed to release payments: " + err.message);
        throw err;
    }
}

async function rateFreelancer(jobId, score) {
    if (!marketplaceContract || !userAccount) {
        showTxError("Please connect your wallet first.");
        return;
    }
    if (score < 1 || score > 5) {
        showTxError("Rating must be between 1 and 5.");
        return;
    }
    try {
        await marketplaceContract.methods.rateFreelancer(jobId, score)
            .estimateGas({ from: userAccount });
        const tx = await marketplaceContract.methods.rateFreelancer(jobId, score)
            .send({ from: userAccount });
        showTxSuccess("Freelancer rated! TX: " + tx.transactionHash);
        return tx;
    } catch (err) {
        showTxError("Failed to rate freelancer: " + err.message);
        throw err;
    }
}
