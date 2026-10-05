# 온체인 거래와 관리기록 정합성 검증 실험

「압수 가상자산의 온체인 거래와 관리기록 간 불일치 탐지를 위한 규칙 기반 상호 검증 모델」 연구용 실험 저장소입니다. Solana Localnet의 네이티브 SOL 이전 거래와 합성 관리기록을 사용합니다.

## 시작하기

Python 3.10 이상이 필요합니다. 합성 시나리오 12개와 제거 실험을 실행합니다.

```bash
python research/run_experiments.py
```

판정 결과는 `research/results.json`에 생성됩니다. Localnet 거래 수집, 증거 JSON 작성, M1/M2 비교 및 실험 한계는 [실험 안내](research/README.md)를 참고하세요.
