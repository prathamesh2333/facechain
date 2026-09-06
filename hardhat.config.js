/**
 * Hardhat is used here only to provide a persistent local JSON-RPC node
 * (`npx hardhat node`). Compilation and deployment of FaceRegistry.sol are
 * done from Python with py-solc-x + web3.py, so there is nothing else to run.
 */
module.exports = {
  solidity: "0.8.20",
  paths: { sources: "./contracts" },
  networks: {
    hardhat: { chainId: 31337 },
  },
};
