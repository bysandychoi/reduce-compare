# Reduce & Compare

대규모 표 데이터(CSV 폴더)를 대표 샘플로 축소하고, 원본과의 유사도를 지표와 그래프로 확인하는 로컬 웹 도구.
지금은 **요구사항·백로그·작업 규칙(훅, 서브에이전트)** 까지 준비된 상태이고, 코드는 백로그 순서대로 만들어 갑니다.

## 폴더 구조

```
reduce-compare/
├── README.md               ← 지금 보는 파일
├── CLAUDE.md               ← Claude Code 작업 규칙 (자동으로 읽힘)
├── problem.md              ← 요구사항 문서
├── backlog.json            ← 작업 목록 (직접 수정 금지, CLI로만)
├── backlog.py              ← 백로그 CLI
├── backend/                ← Python 백엔드 (T011에서 FastAPI 초기화)
│   ├── app/api/            ← API 라우터
│   ├── app/core/           ← 축소·지표 계산 모듈
│   └── tests/
├── frontend/               ← 화면 (T012에서 Vite + React 초기화)
│   └── src/
├── scripts/                ← 샘플 데이터 생성 등 보조 스크립트
├── sample_data/            ← 테스트용 CSV (내용은 git에 올리지 않음)
├── docs/
│   └── tasks/              ← 태스크별 안내서(<ID>.md)와 리뷰(<ID>.review.md)가 쌓이는 곳
├── .claude/                ← Claude Code 설정 (숨김 폴더)
│   ├── settings.json       ← 훅 등록
│   ├── agents/             ← 서브에이전트: task-briefer(haiku), adversarial-reviewer(opus)
│   ├── rules/              ← 태스크 진행·서브에이전트 사용 규칙
│   └── hooks/              ← 훅 스크립트와 설정(config.json: 줄 수 한도, lint/build 명령)
├── .vscode/                ← VS Code 추천 확장·설정
└── .gitignore
```

폴더 뼈대만 만들어 둔 상태입니다. 실제 코드는 백로그 순서대로 채웁니다 (T011 백엔드, T012 프론트엔드).
`sample_data/`의 CSV와 모든 `*.csv`, `*.parquet`는 `.gitignore`로 제외돼 저장소에 올라가지 않습니다.

> macOS Finder에서는 `.claude`, `.vscode`, `.gitignore`가 숨김 파일이라 안 보입니다 (`Cmd + Shift + .` 로 표시).
> VS Code 탐색기에서는 그대로 보입니다.

## 바로 써 보기 (웹 화면 없이)

축소 결과만 확인하려면 이 명령 하나면 됩니다.

```bash
pip install pandas numpy scikit-learn scipy matplotlib
python3 scripts/run_reduce.py <데이터 폴더>              # 결과는 results/ 에 저장
python3 scripts/run_reduce.py <폴더> --inspect           # 컬럼 판별 결과만 확인
python3 scripts/run_reduce.py <폴더> --exclude memo,code # 기준 컬럼에서 빼기
python3 scripts/run_reduce.py <폴더> --columns a,b,c     # 기준 컬럼 직접 지정
python3 scripts/run_reduce.py <폴더> --max-missing 0.2   # 결측 20% 넘는 컬럼 자동 제외
python3 scripts/run_reduce.py <폴더> --target 90 --out 결과폴더
```

출력물:
- 화면: 그룹별 원본·축소 행 수, 종합 유사도(분포·상관·구조), 추천 방식, 크기별 점수
- `results/reduced_<그룹>.csv` — 축소본 (첫 컬럼 `_weight` = 그 행이 대표하는 원본 행 수)
- `results/report_<그룹>.json` — 지표 상세
- `results/compare_<그룹>.png` — 축소 전·후 비교 그림

읽는 파일: `.csv`, `.tsv`, 구분자 텍스트 `.txt` (구분자와 인코딩 자동 감지). 표가 아닌 txt는 건너뜁니다.

시험용 데이터가 필요하면: `python3 scripts/make_sample_data.py --rows 100000 --out sample_data/sales`

## 행이 묶여 있는 데이터 (lot-공정 이력 등)

한 단위(예: lot+공정)가 여러 행을 갖고, 그 행들이 흩어지면 안 되는 데이터는 이 스크립트를 씁니다.

```bash
python3 scripts/run_reduce_units.py "폴더" \
    --unit lot_id,step_id,proc_id,proc_ver \
    --strata step_id,proc_id,proc_ver,lot_floor \
    --combo eqp_id,mask_id,eqp_floor \
    --ratio 0.2 --show-dist lot_floor,eqp_floor,proc_ver
```

- `--unit`: 이 조합이 같은 행은 통째로 남기거나 통째로 뺍니다
- `--strata`: 이 조합별 비율을 원본과 같게 유지합니다 (드문 조합도 최소 1개)
- `--ratio` 생략 시 1%부터 올려가며 기준 점수(기본 85)를 넘는 최소 비율을 찾습니다
- `--show-dist`: 값별 원본·축소 비율을 표로 출력하고 그래프로 저장 (`distribution_<그룹>.csv`, `.png`)
- `--no-plot`: 그래프를 만들지 않음
- `--limit eqp_id=6`: 그 컬럼의 값 종류를 6개로 줄입니다 (많이 쓰인 순서, 남은 값끼리의 비율은 원본 그대로).
  `--limit-mode sample` 을 주면 원본 비율을 확률로 삼아 무작위로 고릅니다
- `--inspect`: 단위·층 구성만 먼저 확인

## 시작하기

1. 압축을 풀고 VS Code에서 **`reduce-compare` 폴더**를 엽니다 (`파일 → 폴더 열기`).
2. VS Code 터미널에서 git 저장소를 만들고 dev 브랜치로 옮깁니다.
   ```bash
   git init -b master
   git add -A && git commit -m "초기 설정"
   git switch -c dev
   ```
3. 같은 터미널에서 `claude`를 실행합니다. 처음 한 번은 이 폴더의 설정(훅)을 신뢰할지 묻는데, 승인해야 훅이 동작합니다.
4. 백로그 확인:
   ```bash
   python3 backlog.py stats
   python3 backlog.py next
   ```
5. Claude에게 "T001부터 시작하자"처럼 태스크를 정해 주면, `CLAUDE.md` 규칙대로 진행합니다.

## 필요한 것
- Python 3.9 이상 (훅과 백로그 CLI는 표준 라이브러리만 사용)
- git
- Claude Code
- 백엔드·프론트엔드가 생긴 뒤: `ruff`, Node.js (lint·build 훅이 사용)

Windows에서는 `.claude/settings.json`의 `python3`를 `python`으로 바꿔야 할 수 있습니다.
