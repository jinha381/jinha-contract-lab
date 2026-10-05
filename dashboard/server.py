"""Read-only local dashboard for Solana RPC and research evidence."""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "research"))
from verify import verdict  # noqa: E402

PUBKEY = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
STATIC = {"/": ("index.html", "text/html; charset=utf-8"), "/style.css": ("style.css", "text/css; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8")}


def evidence_files():
    files = {}
    for folder in (ROOT / "research" / "evidence", ROOT / "research" / "examples"):
        if folder.exists():
            for file in sorted(folder.glob("*.json")):
                files[f"{folder.name}/{file.name}"] = file
    return files


def rpc(url, method, params=None):
    data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}).encode()
    request = urllib.request.Request(url, data, {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=5) as response:
        answer = json.load(response)
    if "error" in answer:
        raise RuntimeError(str(answer["error"]))
    return answer.get("result")


def transaction_summary(detail, signature):
    if not detail:
        return {"signature": signature, "state": "unavailable", "transfers": []}
    meta = detail.get("meta") or {}
    message = (detail.get("transaction") or {}).get("message") or {}
    transfers = []
    for instruction in message.get("instructions", []):
        parsed = instruction.get("parsed") or {}
        if instruction.get("program") == "system" and parsed.get("type") == "transfer":
            info = parsed.get("info") or {}
            transfers.append({"from": info.get("source"), "to": info.get("destination"), "lamports": info.get("lamports")})
    return {"signature": signature, "slot": detail.get("slot"), "block_time": detail.get("blockTime"), "state": "failed" if meta.get("err") else "success", "fee": meta.get("fee"), "transfers": transfers, "instruction_count": len(message.get("instructions", []))}


class Handler(BaseHTTPRequestHandler):
    rpc_url = "http://127.0.0.1:18999"

    def send_json(self, value, code=200):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path in STATIC:
            name, content_type = STATIC[url.path]
            body = (ASSETS / name).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        try:
            query = parse_qs(url.query)
            if url.path == "/api/status":
                self.send_json({"rpc": self.rpc_url, "health": rpc(self.rpc_url, "getHealth"), "slot": rpc(self.rpc_url, "getSlot"), "block_height": rpc(self.rpc_url, "getBlockHeight"), "genesis_hash": rpc(self.rpc_url, "getGenesisHash")})
            elif url.path == "/api/cases":
                cases = []
                for case_id, file in evidence_files().items():
                    try:
                        data = json.loads(file.read_text(encoding="utf-8"))
                        cases.append({"id": case_id, "case_id": data.get("C", {}).get("case_id"), "wallet": data.get("C", {}).get("wallet"), "coverage_complete": data.get("coverage_complete", False), "transaction_count": len(data.get("T", []))})
                    except (OSError, ValueError, TypeError):
                        cases.append({"id": case_id, "error": "invalid evidence file"})
                self.send_json({"cases": cases})
            elif url.path == "/api/case":
                case_id = query.get("id", [""])[0]
                file = evidence_files().get(case_id)
                if file is None:
                    self.send_json({"error": "case not found"}, 404)
                    return
                data = json.loads(file.read_text(encoding="utf-8"))
                self.send_json({"id": case_id, "evidence": data, "M1": verdict(data, baseline=True), "M2": verdict(data)})
            elif url.path == "/api/wallet":
                address = query.get("address", [""])[0]
                if not PUBKEY.fullmatch(address):
                    self.send_json({"error": "invalid public address"}, 400)
                    return
                balance = rpc(self.rpc_url, "getBalance", [address, {"commitment": "finalized"}])
                signatures = rpc(self.rpc_url, "getSignaturesForAddress", [address, {"limit": 25, "commitment": "finalized"}])
                items = []
                for item in signatures:
                    detail = rpc(self.rpc_url, "getTransaction", [item["signature"], {"encoding": "jsonParsed", "commitment": "finalized", "maxSupportedTransactionVersion": 0}])
                    tx = transaction_summary(detail, item["signature"])
                    tx["block_time"] = tx.get("block_time") or item.get("blockTime")
                    items.append(tx)
                self.send_json({"address": address, "balance": balance.get("value"), "transactions": items, "limit": 25, "commitment": "finalized"})
            else:
                self.send_json({"error": "not found"}, 404)
        except (urllib.error.URLError, TimeoutError, RuntimeError) as error:
            self.send_json({"error": f"RPC unavailable: {error}"}, 503)
        except (OSError, ValueError, TypeError, KeyError) as error:
            self.send_json({"error": str(error)}, 422)

    def do_POST(self):
        self.send_json({"error": "read-only dashboard"}, 405)

    def log_message(self, format, *args):
        print("dashboard:", format % args)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rpc", default="http://127.0.0.1:18999", help="local Solana RPC")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    parsed = urlparse(args.rpc)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        parser.error("--rpc must be a local HTTP endpoint")
    Handler.rpc_url = args.rpc
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Research dashboard: http://127.0.0.1:{args.port} | RPC: {args.rpc}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
