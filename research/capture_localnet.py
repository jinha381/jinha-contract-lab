"""Capture parsed native SOL transfers for one custody address from local RPC.

This is an evidence collection aid. Review coverage, opening/closing balances,
and all signatures before setting coverage_complete in the output JSON.
"""

import argparse
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("wallet")
    p.add_argument("--rpc", default="http://127.0.0.1:8899")
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--output", type=Path, default=Path("research/localnet-evidence.json"))
    args = p.parse_args()
    counter = 0

    def rpc(method, params):
        nonlocal counter
        counter += 1
        body = json.dumps({"jsonrpc": "2.0", "id": counter, "method": method, "params": params}).encode()
        with urllib.request.urlopen(urllib.request.Request(args.rpc, body, {"Content-Type": "application/json"}), timeout=15) as response:
            result = json.load(response)
        if "error" in result:
            raise RuntimeError(result["error"])
        return result["result"]

    signatures = rpc("getSignaturesForAddress", [args.wallet, {"limit": args.limit}])
    transfers = []
    skipped = []
    for item in reversed(signatures):
        detail = rpc("getTransaction", [item["signature"], {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])
        if detail is None or item.get("blockTime") is None:
            skipped.append(item["signature"])
            continue
        instructions = detail["transaction"]["message"]["instructions"]
        native = [ix for ix in instructions if ix.get("program") == "system" and ix.get("parsed", {}).get("type") == "transfer"]
        if len(native) != 1 or len(instructions) != 1:
            skipped.append(item["signature"])
            continue
        info = native[0]["parsed"]["info"]
        transfers.append({"txid": item["signature"], "from": info["source"], "to": info["destination"], "amount": info["lamports"], "time": datetime.fromtimestamp(item["blockTime"], timezone.utc).isoformat().replace("+00:00", "Z"), "status": "failed" if detail["meta"]["err"] else "success", "fee": detail["meta"]["fee"] if info["source"] == args.wallet else 0, "asset": "SOL"})
    evidence = {"C": {"case_id": "EDIT_ME", "wallet": args.wallet, "asset": "SOL", "start": "EDIT_ME", "end": "EDIT_ME", "opening": 0, "closing": 0}, "A": [], "H": [], "L": [], "T": transfers, "coverage_complete": False, "capture": {"rpc": args.rpc, "signature_count": len(signatures), "limit": args.limit, "skipped_signatures": skipped}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"captured {len(transfers)} transfers; skipped {len(skipped)} signatures; review {args.output}")


if __name__ == "__main__":
    main()
