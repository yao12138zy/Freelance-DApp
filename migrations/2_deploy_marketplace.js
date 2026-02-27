const FreelanceMarketplace = artifacts.require("FreelanceMarketplace");
const MultiSigArbitration = artifacts.require("MultiSigArbitration");

module.exports = async function(deployer, network, accounts) {
  // Deploy marketplace with 0 platform fee for MVP
  await deployer.deploy(FreelanceMarketplace, 0);
  const marketplace = await FreelanceMarketplace.deployed();

  // Deploy arbitration with 3 arbitrator addresses from Ganache
  await deployer.deploy(
    MultiSigArbitration,
    marketplace.address,
    [accounts[7], accounts[8], accounts[9]]
  );
  const arbitration = await MultiSigArbitration.deployed();

  // Wire arbitration contract into marketplace
  await marketplace.setArbitrationContract(arbitration.address);
};
