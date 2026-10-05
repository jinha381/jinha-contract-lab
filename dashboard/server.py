"""Localnet RPC와 연구 증거 JSON을 함께 보여 주는 읽기 전용 웹 서버.

브라우저에는 정적 화면과 제한된 조회 API만 제공한다. RPC 대상과 웹 서버
바인딩 주소를 localhost로 제한하며 송금·파일 수정 API는 제공하지 않는다.
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# 실행 위치와 무관하게 저장소 루트·화면 파일의 절대경로를 계산한다.
ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "research"))
from verify import verdict  # noqa: E402

# 지갑 조회 API에는 Solana 공개주소 형태만 허용한다. STATIC은 노출할
# 화면 파일의 허용 목록으로, URL을 임의 파일 경로로 해석하지 않는다.
PUBKEY = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
STATIC = {"/": ("index.html", "text/html; charset=utf-8"), "/style.css": ("style.css", "text/css; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8")}


def evidence_files():
    """표시 가능한 증거 파일을 두 폴더의 JSON으로만 제한해 반환한다."""
    # evidence는 로컬 실험값(.gitignore), examples는 공개 샘플이다.
    files = {}
    for folder in (ROOT / "research" / "evidence", ROOT / "research" / "examples"):
        if folder.exists():
            for file in sorted(folder.glob("*.json")):
                files[f"{folder.name}/{file.name}"] = file
    return files


def rpc(url, method, params=None):
    """백엔드에서 Localnet JSON-RPC를 호출해 브라우저의 CORS를 피한다."""
    data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}).encode()
    request = urllib.request.Request(url, data, {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=5) as response:
        answer = json.load(response)
    if "error" in answer:
        raise RuntimeError(str(answer["error"]))
    return answer.get("result")


def transaction_summary(detail, signature):
    """RPC 거래 상세에서 화면에 필요한 네이티브 SOL 이전만 요약한다."""
    # 상세가 지워졌거나 아직 조회되지 않으면 추정값을 만들지 않는다.
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
    """정적 화면과 상태·사례·지갑 조회 API를 처리하는 HTTP 핸들러."""
    rpc_url = "http://127.0.0.1:18999"

    def send_json(self, value, code=200):
        """JSON 응답을 캐시 없이 보낸다. 새 증거/잔액은 새로고침 때 읽는다."""
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        """허용된 정적 파일 또는 네 가지 읽기 전용 API만 제공한다."""
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
                # 사용자가 준 id를 경로에 붙이지 않고 허용 파일 사전에서 찾는다.
                case_id = query.get("id", [""])[0]
                file = evidence_files().get(case_id)
                if file is None:
                    self.send_json({"error": "case not found"}, 404)
                    return
                data = json.loads(file.read_text(encoding="utf-8"))
                self.send_json({"id": case_id, "evidence": data, "M1": verdict(data, baseline=True), "M2": verdict(data)})
            elif url.path == "/api/wallet":
                # 최근 25개 서명만 보여 준다. 전체 관측구간의 완전성을
                # 이 목록으로 주장하지 않으며 연구 판정은 증거 JSON을 쓴다.
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
        """변경 요청은 거부해 대시보드가 거래를 만들거나 기록을 쓰지 못하게 한다."""
        self.send_json({"error": "read-only dashboard"}, 405)

    def log_message(self, format, *args):
        """접속 기록에 dashboard 접두어를 붙여 표준 출력에 남긴다."""
        print("dashboard:", format % args)


def main():
    """로컬 RPC만 허용하고 웹 서버도 127.0.0.1에만 바인딩한다."""
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
