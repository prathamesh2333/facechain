# FaceChain — Face Identification & Blockchain Verification

**HH Goa 2026 · Shortlisting Task 3**

A working end-to-end pipeline:

```
face scan  →  encode the face  →  search the live web & social media for it
           →  re-check every hit with the face encoder
           →  anchor the confirmed finding on a blockchain
           →  re-verify the evidence against the on-chain record
```

If the face turns out to be on **no** social platform and nowhere on the open
web, the app offers an **Add Face** button: the operator enrols the person
locally, that enrolment is anchored on chain as well, and every later scan of
that person matches instantly from the local index.

---

## What it actually does

| # | Stage | How |
|---|-------|-----|
| 1 | **Face detection & encoding** | YuNet detector + SFace 128-d encoder, both run through OpenCV's DNN module. No dlib, no CUDA, no heavyweight framework. |
| 2 | **Local index check** | The embedding is compared against every previously enrolled face (cosine similarity). |
| 3 | **Publish the frame** | The scanned image is uploaded to a throwaway public file host, because reverse-image-search back-ends need a URL they can fetch. |
| 4 | **Live web / social search** | Real reverse image search — SerpAPI → Google Lens, Yandex and Bing, plus key-free scraped fallbacks. If Google Lens can name the person, a second Google search restricted to `instagram.com`, `x.com`, `facebook.com`, `linkedin.com`, `youtube.com`, `threads.net` looks for their actual profile. |
| 5 | **Verification of every candidate** | Nothing is trusted because a search engine returned it. Each candidate image is downloaded, run back through the face encoder, and kept only if its cosine similarity to the query face clears the threshold. This is what stops a "looks similar" web result from being reported as an identification. |
| 6 | **Blockchain anchoring** | The whole finding is serialised to canonical JSON, hashed with keccak256, and written to a `FaceRegistry` smart contract. |
| 7 | **Re-verification** | The evidence file is re-hashed and looked up on chain. Change one byte of it and verification fails — there is a built-in tamper test that demonstrates exactly this. |

**No biometric data and no post content ever go on chain** — only keccak256
commitments. That is the whole point: the chain proves *what was found and
when*, without becoming a face database itself.

---

## Quick start

```bash
git clone <your repo url>
cd facechain

python -m venv .venv
# Windows:  .venv\Scripts\activate
source .venv/bin/activate

pip install -r requirements.txt
python scripts/download_models.py     # ~39 MB of ONNX models, one time
python scripts/fetch_samples.py       # a few sample faces (optional)

cp .env.example .env                  # Windows: copy .env.example .env
```

Then either run the web app:

```bash
python app.py          # http://127.0.0.1:5000
```

or the command line:

```bash
python run.py scan samples/person_a.jpg
```

Nothing else is required — the default `CHAIN_MODE=memory` runs a real EVM
in-process, so there is no node to start and no wallet to fund.

---

## The web app

`python app.py` → <http://127.0.0.1:5000>

* **Face scan** — capture from your webcam, or choose an image file.
* **Pipeline** — every stage streams live as it happens (server-sent events).
* **Result** — the detected face, the confirmed match, the post URL, the
  similarity score and the SHA-256 of the matched image.
* **Candidates** — the full table of everything the search engines returned,
  with the similarity the face encoder measured for each, so you can see the
  rejects as well as the hit.
* **Add face** — appears only when nothing was found. Name, handles, profile
  links; the enrolment is anchored on chain immediately.
* **Blockchain record** — contract, record id, record hash, tx hash, block,
  explorer link (testnet), plus **Re-verify** and **Tamper test** buttons.

---

## The command line

```bash
# full pipeline
python run.py scan samples/person_a.jpg
python run.py scan photo.jpg --chain local

# enrol a face the internet does not know
python run.py add-face photo.jpg --name "Asha Rao" \
    --handle "@asha" --link "https://instagram.com/asha"

python run.py list                                   # enrolled faces

# re-verify a stored finding against the chain
python run.py --chain local verify data/evidence/<file>.json

# prove it is tamper-evident: corrupt one field, verification must fail
python run.py --chain local verify data/evidence/<file>.json --tamper

python run.py --chain local chain-info
python run.py --chain local deploy
python scripts/selftest.py --chain local             # end-to-end self test
```

---

## Which blockchain

The same Solidity contract (`contracts/FaceRegistry.sol`, solc 0.8.20) runs on
all three back-ends. Pick one with `CHAIN_MODE` in `.env`, or `--chain` on the
command line.

| `CHAIN_MODE` | What it is | Setup | Persists between runs |
|---|---|---|---|
| `memory` *(default)* | A real EVM running in-process via `eth-tester` / `py-evm`. | none | no |
| `local` | Any local Ethereum JSON-RPC node — Hardhat, Anvil or Ganache — at `RPC_URL`. | one command, see below | **yes** |
| `testnet` | A public testnet. Default config is **Polygon Amoy** with Polygonscan explorer links. | test wallet + free faucet MATIC | **yes** |

For a demo where you anchor a record and re-verify it in a *later* run, use
`local` or `testnet`.

### Local node (persistent, free)

```bash
npm install && npx hardhat node      # or:  npx ganache --port 8545   /   anvil
```

Then set `CHAIN_MODE=local` in `.env`. Local nodes unlock funded dev accounts,
so no `PRIVATE_KEY` is needed. More detail in `scripts/local_node.md`.

### Public testnet

```env
CHAIN_MODE=testnet
TESTNET_RPC_URL=https://rpc-amoy.polygon.technology
EXPLORER_TX_URL=https://amoy.polygonscan.com/tx/
PRIVATE_KEY=0x...          # a throwaway test wallet, funded from a faucet
```

Never put a key that holds real money in `.env`.

### The contract

```solidity
function anchor(bytes32 recordHash, bytes32 faceHash,
                string sourceUrl, string platform) returns (uint256 id);

function verify(bytes32 recordHash)
    returns (bool exists, uint256 id, Record record);

function recordsForFace(bytes32 faceHash) returns (uint256[]);
function getRecord(uint256 id) returns (Record);
function total() returns (uint256);
```

`recordHash` is `keccak256` of the canonical JSON of the evidence file.
`faceHash` is `sha256` of the L2-normalised, 3-decimal-quantised embedding —
a stable commitment to the face that cannot be inverted back into a photo.
Re-anchoring an identical record reverts with `AlreadyAnchored`, so duplicates
cannot quietly overwrite history.

---

## Configuration

Everything lives in `.env` (see `.env.example`). The only entry worth setting
up properly is the search key:

```env
SERPAPI_KEY=            # https://serpapi.com/manage-api-key — free tier: 100 searches/month
CHAIN_MODE=memory       # memory | local | testnet
MATCH_THRESHOLD=0.363   # SFace's published cosine operating point
WEB_MATCH_THRESHOLD=0.40  # stricter bar before a web hit counts as an identification
```

Without a SerpAPI key the pipeline still runs, using key-free scraped engines —
but see the limitations below.

---

## Project layout

```
facechain/
  face.py        YuNet detection + SFace embeddings, face hashing
  search.py      reverse image search back-ends, candidate model, page scraping
  imghost.py     publishes the scanned frame to a temporary public URL
  localdb.py     the "Add Face" store
  chain.py       solc compilation, three chain back-ends, anchor + verify
  pipeline.py    the end-to-end orchestration
  config.py      all settings
contracts/FaceRegistry.sol
scripts/         download_models.py, fetch_samples.py, selftest.py, local_node.md
templates/       the web UI
app.py           Flask app
run.py           command line
data/evidence/   one JSON evidence file per scan — this is what gets hashed
```

---

## Known limitations

* **Face search on the open web is genuinely hard.** Google, Bing and Meta all
  deliberately suppress face-based lookups, and Instagram/Facebook block
  automated access to post pages. In practice the pipeline identifies people
  who have a public web footprint (public figures, public profiles, indexed
  photos) far more reliably than private individuals — which is the correct
  and safer behaviour, and precisely why the **Add Face** path exists.
* **Without a SerpAPI key** the key-free fallbacks are best-effort scraping.
  They break whenever Yandex or Bing change their markup, and they are not
  true visual search, so they return far weaker candidates. Use a key for the
  demo.
* **The temporary image host is a third party.** The scanned frame is uploaded
  to a public throwaway host (litterbox / x0.at / uguu) so search engines can
  fetch it. Do not scan anything sensitive.
* **SFace is a good, small model, not a state-of-the-art one.** At the 0.363
  operating point it is strong on frontal, reasonably lit faces; heavy pose,
  motion blur, masks or very low resolution will cost accuracy. Only the
  largest face in a frame is used as the query.
* **`memory` chain state disappears** when the process exits, so a finding
  anchored in one run cannot be re-verified in the next. Use `local` or
  `testnet` for that.
* **Testnet costs test gas.** If the faucet balance runs out, anchoring fails
  and the pipeline reports it rather than pretending it succeeded.
* **The chain proves integrity, not truth.** It proves that this exact finding
  existed at this time and has not been altered since. It does not prove the
  face match was correct — that is what the similarity score and the raw
  candidate table are there for.

## Ethics

This is a shortlisting exercise built around publicly available data. Face
search against real people has obvious potential for misuse; the pipeline is
deliberately built so that nothing biometric is published, every match is
shown with the score behind it, and unverified search hits are never reported
as identifications.

---

## Credits

* [OpenCV Zoo](https://github.com/opencv/opencv_zoo) — YuNet and SFace models
* [web3.py](https://web3py.readthedocs.io/), [py-solc-x](https://github.com/ApeWorX/py-solc-x), [eth-tester](https://github.com/ethereum/eth-tester)
* [SerpAPI](https://serpapi.com/) — Google Lens / Yandex / Bing search access

MIT licensed.
