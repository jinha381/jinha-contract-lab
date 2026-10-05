"""Run the paper's controlled scenarios and ablations without dependencies."""

import copy
import json
from pathlib import Path

from verify import verdict


def base():
    return {"C": {"case_id": "case-001", "wallet": "custody", "asset": "SOL", "start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z", "opening": 100000, "closing": 100000}, "A": [], "H": [], "L": [], "T": [], "coverage_complete": True}


def tx(txid="tx1", src="custody", dst="recipient", amount=1000, time="2026-01-01T12:00:00Z"):
    return {"txid": txid, "from": src, "to": dst, "amount": amount, "time": time, "status": "success", "fee": 10 if src == "custody" else 0, "asset": "SOL"}


def approved():
    b = base()
    b["T"] = [tx()]
    b["C"]["closing"] = 98990
    b["A"] = [{"id": "a1", "amount": 1000, "recipient": "recipient", "valid_from": "2026-01-01T00:00:00Z", "valid_until": "2026-01-02T00:00:00Z", "use_limit": 1}]
    b["H"] = [{"approval_id": "a1", "state": "active", "time": "2026-01-01T00:00:00Z"}]
    b["L"] = [{"id": "l1", "approval_id": "a1", "txid": "tx1", "result": "success", "time": "2026-01-01T12:01:00Z"}]
    return b


def cases():
    n1 = base()
    n2 = approved()
    n3 = base(); n3["T"] = [tx(src="outside", dst="custody")]; n3["L"] = [{"id": "l1", "txid": "tx1", "result": "success"}]; n3["C"]["closing"] = 101000
    x1 = approved(); x1["A"] = []; x1["H"] = []
    x2 = approved(); x2["A"][0]["amount"] = 999
    x3 = approved(); x3["H"].append({"approval_id": "a1", "state": "cancelled", "time": "2026-01-01T11:00:00Z"})
    x4 = approved(); x4["T"].append(tx("tx2", time="2026-01-01T13:00:00Z")); x4["L"].append({"id": "l2", "approval_id": "a1", "txid": "tx2", "result": "success"}); x4["C"]["closing"] = 97980
    x5 = approved(); x5["L"][0]["result"] = "failed"
    x6 = base(); x6["T"] = [tx(), tx("tx2", "outside", "custody", 1010, "2026-01-01T13:00:00Z")]; x6["L"] = [{"id": "l1", "txid": "tx1", "result": "success"}, {"id": "l2", "txid": "tx2", "result": "success"}]
    u1 = approved(); u1["coverage_complete"] = False
    u2 = approved(); u2["A"].append({**u2["A"][0], "id": "a2"}); u2["H"].append({"approval_id": "a2", "state": "active", "time": "2026-01-01T00:00:00Z"}); u2["L"][0].pop("approval_id")
    u3 = approved(); u3["H"] = []
    return {"N1": (n1, "PASS"), "N2": (n2, "PASS"), "N3": (n3, "PASS"), "X1": (x1, "FAIL"), "X2": (x2, "FAIL"), "X3": (x3, "FAIL"), "X4": (x4, "FAIL"), "X5": (x5, "FAIL"), "X6": (x6, "FAIL"), "U1": (u1, "UNKNOWN"), "U2": (u2, "UNKNOWN"), "U3": (u3, "UNKNOWN")}


def run():
    rows = []
    for name, (data, expected) in cases().items():
        m1, m2 = verdict(data, True), verdict(data)
        rows.append({"id": name, "expected": expected, "M1": m1["verdict"], "M2": m2["verdict"], "checks": m2["checks"], "reasons": m2["reasons"]})
    ablations = {}
    for label, name, omit in [("A1", "X3", ["H"]), ("A2", "X4", ["use_limit"]), ("A3", "X5", ["R3"])]:
        data = copy.deepcopy(cases()[name][0])
        ablations[label] = {"case": name, "original": verdict(data)["verdict"], "ablated": verdict(data, omit=omit)["verdict"]}
    connected = approved()
    connected["A"].append({**connected["A"][0], "id": "a2"})
    connected["H"].append({"approval_id": "a2", "state": "active", "time": "2026-01-01T00:00:00Z"})
    disconnected = copy.deepcopy(connected)
    disconnected["L"][0].pop("approval_id")
    ablations["A4"] = {"case": "two_matching_approvals", "original": verdict(connected)["verdict"], "ablated": verdict(disconnected)["verdict"]}
    unknown_cases = [row for row in rows if row["expected"] == "UNKNOWN"]
    ablations["A5a"] = {"cases": [row["id"] for row in unknown_cases], "forced": "PASS", "unsupported_decisions": len(unknown_cases)}
    ablations["A5b"] = {"cases": [row["id"] for row in unknown_cases], "forced": "FAIL", "unsupported_decisions": len(unknown_cases)}
    output = {"source": "synthetic evidence; not Solana Localnet observations", "cases": rows, "ablations": ablations}
    path = Path(__file__).parent / "results.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path}")
    for row in rows:
        print(f"{row['id']:>2} expected={row['expected']:<7} M1={row['M1']:<7} M2={row['M2']}")
    if any(r["expected"] != r["M2"] for r in rows):
        raise SystemExit("M2 differs from predeclared expectations")


if __name__ == "__main__":
    run()
