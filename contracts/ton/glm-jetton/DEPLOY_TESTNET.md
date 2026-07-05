# GLM Jetton Testnet Deployment Checklist

## Preconditions

- Legal review confirms testnet-only pilot is acceptable.
- Security owner approves selected Jetton implementation.
- Testnet treasury wallet is created and backed up.
- Testnet deployer wallet is funded with testnet TON.
- GLM metadata URL is reachable.
- Admin understands that testnet deployment is not a public token launch.

## Deployment Steps

1. Generate live operator handoff.
   ```bash
   npm run deploy:handoff
   ```
2. Select TEP-74 compatible Jetton implementation.
   ```bash
   npm run reference:fetch
   npm run reference:status
   ```
3. Set metadata:
   - name: `GLAME Coin`
   - symbol: `GLM`
   - decimals: `9`
   - description: `GLAME club utility unit for CryptoGLAME testnet claim pilot.`
4. Set admin address to GLAME testnet treasury/admin wallet.
5. Generate the GLM Blueprint deploy script.
   ```bash
   TON_JETTON_ADMIN_ADDRESS=EQ... npm run blueprint:prepare
   TON_JETTON_ADMIN_ADDRESS=EQ... npm run blueprint:status
   ```
6. Install/build the pinned reference and deploy Jetton master to TON testnet using the commands printed by `blueprint:prepare`.
7. Run `checkWalletLib` from the pinned reference after deploy and confirm wallet library status.
8. Save:
   - Jetton master address;
   - deploy tx hash;
   - wallet code hash;
   - admin address;
   - metadata URL.
9. Update `glm-jetton.testnet.json`.
   ```bash
   npm run record:deploy -- \
     --jetton-master-address EQ... \
     --deploy-tx-hash ... \
     --admin-address EQ... \
     --treasury-address EQ... \
     --wallet-code-hash ...
   ```
10. Add backend env:
   - `TON_GLM_JETTON_MASTER_ADDRESS`;
   - `TON_GLM_TREASURY_ADDRESS`;
   - `TON_NETWORK=testnet`.
11. Mint a small GLM amount to GLAME treasury test wallet.
12. Mint/transfer a test claim to a verified partner wallet.
13. Store tx hash in GLAME claim transaction.

## Rollback

Testnet rollback means:

- pause on-chain claim processing;
- mark failed/canceled claim in GLAME admin;
- refund internal GLM if the on-chain transfer did not happen;
- document incident in audit notes.
