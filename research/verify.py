"""Offline prototype for the paper's C/A/H/L/T consistency rules.

Input is a JSON evidence bundle, not a claim that RPC data is complete or trusted.
Amounts and fees are integer lamports; times are ISO 8601 UTC strings.
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path


def verdict(bundle, baseline=False, omit=()):
    c = bundle.get("C", {})
    approvals = bundle.get("A", [])
    history = bundle.get("H", [])
    logs = bundle.get("L", [])
    txs = bundle.get("T", [])
    omitted = set(omit)
    checks = {f"R{i}": "PASS" for i in range(5)}
    reasons = []

    def mark(rule, status, reason):
        if checks[rule] != "FAIL" or status == "FAIL":
            checks[rule] = status
        reasons.append({"rule": rule, "status": status, "detail": reason})

    required_c = ("case_id", "wallet", "asset", "start", "end", "opening", "closing")
    if any(k not in c for k in required_c) or not isinstance(txs, list):
        mark("R0", "UNKNOWN", "C or T is incomplete")
    if not baseline and (not bundle.get("coverage_complete", False) or bundle.get("rpc_error", False)):
        mark("R0", "UNKNOWN", "on-chain observation is incomplete")
    if checks["R0"] == "UNKNOWN":
        return {"verdict": "UNKNOWN", "checks": checks, "reasons": reasons}

    required_t = ("txid", "from", "to", "amount", "time", "status", "fee")
    if any(not isinstance(t, dict) or any(k not in t for k in required_t) for t in txs):
        mark("R0", "UNKNOWN", "transaction fields are incomplete")
    ids = [t["txid"] for t in txs if isinstance(t, dict) and "txid" in t]
    if len(ids) != len(set(ids)):
        mark("R0", "UNKNOWN", "duplicate transaction identifier")
    if checks["R0"] == "UNKNOWN":
        return {"verdict": "UNKNOWN", "checks": checks, "reasons": reasons}

    wallet = c["wallet"]
    outgoing = []
    for t in txs:
        if not (c["start"] <= t["time"] <= c["end"]) or t.get("asset", "SOL") != c["asset"]:
            mark("R1", "FAIL", f"transaction outside managed scope: {t['txid']}")
        if wallet not in (t["from"], t["to"]):
            mark("R1", "FAIL", f"unrelated transaction: {t['txid']}")
        if t["from"] == wallet and t["status"] == "success":
            outgoing.append(t)

    used = defaultdict(int)
    for t in sorted(outgoing, key=lambda x: (x["time"], x["txid"])):
        candidates = [a for a in approvals if a.get("recipient") == t["to"] and a.get("amount") == t["amount"]]
        linked = [l for l in logs if l.get("txid") == t["txid"]]
        explicit = {l.get("approval_id") for l in linked if l.get("approval_id")}
        if explicit:
            candidates = [a for a in candidates if a.get("id") in explicit]
        if len(candidates) > 1 and not baseline:
            mark("R0", "UNKNOWN", f"ambiguous approval for {t['txid']}")
            continue
        if not candidates:
            mark("R2", "FAIL", f"no matching approval for {t['txid']}")
            continue
        a = candidates[0]
        if not baseline:
            if not (a.get("valid_from", "") <= t["time"] <= a.get("valid_until", "")):
                mark("R2", "FAIL", f"approval expired or not yet valid: {a['id']}")
            if "use_limit" in omitted or "use_limit" not in a:
                mark("R0", "UNKNOWN", f"use limit unavailable: {a['id']}")
            else:
                used[a["id"]] += 1
                if used[a["id"]] > a["use_limit"]:
                    mark("R2", "FAIL", f"approval reused: {a['id']}")
            events = [h for h in history if h.get("approval_id") == a["id"] and h.get("time", "") <= t["time"]]
            if "H" in omitted or not events:
                mark("R0", "UNKNOWN", f"approval history unavailable: {a['id']}")
            elif max(events, key=lambda h: h["time"])["state"] != "active":
                mark("R2", "FAIL", f"approval inactive at execution: {a['id']}")

    if not baseline and "R3" not in omitted:
        tx_by_id = {t.get("txid"): t for t in txs}
        for t in txs:
            matches = [l for l in logs if l.get("txid") == t.get("txid")]
            if len(matches) == 0:
                mark("R3", "FAIL", f"execution log missing: {t.get('txid')}")
            elif len(matches) > 1:
                mark("R0", "UNKNOWN", f"multiple logs for {t.get('txid')}")
            elif matches[0].get("result") != t.get("status"):
                mark("R3", "FAIL", f"execution result differs: {t.get('txid')}")
        for log in logs:
            if log.get("txid") not in tx_by_id:
                mark("R3", "FAIL", f"logged transaction not observed: {log.get('txid')}")

    if not baseline:
        expected = c["opening"]
        for t in txs:
            if t.get("status") == "success":
                if t.get("to") == wallet:
                    expected += t["amount"]
                if t.get("from") == wallet:
                    expected -= t["amount"] + t["fee"]
            elif t.get("from") == wallet:
                expected -= t.get("fee", 0)
        if expected != c["closing"]:
            mark("R4", "FAIL", f"computed closing {expected}, recorded {c['closing']}")

    result = "UNKNOWN" if checks["R0"] == "UNKNOWN" else "FAIL" if "FAIL" in checks.values() else "PASS"
    return {"verdict": result, "checks": checks, "reasons": reasons}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--baseline", action="store_true", help="M1 basic approval conditions")
    parser.add_argument("--omit", action="append", choices=["H", "use_limit", "R3"])
    args = parser.parse_args()
    data = json.loads(args.evidence.read_text(encoding="utf-8"))
    print(json.dumps(verdict(data, args.baseline, args.omit or ()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
