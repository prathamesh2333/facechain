#!/usr/bin/env python3
"""FaceChain command line runner.

Examples
--------
  python run.py scan samples/person.jpg
  python run.py scan samples/person.jpg --chain local
  python run.py add-face samples/person.jpg --name "Asha R" --handle @asha --link https://instagram.com/asha
  python run.py list
  python run.py verify data/evidence/20260906-101500-ab12cd.json
  python run.py verify data/evidence/20260906-101500-ab12cd.json --tamper
  python run.py chain-info
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

from facechain import config
from facechain.chain import Blockchain
from facechain.pipeline import Pipeline

BOLD, DIM, GREEN, RED, YELLOW, CYAN, RESET = (
    "\033[1m", "\033[2m", "\033[92m", "\033[91m", "\033[93m", "\033[96m", "\033[0m"
)


def banner(text: str) -> None:
    print(f"\n{BOLD}{CYAN}== {text}{RESET}")


def progress(step: str, message: str, extra: dict) -> None:
    print(f"  {DIM}[{step:<8}]{RESET} {message}")


# --------------------------------------------------------------------------
def cmd_scan(args) -> int:
    path = Path(args.image)
    if not path.exists():
        print(f"{RED}No such image: {path}{RESET}")
        return 1
    data = path.read_bytes()

    banner(f"FaceChain scan - {path.name}")
    pipe = Pipeline(chain_mode=args.chain)
    if pipe.chain is not None:
        info = pipe.chain.info()
        print(f"  {DIM}chain: {info['mode']} (chainId {info['chain_id']}) "
              f"contract {info['contract']}{RESET}")
    elif pipe.chain_error:
        print(f"  {YELLOW}chain unavailable: {pipe.chain_error}{RESET}")

    result = pipe.scan(data, on_progress=progress, anchor=not args.no_anchor)

    banner("Result")
    colour = {"matched": GREEN, "matched_local": GREEN,
              "not_found": YELLOW, "no_face": RED}.get(result.status, "")
    print(f"  status : {colour}{result.status}{RESET}")
    print(f"  detail : {result.message}")
    if result.identity_guess:
        print(f"  name   : {result.identity_guess}")

    if result.match:
        m = result.match
        print(f"\n  {BOLD}Matched post{RESET}")
        print(f"    platform   : {m['platform']}  ({m['source']})")
        print(f"    url        : {m['page_url']}")
        print(f"    image      : {m['image_url']}")
        print(f"    similarity : {m['similarity']}")
        print(f"    found by   : {m['engine']}")
        print(f"    img sha256 : {m['image_sha256'][:32]}...")

    verified = [c for c in result.candidates if c["verified"]]
    if result.candidates:
        print(f"\n  {len(result.candidates)} candidates checked, {len(verified)} face-verified")
        for c in result.candidates[:8]:
            mark = f"{GREEN}MATCH{RESET}" if c["verified"] else f"{DIM}  -  {RESET}"
            print(f"    {mark} {c['similarity']:.3f}  {c['platform']:<10} {c['page_url'][:66]}")

    if result.anchor and "error" not in result.anchor:
        a = result.anchor
        print(f"\n  {BOLD}Blockchain{RESET}")
        print(f"    chain      : {a['chain_mode']} (chainId {a['chain_id']})")
        print(f"    contract   : {a['contract']}")
        print(f"    record id  : {a['record_id']}")
        print(f"    recordHash : {a['record_hash']}")
        print(f"    tx         : {a['tx_hash']}  block {a['block_number']}")
        if a.get("explorer_url"):
            print(f"    explorer   : {a['explorer_url']}")
    elif result.anchor:
        print(f"\n  {YELLOW}Blockchain: {result.anchor['error']}{RESET}")

    if result.verification:
        ok = result.verification["verified"]
        print(f"\n  {BOLD}Re-verification{RESET}: "
              f"{GREEN + 'VERIFIED - evidence matches the on-chain record' + RESET if ok else RED + 'FAILED' + RESET}")

    print(f"\n  evidence: {result.evidence_file}")
    if result.status == "not_found":
        print(f"\n  {YELLOW}This face is not on any social platform we could reach.{RESET}")
        print(f"  Enrol it with:\n    python run.py add-face {path} --name \"Their Name\"")
    return 0


def cmd_add_face(args) -> int:
    path = Path(args.image)
    if not path.exists():
        print(f"{RED}No such image: {path}{RESET}")
        return 1
    banner(f"Add face - {args.name}")
    pipe = Pipeline(chain_mode=args.chain)
    out = pipe.add_face(path.read_bytes(), name=args.name,
                        handles=args.handle, links=args.link, notes=args.notes or "")
    if not out.get("ok"):
        print(f"{RED}{out.get('error')}{RESET}")
        return 1
    e = out["entry"]
    print(f"  enrolled   : {e['name']} (id {e['id']})")
    print(f"  handles    : {', '.join(e['handles']) or '-'}")
    print(f"  links      : {', '.join(e['links']) or '-'}")
    print(f"  face hash  : {e['face_hash'][:32]}...")
    a = out.get("anchor") or {}
    if "error" in a:
        print(f"  {YELLOW}chain: {a['error']}{RESET}")
    else:
        print(f"  anchored   : record #{a['record_id']} tx {a['tx_hash'][:20]}... "
              f"block {a['block_number']}")
        if a.get("explorer_url"):
            print(f"  explorer   : {a['explorer_url']}")
        v = out.get("verification") or {}
        print(f"  re-verify  : {GREEN + 'VERIFIED' + RESET if v.get('verified') else RED + 'FAILED' + RESET}")
    print(f"  evidence   : {out['evidence_file']}")
    return 0


def cmd_list(args) -> int:
    from facechain.localdb import LocalFaceDB
    db = LocalFaceDB()
    banner(f"Enrolled faces ({len(db)})")
    for e in db.all():
        anchored = "on-chain" if e.anchor and "error" not in e.anchor else "not anchored"
        print(f"  {e.id}  {e.name:<24} {', '.join(e.handles) or '-':<22} [{anchored}]")
    if not len(db):
        print("  (none yet - run: python run.py add-face <image> --name \"...\")")
    return 0


def cmd_verify(args) -> int:
    path = Path(args.evidence)
    if not path.exists():
        print(f"{RED}No such evidence file: {path}{RESET}")
        return 1
    banner(f"Re-verify against the chain - {path.name}")
    data = json.loads(path.read_text(encoding="utf-8"))
    record = data.get("record")
    if record is None:
        print(f"{RED}This file has no record block.{RESET}")
        return 1

    if args.tamper:
        record = copy.deepcopy(record)
        target = record.get("matched_post") or record.get("enrollment") or record["query"]
        key = next(iter(target))
        old = target[key]
        target[key] = f"{old}-TAMPERED"
        print(f"  {YELLOW}Tamper test: changed '{key}' in the evidence.{RESET}")

    chain = Blockchain(args.chain)
    try:
        chain.connect_contract(deploy_if_missing=False)
    except Exception as exc:  # noqa: BLE001
        print(f"{RED}{exc}{RESET}")
        print(f"{DIM}Tip: 'memory' mode resets each run - use --chain local with a node "
              f"for verification across runs.{RESET}")
        return 1

    out = chain.verify(record)
    print(f"  chain          : {out['chain_mode']} (chainId {out['chain_id']})")
    print(f"  contract       : {out['contract']}")
    print(f"  recomputed hash: {out['recomputed_hash']}")
    if out["verified"]:
        oc = out["on_chain"]
        print(f"\n  {GREEN}{BOLD}VERIFIED{RESET} - this exact evidence is anchored on chain")
        print(f"    record id : {out['record_id']}")
        print(f"    source    : {oc['sourceUrl'] or '-'}")
        print(f"    platform  : {oc['platform']}")
        print(f"    anchored  : {oc['timestamp']} by {oc['submitter']}")
        return 0
    print(f"\n  {RED}{BOLD}NOT VERIFIED{RESET} - no record with this hash exists on chain")
    if args.tamper:
        print(f"  {GREEN}(expected - the tamper test proves the record is tamper-evident){RESET}")
    return 0 if args.tamper else 2


def cmd_chain_info(args) -> int:
    banner("Chain info")
    chain = Blockchain(args.chain)
    chain.connect_contract()
    info = chain.info()
    for k, v in info.items():
        print(f"  {k:<10}: {v}")
    print(f"  {'records':<10}: {chain.total()}")
    if config.DEPLOYMENTS_FILE.exists():
        print(f"\n  deployments file: {config.DEPLOYMENTS_FILE}")
        print("  " + config.DEPLOYMENTS_FILE.read_text(encoding="utf-8").replace("\n", "\n  "))
    return 0


def cmd_deploy(args) -> int:
    banner("Deploy FaceRegistry")
    chain = Blockchain(args.chain)
    addr = chain.deploy()
    print(f"  chain    : {chain.mode} (chainId {chain.chain_id})")
    print(f"  deployer : {chain.account}")
    print(f"  address  : {GREEN}{addr}{RESET}")
    print(f"  saved to : {config.DEPLOYMENTS_FILE}")
    return 0


# --------------------------------------------------------------------------
def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="run.py", description="FaceChain - face identification + blockchain verification")
    p.add_argument("--chain", choices=["memory", "local", "testnet"], default=None,
                   help="which chain back-end to use (default: CHAIN_MODE from .env)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="run the full pipeline on an image")
    s.add_argument("image")
    s.add_argument("--no-anchor", action="store_true", help="skip the blockchain step")
    s.set_defaults(func=cmd_scan)

    s = sub.add_parser("add-face", help="enrol a face that the web does not know")
    s.add_argument("image")
    s.add_argument("--name", required=True)
    s.add_argument("--handle", action="append", default=[])
    s.add_argument("--link", action="append", default=[])
    s.add_argument("--notes", default="")
    s.set_defaults(func=cmd_add_face)

    s = sub.add_parser("list", help="list enrolled faces")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("verify", help="re-verify an evidence file against the chain")
    s.add_argument("evidence")
    s.add_argument("--tamper", action="store_true",
                   help="deliberately corrupt one field first - verification must fail")
    s.set_defaults(func=cmd_verify)

    s = sub.add_parser("chain-info", help="show chain / contract status")
    s.set_defaults(func=cmd_chain_info)

    s = sub.add_parser("deploy", help="deploy a fresh FaceRegistry contract")
    s.set_defaults(func=cmd_deploy)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
