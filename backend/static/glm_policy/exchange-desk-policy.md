# CryptoGLAME Exchange Desk Policy

Updated: 2026-08-01

## Purpose

The GLAME exchange desk is a controlled utility pilot for two partner-cabinet flows:

- buy GLM for GRAM from the GLAME bank allocation;
- request a limited GLM to GRAM exchange through GLAME after transferring GLM to the GLAME treasury wallet.

The exchange desk is not a public DEX, not a promise of token price growth, not an investment product, and not a guaranteed buyback program.

## Buy GLM For GRAM

The partner creates a buy request in the partner cabinet. The system calculates the GRAM amount from the current GRAM/RUB operational rate and the configured GLM distribution rule.

After the partner sends GRAM to GLAME treasury and settlement verifies the TON transaction, GLAME transfers GLM from the operational hot-wallet to the partner's verified TON wallet.

Default operational rule:

- distribution reference: `1 GLM = 1 RUB`;
- GRAM amount is calculated by the current GRAM/RUB rate;
- operation limits are enforced by backend policy and signer limits.

## Sell GLM For GRAM

The partner creates a sell request in the partner cabinet. The request shows an estimated GRAM payout using the current GLAME exchange desk rule, spread, and GRAM/RUB rate.

The partner must transfer GLM from the verified TON wallet to the GLAME treasury wallet. GLAME verifies the incoming GLM transfer and closes the request manually or through an approved operator workflow.

GRAM payout is limited by:

- current exchange desk enabled/paused status;
- per-operation and daily limits;
- available treasury reserve;
- compliance, anti-fraud, and manual review rules;
- current spread and operational rate.

GLAME may reject, pause, delay, or manually review a request.

## No Public Buyback Promise

The exchange desk does not create an obligation for GLAME to buy GLM from every holder, at every time, or at a fixed public price.

GLAME does not promise:

- token price growth;
- guaranteed liquidity;
- fixed market value;
- permanent buyback;
- investment return;
- DEX listing;
- USDT or fiat redemption.

## Admin Controls

The production operator must be able to:

- pause the exchange desk;
- update limits and spread through env/config;
- verify incoming GLM deposits;
- record GRAM payout transaction hashes;
- reject suspicious or unsupported requests;
- preserve audit evidence for every closed request.

## Required Evidence

Each processed sell request must have:

- request id;
- verified partner account and TON wallet;
- GLM amount;
- expected GLM sender wallet;
- GLAME treasury wallet;
- incoming GLM transaction hash or verified settlement evidence;
- outgoing GRAM payout transaction hash;
- operator/admin id;
- timestamp and comment.

## Launch Position

The exchange desk is a controlled post-launch pilot. It can be used to observe utility demand and treasury turnover before considering any broader P2P, DEX, or listing strategy.
