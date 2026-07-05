# GLM Jetton Security Review Checklist

## Contract Scope

- Jetton master contract
- Jetton wallet contract
- Implementation decision: `IMPLEMENTATION_DECISION.md`
- Reference lock: `reference.jetton-contract.lock.json`
- Vendored reference checkout: `vendor/ton-blockchain-jetton-contract`
- Mint/admin controls
- Metadata update controls
- Treasury wallet operations
- Claim operator workflow

## Required Checks

- TEP-74 compatibility.
- Local reference checkout matches the locked commit.
- Reference dependency audit is reviewed before mainnet; current upstream dev dependency audit must not be ignored.
- JettonMinter and JettonWallet compiled artifact hashes are recorded before deploy.
- JettonWallet `libraryHash` is recorded and checked with `checkWalletLib`.
- Minting can only be performed by authorized admin.
- Admin transfer/revoke behavior is explicit.
- Metadata update permissions are explicit.
- Wallet address derivation matches standard Jetton wallet behavior.
- Transfer, burn and notification behavior matches selected implementation.
- Excess TON handling is reviewed.
- No hidden upgrade path without documented admin control.
- No unlimited production minting without treasury policy.

## GLAME-Specific Checks

- GLAME ledger uses integer GLM, but Jetton metadata uses `decimals = 9` for TON wallet display compatibility; operator scripts must convert GLM amounts to base units before mint.
- Claim amount equals internal GLM pending claim amount.
- Claim destination equals verified TON wallet address.
- Claim is idempotent: one claim -> one on-chain tx hash.
- Failed on-chain operation does not mark claim as processed.
- Processed claim cannot be processed twice.
- Manual tx hash entry requires admin identity and comment.

## Mainnet Gate

Mainnet deployment is blocked until:

- legal approval;
- security review;
- treasury policy approval;
- incident response process;
- public risk disclosure;
- operator runbook.
