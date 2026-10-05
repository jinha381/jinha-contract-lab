# 온체인 거래와 관리기록 정합성 검증 실험

「압수 가상자산의 온체인 거래와 관리기록 간 불일치 탐지를 위한 규칙 기반 상호 검증 모델」 연구용 실험 저장소입니다. Solana Localnet의 네이티브 SOL 이전 거래와 합성 관리기록을 사용합니다.

## 파일 구성과 동작 개요

| 파일 | 목적과 동작 |
| --- | --- |
| [`research/verify.py`](research/verify.py) | C/A/H/L/T 증거 JSON에 기본 비교 M1 또는 R0~R4 기반 M2를 적용하고 `PASS`·`FAIL`·`UNKNOWN` 및 사유를 반환하는 공통 검증기. |
| [`research/run_experiments.py`](research/run_experiments.py) | N1~N3, X1~X6, U1~U3 합성 사례와 A1~A5 제거 실험을 만들고 M1/M2 결과를 `research/results.json`에 출력. 실제 Localnet 관측값은 생성하지 않음. |
| [`research/run_n1.py`](research/run_n1.py) | 거래 없는 구간의 시작·종료 잔액/슬롯을 읽고, 종료 직후 서명 목록과 ledger 보관 범위로 자료 충분성을 확인. 송금하지 않음. |
| [`research/run_n2.py`](research/run_n2.py) | `prepare`에서 출금 승인 A/H를 거래 전에 저장하고, 사용자가 송금한 뒤 `finalize`에서 T·L·수수료·기말잔액과 관측 범위를 기록. 스크립트 자체는 송금하지 않음. |
| [`research/run_n3.py`](research/run_n3.py) | 정상 입금용 스크립트. `prepare`로 입금 전 잔액을 기록하고 `finalize`로 외부지갑의 입금 T와 확인기록 L을 수집. 문법 확인을 마쳤으며 Localnet 실측 검증은 아직 진행하지 않음. |
| [`research/capture_localnet.py`](research/capture_localnet.py) | 공개주소의 단일 System Program SOL 이전 거래를 범용으로 수집. 관측범위·잔액은 수동 보완이 필요해 `coverage_complete`를 자동으로 참으로 만들지 않음. |
| [`dashboard/server.py`](dashboard/server.py) | Localnet RPC와 증거 JSON을 읽는 localhost 전용 HTTP 서버. 상태·사례·지갑 조회 API를 제공하고 변경 요청은 거부. |
| [`dashboard/index.html`](dashboard/index.html), [`app.js`](dashboard/app.js), [`style.css`](dashboard/style.css) | 대시보드의 구조, 데이터 조회·표시, 화면 디자인을 각각 담당. 거래 전송 기능 없음. |
| [`research/examples/approved-withdrawal.json`](research/examples/approved-withdrawal.json) | 실제 체인 자료가 아닌 정상 출금 입력 형식의 예시. |

`research/evidence/*.json`은 Localnet 실측 증거, `research/results.json`은 합성 사례 실행 결과다. 두 경로는 Git에서 제외되므로 로컬에만 저장된다. 실험 지갑 키 파일도 저장소에 두지 않는다.

## 시작하기

Python 3.10 이상이 필요합니다. 합성 시나리오 12개와 제거 실험을 실행합니다.

```bash
python research/run_experiments.py
```

판정 결과는 `research/results.json`에 생성됩니다. Localnet 거래 수집, 증거 JSON 작성, M1/M2 비교 및 실험 한계는 [실험 안내](research/README.md)를 참고하세요.

## 로컬 대시보드

Localnet이 실행 중일 때 다음 명령을 실행한 뒤 브라우저에서 `http://127.0.0.1:8765`를 엽니다.

```bash
python dashboard/server.py --rpc http://127.0.0.1:18999
```

대시보드는 거래 전송 기능 없이 RPC의 슬롯·잔액·주소별 최근 거래와 `research/examples/*.json`, `research/evidence/*.json`의 증거·M1/M2·R0~R4 판정 결과를 보여줍니다. 기본 RPC 주소는 현재 연구용 Localnet의 `18999` 포트입니다. 다른 포트를 쓰면 `--rpc`를 바꾸세요. 웹 서버는 PC의 `127.0.0.1:8765`에만 열립니다. 종료는 실행 터미널에서 `Ctrl+C`입니다.
