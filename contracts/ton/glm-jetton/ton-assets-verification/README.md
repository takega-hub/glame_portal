# GLAME Coin Tonkeeper Verification

Tonkeeper may mark new Jettons as unverified/spam until the token is reviewed and added to the public `tonkeeper/ton-assets` asset list.

## Mainnet Jetton

- Name: `GLAME Coin`
- Symbol: `GLM`
- Master address: `EQBaHSwImRBl25rWgCpG1is_g_fByAt-dT36APLnywC7v2fl`
- Raw address for `ton-assets`: `0:5a1d2c08991065db9ad6802a46d62b3f83f7c1c80b7e753dfa00f2e7cb00bbbf`
- Partner site: `https://partner.glamejewelry.ru/referral`
- Metadata: `https://partner.glamejewelry.ru/static/glm_policy/jetton-metadata.json`
- Icon: `https://partner.glamejewelry.ru/static/glm_policy/glm-token-icon-v3.png`

## PR Steps

1. Fork `https://github.com/tonkeeper/ton-assets`.
2. In the fork, create `jettons/GLM.yaml`.
3. Copy the contents of `GLM.yaml` from this folder into that file.
4. Do not edit generated `jettons.json` directly; Tonkeeper generates it from YAML.
5. Run repository checks if available.
6. Open a pull request titled `Add GLAME Coin GLM jetton`.
7. Use the text from `PR_DESCRIPTION.md` as the pull request description.

## Notes

- This does not change balances or transactions.
- Wallet apps may cache token trust status, so the warning can remain visible until the asset-list PR is reviewed, merged, and propagated.
- Avoid bulk airdrops to unrelated wallets before verification; this can increase spam heuristics.
