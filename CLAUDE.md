# 작업 규칙

이 프로젝트는 `.claude/settings.json`의 훅이 아래 규칙을 강제합니다. 훅이 막거나 되돌려 보내면 메시지대로 고친 뒤 계속하세요.
세부 규칙은 `.claude/rules/`에 있습니다: 태스크 진행(`task-workflow.md`), 서브에이전트 사용(`subagents.md`).

## 문서
- 요구사항: `problem.md`
- 작업 목록: `backlog.json` — **직접 읽거나 수정하지 말고** `python3 backlog.py`로만 다룹니다.
- 태스크 안내서: `docs/tasks/<ID>.md` (task-briefer가 작성)
- 태스크 리뷰: `docs/tasks/<ID>.review.md` (adversarial-reviewer가 작성)

## 태스크 진행 순서 (요약)
1. `python3 backlog.py next`로 고르고, 사용자와 합의한 태스크를 `status <ID> in_progress`
2. **task-briefer**(haiku)로 `docs/tasks/<ID>.md` 작성 → 읽고 시작
3. 구현 — in_progress 태스크가 없으면 파일 수정이 막힙니다
4. 파일을 만들거나 고친 뒤 **adversarial-reviewer**(opus)로 리뷰 → 재작업 필요면 고치고 다시 리뷰
5. PASS를 받으면 `status <ID> done` → lint·build 통과 시 자동 커밋·push

## 백로그 CLI
- 조회: `python3 backlog.py list [-e E3] [-s todo] [-r]`, `next`, `show T033`, `stats`
- 수정: `update T033 ...`, `status T010 in_progress|done|blocked`
- 추가: `add -e E13 -t "제목" -m 20 --dep T131 --ac "완료 기준"` (태스크는 30분 이하)

## 자동으로 일어나는 일
- 세션 시작: 현재 브랜치와 진행 중인 태스크를 알려 줍니다.
- 백로그를 바꾸면 `backlog.json`만 자동 커밋됩니다.
- `done`으로 바꾸면 리뷰 PASS와 lint·build 통과를 확인하고, 전체 작업을 커밋·push합니다.
  조건을 못 채우거나 master/main 브랜치면 `in_progress`로 되돌려집니다.
- 작업을 끝낼 때 lint·build가 통과해야 종료할 수 있습니다.

## 코드 길이
- 파일·함수 줄 수 한도는 `.claude/hooks/config.json`의 `line_limits`에 있습니다 (빈 줄 제외).
- 85% 이상이면 경고: 더 늘리기 전에 분리를 고려합니다.
- 100%를 넘으면 반려: 모듈이나 함수를 나눠서 다시 작업합니다.

## 브랜치
- `master`/`main`에서 직접 작업하지 않습니다. `dev` 브랜치에서 작업합니다.
