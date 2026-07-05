# CryptoGLAME KYC/AML Policy Draft

Status: internal draft for legal/compliance review  
Last updated: 2026-07-02

## 1. Scope

This draft applies to future on-chain claim, crypto payout, P2P marketplace and high-value bridge operations.

## 2. Current MVP

Current internal GLM ledger does not provide unrestricted cash-out. TON Connect verifies wallet ownership but is not full identity verification.

## 3. Triggers for Additional Review

Additional review is required for:

- crypto payout requests;
- repeated high-value bridge operations;
- suspicious self-referral patterns;
- many wallets linked to one customer;
- attempts to bypass limits;
- external exchange/DEX scenarios;
- manual treasury operation requests.

## 4. Controls

- verified phone/account before partner access;
- TON `ton_proof` before wallet verification;
- admin approval for claim enablement;
- limits per operation and per month;
- audit trail for bridge, claim, redemption and repair;
- public audit hash for ledger transparency;
- freeze/review status for suspicious accounts.

## 5. Required Before Crypto Payouts

Before enabling partner crypto payouts:

- approved legal/accounting model;
- partner identity status;
- wallet screening policy;
- transaction limits;
- tax/accounting report;
- incident process.

