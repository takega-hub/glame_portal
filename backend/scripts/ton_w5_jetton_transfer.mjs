import { createRequire } from "node:module";

const requireFromVendor = createRequire(
  new URL(
    "../../contracts/ton/glm-jetton/vendor/ton-blockchain-jetton-contract/package.json",
    import.meta.url,
  ),
);
const { mnemonicToPrivateKey } = requireFromVendor("@ton/crypto");
const {
  Address,
  beginCell,
  internal,
  JettonMaster,
  TonClient,
  WalletContractV5R1,
} = requireFromVendor("@ton/ton");

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => {
      data += chunk;
    });
    process.stdin.on("end", () => resolve(data));
    process.stdin.on("error", reject);
  });
}

function jsonRpcEndpoint(baseUrl, network) {
  const fallback =
    network === "mainnet"
      ? "https://toncenter.com/api/v2"
      : "https://testnet.toncenter.com/api/v2";
  const base = (baseUrl || fallback).replace(/\/$/, "");
  return base.endsWith("/jsonRPC") ? base : `${base}/jsonRPC`;
}

async function sleep(ms) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

async function withRetry(label, action) {
  let lastError;
  for (let attempt = 1; attempt <= 5; attempt += 1) {
    try {
      return await action();
    } catch (error) {
      lastError = error;
      const message = String(error?.message || error);
      const retryable =
        message.includes("429") ||
        message.includes("Too Many Requests") ||
        message.includes("ECONNRESET") ||
        message.includes("ETIMEDOUT");
      if (!retryable || attempt === 5) {
        break;
      }
      await sleep(1200 * attempt);
    }
  }
  throw new Error(`${label}: ${lastError?.message || lastError}`);
}

async function main() {
  const payload = JSON.parse(await readStdin());
  const network = payload.network || "testnet";
  const endpoint = jsonRpcEndpoint(payload.toncenterBaseUrl, network);
  const client = new TonClient({
    endpoint,
    apiKey: payload.apiKey || undefined,
  });

  const words = String(payload.mnemonic || "")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (words.length !== 24) {
    throw new Error("mnemonic must contain 24 words");
  }

  const keyPair = await mnemonicToPrivateKey(words);
  const wallet = WalletContractV5R1.create({
    workchain: 0,
    publicKey: keyPair.publicKey,
    walletId: network === "testnet" ? { networkGlobalId: -3 } : undefined,
  });
  const expected = payload.expectedWalletAddress
    ? Address.parse(payload.expectedWalletAddress)
    : null;
  if (expected && !wallet.address.equals(expected)) {
    throw new Error("W5 mnemonic does not match expected wallet address");
  }

  const openedWallet = client.open(wallet);
  const seqno = await withRetry("getSeqno", () => openedWallet.getSeqno());
  const master = client.open(
    JettonMaster.create(Address.parse(payload.jettonMasterAddress)),
  );
  const hotJettonWallet = await withRetry("getWalletAddress", () =>
    master.getWalletAddress(wallet.address),
  );
  const destination = Address.parse(payload.destinationWalletAddress);
  const queryId = BigInt(payload.queryId);
  const amountBaseUnits = BigInt(payload.amountBaseUnits);
  const txValueNanoton = BigInt(payload.txValueNanoton);
  const forwardNanoton = BigInt(payload.forwardNanoton || "1");

  const forwardPayload = beginCell()
    .storeUint(0, 32)
    .storeStringTail(payload.comment || "")
    .endCell();
  const transferBody = beginCell()
    .storeUint(0x0f8a7ea5, 32)
    .storeUint(queryId, 64)
    .storeCoins(amountBaseUnits)
    .storeAddress(destination)
    .storeAddress(wallet.address)
    .storeBit(0)
    .storeCoins(forwardNanoton)
    .storeBit(1)
    .storeRef(forwardPayload)
    .endCell();

  await withRetry("sendTransfer", () =>
    openedWallet.sendTransfer({
      secretKey: keyPair.secretKey,
      seqno,
      messages: [
        internal({
          to: hotJettonWallet,
          value: txValueNanoton,
          bounce: true,
          body: transferBody,
        }),
      ],
    }),
  );

  console.log(
    JSON.stringify({
      status: "sent",
      wallet_address: wallet.address.toString({ testOnly: network !== "mainnet" }),
      wallet_address_raw: wallet.address.toRawString(),
      hot_jetton_wallet_address: hotJettonWallet.toString({
        testOnly: network !== "mainnet",
      }),
      hot_jetton_wallet_raw: hotJettonWallet.toRawString(),
      seqno,
      query_id: queryId.toString(),
      endpoint,
    }),
  );
}

main().catch((error) => {
  console.error(JSON.stringify({ status: "error", error: error.message }));
  process.exit(1);
});
