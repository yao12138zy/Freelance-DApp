// web3_connect.js — MetaMask connection with chain validation

let userAccount = null;
let web3Instance = null;
let marketplaceContract = null;
let arbitrationContract = null;
let appConfig = null;

async function loadConfig() {
    const resp = await fetch("/api/config");
    if (!resp.ok) throw new Error("Failed to load config");
    appConfig = await resp.json();
    return appConfig;
}

async function connectWallet() {
    if (typeof window.ethereum === "undefined") {
        alert("Please install MetaMask to use this application.");
        return false;
    }

    try {
        // Load config from Flask backend
        if (!appConfig) await loadConfig();

        // Request accounts
        const accounts = await window.ethereum.request({ method: "eth_requestAccounts" });
        const chainId = await window.ethereum.request({ method: "eth_chainId" });

        // Validate chain
        if (chainId !== appConfig.chainIdHex) {
            alert(`Wrong network. Please switch MetaMask to chain ID ${appConfig.chainIdHex} (Ganache).`);
            return false;
        }

        userAccount = accounts[0];
        web3Instance = new Web3(window.ethereum);

        // Initialize contract instances
        marketplaceContract = new web3Instance.eth.Contract(appConfig.abi, appConfig.contractAddress);
        if (appConfig.arbitrationAddress && appConfig.arbitrationAbi) {
            arbitrationContract = new web3Instance.eth.Contract(appConfig.arbitrationAbi, appConfig.arbitrationAddress);
        }

        // Update UI
        updateWalletUI();

        return true;
    } catch (err) {
        console.error("Wallet connection failed:", err);
        alert("Failed to connect wallet: " + err.message);
        return false;
    }
}

function updateWalletUI() {
    const walletBtn = document.getElementById("connectWalletBtn");
    const walletAddr = document.getElementById("walletAddress");
    if (walletBtn && userAccount) {
        walletBtn.textContent = "Connected";
        walletBtn.classList.add("connected");
    }
    if (walletAddr && userAccount) {
        walletAddr.textContent = userAccount.slice(0, 6) + "..." + userAccount.slice(-4);
    }
}

// Listen for account/chain changes
if (window.ethereum) {
    window.ethereum.on("accountsChanged", (accounts) => {
        userAccount = accounts[0] || null;
        updateWalletUI();
        if (!userAccount) location.reload();
    });
    window.ethereum.on("chainChanged", () => {
        location.reload();
    });
}

// Helper: convert ETH string to wei as BigInt (no float precision loss)
function ethToWeiBigInt(ethString) {
    return BigInt(Web3.utils.toWei(ethString, "ether"));
}

// Helper: convert wei to ETH string for display
function weiToEth(weiString) {
    return Web3.utils.fromWei(weiString.toString(), "ether");
}

// Helper: format address for display
function shortAddress(addr) {
    if (!addr || addr === "0x0000000000000000000000000000000000000000") return "N/A";
    return addr.slice(0, 6) + "..." + addr.slice(-4);
}

// Helper: format timestamp
function formatTimestamp(ts) {
    if (!ts || ts === 0) return "N/A";
    return new Date(ts * 1000).toLocaleDateString();
}

// Job status enum mapping
const JOB_STATUS = ["Open", "InProgress", "Completed", "Disputed", "Cancelled"];
const BID_STATUS = ["Pending", "Accepted", "Rejected", "Expired"];

// Helper: get status badge HTML
function statusBadge(statusIndex, type = "job") {
    const statuses = type === "job" ? JOB_STATUS : BID_STATUS;
    const label = statuses[statusIndex] || "Unknown";
    const colors = type === "job"
        ? ["status-open", "status-inprogress", "status-completed", "status-disputed", "status-cancelled"]
        : ["status-pending", "status-accepted", "status-rejected", "status-expired"];
    return `<span class="status-badge ${colors[statusIndex] || ''}">${label}</span>`;
}

// Helper: show notification
function showNotification(message, type = "info") {
    const container = document.getElementById("notifications");
    if (!container) return;
    const div = document.createElement("div");
    div.className = `notification notification-${type}`;
    div.textContent = message;
    container.appendChild(div);
    setTimeout(() => div.remove(), 5000);
}

// Helper: show transaction pending/confirmed
function showTxStatus(message) {
    showNotification(message, "info");
}

function showTxSuccess(message) {
    showNotification(message, "success");
}

function showTxError(message) {
    showNotification(message, "error");
}
