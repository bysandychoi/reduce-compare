# 서브에이전트 사용 규칙

| 서브에이전트 | 모델 | 언제 | 쓰는 파일 |
|---|---|---|---|
| task-briefer | haiku (가장 가벼운 모델) | 태스크를 in_progress로 바꾼 직후 | `docs/tasks/<ID>.md` |
| adversarial-reviewer | opus (가장 강한 모델) | 파일을 만들거나 고친 뒤, done 직전 | `docs/tasks/<ID>.review.md` |

## task-briefer
- 호출 예: "T033 브리핑을 만들어 줘" — 태스크 ID만 넘기면 된다.
- 결과 파일을 반드시 직접 읽고 시작한다. 관련 파일 목록에 빠진 것이 보이면 직접 보완해도 된다 (`docs/tasks/`는 자유롭게 수정 가능).
- 태스크 설명이 바뀌었거나(`update`) 선행 태스크가 새로 끝났으면 다시 호출해서 갱신한다.

## adversarial-reviewer
- 호출할 때 태스크 ID와 이번에 바꾼 파일 목록, 스스로 확인한 것(돌린 테스트 등)을 함께 넘긴다.
  예: "T033 리뷰. 바뀐 파일: backend/app/reduce/cluster.py, backend/tests/test_cluster.py. pytest 통과."
- 리뷰어에게 코드를 고치라고 시키지 않는다. 수정은 메인 에이전트가 한다.
- 리뷰어의 판정을 메인 에이전트가 대신 PASS로 바꾸거나 review.md의 `판정:` 줄을 고치지 않는다.
- 같은 태스크에서 3번 연속 `재작업 필요`가 나오면 멈추고 사용자에게 상황을 요약해 판단을 받는다.
- 화면·그래프 태스크면 `docs/tasks/<ID>.sample.png`가 있고 `<ID>.md`에 삽입됐는지, 그림이 이번 변경과 맞는지도 리뷰 대상이다 (task-workflow.md "대표 화면 예시").
- E0(열린 질문 결정) 태스크는 리뷰 없이 done 처리할 수 있다 (`review.exempt_epics`).

## 공통
- 두 서브에이전트 모두 `backlog.json`을 직접 읽지 않고 `python3 backlog.py show <ID>`를 쓴다.
- 서브에이전트가 만든 문서도 done 커밋에 함께 들어간다.
