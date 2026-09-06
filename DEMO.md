# Screen recording script

A plain, unedited screen recording is all the submission asks for. This is the
shortest path that shows every required stage working. Budget 3–5 minutes.

## Before you hit record

```bash
cp .env.example .env
```

Put your SerpAPI key in `.env` and set:

```env
SERPAPI_KEY=your_key_here
CHAIN_MODE=local
```

Start the local chain in its own terminal and leave it running:

```bash
npx hardhat node        # or: npx ganache --port 8545
```

Then, in a second terminal:

```bash
python scripts/download_models.py
python run.py --chain local deploy
```

Have ready:

* **Photo A** — someone with a real public web presence (a public figure, or
  your own photo if your Instagram/LinkedIn profile picture is public). This is
  the "found on social media" demo.
* **Photo B** — a face with no public web footprint. This is the "Add Face"
  demo.

## Record this

**1. Show the contract is live (10 s)**

```bash
python run.py --chain local chain-info
```

Point at the chain id, contract address and record count.

**2. Web app, the found case (90 s)**

```bash
python app.py
```

Open <http://127.0.0.1:5000>. Choose Photo A (or capture from the webcam) and
press **Run pipeline**. Narrate the stages as they stream in:

* face detected and encoded
* frame published to a public URL
* reverse image search running across live engines
* each candidate downloaded and re-checked with the face encoder
* the confirmed match, with its similarity score and post URL
* the finding anchored on chain — read out the tx hash and block number
* the re-verification going green

Scroll down to the **candidates** table and point out the results that were
returned by the search engine but *rejected* by the face check. That is the
evidence that the search step is real and not a hardcoded answer.

**3. Tamper test (20 s)**

In the Blockchain panel, press **Re-verify against chain** → verified. Then
press **Tamper test** → not verified. Say the line out loud: one byte changes,
the hash changes, the chain no longer recognises it.

**4. The Add Face case (60 s)**

Press **Reset**, choose Photo B, **Run pipeline**. It ends with *not found on
any social platform or the open web* and the **Add Face** panel appears. Fill
in a name and a handle, press **Add face & anchor on chain**, show the tx hash.

Press **Reset**, choose Photo B again, **Run pipeline** — this time it is
identified from the local index and that identification is anchored too.

**5. Re-verify from a cold start (30 s)**

Back in the terminal — a fresh process, nothing cached:

```bash
python run.py list
ls data/evidence
python run.py --chain local verify data/evidence/<the-file>.json
python run.py --chain local verify data/evidence/<the-file>.json --tamper
```

Verified, then deliberately failed. That closes the loop.

**Optional (30 s)** — if you set `CHAIN_MODE=testnet` with a funded test
wallet, run one scan on Polygon Amoy and open the Polygonscan link the app
prints, so the record is visible on a public explorer.

## If the search step returns nothing on the day

Say so on camera and run:

```bash
python scripts/selftest.py --chain local
```

It proves the encoder, the candidate-verification stage, the anchoring and the
tamper detection all work, independently of whether a search API is in credit.
