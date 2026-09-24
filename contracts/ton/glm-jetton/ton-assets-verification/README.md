# GLAME Coin Tonkeeper Verification

Tonkeeper may mark new Jettons as unverified/spam until the token is reviewed and added to the public `tonkeeper/ton-assets` asset list.

## Mainnet Jetton

- Name: `GLAME Coin`
- Symbol: `GLM`
- Master address: `EQBaHSwImRBl25rWgCpG1is_g_fByAt-dT36APLnywC7v2fl`
- Raw address for `ton-assets`: `0:5a1d2c08991065db9ad6802a46d62b3f83f7c1c80b7e753dfa00f2e7cb00bbbf`
- GLM landing: `https://partner.glamejewelry.ru/glm`
- Partner site: `https://partner.glamejewelry.ru/referral`
- Metadata: `https://partner.glamejewelry.ru/static/glm_policy/jetton-metadata-mainnet-v2.json`
- Icon: `https://partner.glamejewelry.ru/static/glm_policy/glm-token-icon-v3.png`
- Metadata update tx: `/BG9GiyynGQOQNqZx48Fx9YKoBPdzoIULZYGGF7JV4c=`

## Submission Status

- Pull request: https://github.com/tonkeeper/ton-assets/pull/5779
- Status: merged; wallet/client cache propagation may still lag after merge.

## TonAPI Cache Note

On 2026-07-07 the GLM Jetton master content URI was updated on-chain to the production metadata URL above.
`get_jetton_data` confirms that the master content contains:

```text
https://partner.glamejewelry.ru/static/glm_policy/jetton-metadata-mainnet-v2.json
```

If Tonkeeper/TonAPI ever shows stale metadata again, request a TonAPI metadata refresh for:

```text
EQBaHSwImRBl25rWgCpG1is_g_fByAt-dT36APLnywC7v2fl
```

Suggested PR/support comment:

```text
GLM Jetton metadata was updated on-chain to the production metadata URL.
Master: EQBaHSwImRBl25rWgCpG1is_g_fByAt-dT36APLnywC7v2fl
Raw: 0:5a1d2c08991065db9ad6802a46d62b3f83f7c1c80b7e753dfa00f2e7cb00bbbf
Metadata: https://partner.glamejewelry.ru/static/glm_policy/jetton-metadata-mainnet-v2.json
Icon: https://partner.glamejewelry.ru/static/glm_policy/glm-token-icon-v3.png
Metadata update tx: /BG9GiyynGQOQNqZx48Fx9YKoBPdzoIULZYGGF7JV4c=
Please refresh TonAPI/Tonkeeper metadata cache for this Jetton.
```

## PR Steps

1. Run local validation:

   ```bash
   cd contracts/ton/glm-jetton
   npm run validate:ton-assets
   npm run validate:ton-assets:live
   ```

2. Fork `https://github.com/tonkeeper/ton-assets`.
3. In the fork, create `jettons/GLM.yaml`.
4. Copy the contents of `GLM.yaml` from this folder into that file.
5. Do not edit generated `jettons.json` directly; Tonkeeper generates it from YAML.
6. Run repository checks if available.
7. Open a pull request titled `Add GLAME Coin GLM jetton`.
8. Use the text from `PR_DESCRIPTION.md` as the pull request description.

## Ready Patch Flow

If you already forked `tonkeeper/ton-assets`, you can apply the prepared patch:

```bash
git clone https://github.com/<your-github-user>/ton-assets.git
cd ton-assets
git checkout -b add-glame-coin-glm
git am /path/to/glame-platform/contracts/ton/glm-jetton/ton-assets-verification/glame-ton-assets-pr.patch
git push origin add-glame-coin-glm
```

Then open a pull request from `<your-github-user>:add-glame-coin-glm` to `tonkeeper:main`.

If an API-based submission fails with `Resource not accessible by personal access token`, the token cannot create forks or open pull requests for `tonkeeper/ton-assets`. Use one of these options:

- fork `tonkeeper/ton-assets` manually in the GitHub UI and use the patch flow above;
- or use a classic GitHub PAT with `public_repo` scope;
- or use a fine-grained token that has access to the fork repository and permission to write contents and create pull requests.

## Upstream CI Precheck

The Tonkeeper repository currently runs `python3 generator.py` in CI. A local precheck can be done without committing generated files:

```bash
git clone --depth 1 https://github.com/tonkeeper/ton-assets.git /tmp/ton-assets-glm-check
cp contracts/ton/glm-jetton/ton-assets-verification/GLM.yaml /tmp/ton-assets-glm-check/jettons/GLM.yaml
cd /tmp/ton-assets-glm-check
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python generator.py
```

`generator.py` may update root generated files such as `jettons.json` locally. Do not include those files in the pull request; the upstream template asks PRs to change only source `.yaml` files.

## Notes

- This does not change balances or transactions.
- Wallet apps may cache token trust status, so the warning can remain visible until the asset-list PR is reviewed, merged, and propagated.
- Avoid bulk airdrops to unrelated wallets before verification; this can increase spam heuristics.
