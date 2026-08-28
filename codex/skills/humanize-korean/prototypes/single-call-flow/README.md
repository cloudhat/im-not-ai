# PROTOTYPE — Codex single-call flow

이 prototype은 한 번의 Codex 호출에서 설치 진입점부터 최종 응답까지의 절차가
fail-fast 상태 전이로 충분한지 확인한다. 실제 파일을 만들거나 윤문하지 않으며,
최종 구현 계약도 아니다.

초안의 전제는 다음과 같다.

- 설치 진입 SKILL은 선언 위치 기준의 고정 상대경로로 구현 SKILL을 읽고 끝난다.
- 구현 SKILL은 입력과 옵션을 검증한 뒤 결정적 도구로 run directory와
  `01_input.md`를 만든다.
- Codex는 규칙을 읽고 윤문 본문 초안을 만든다.
- 결정적 도구가 탐지 건수와 변경률 gate를 계산한다.
- 모든 검증이 통과한 뒤에만 `final.md`를 확정하고, 명시적으로 요청된 경우에만
  원본 파일에 반영한다.
- 경로나 도구가 실패하면 검색·대체 구현·수치 추정 없이 즉시 중단한다.

실행:

```bash
python3 codex/skills/humanize-korean/prototypes/single-call-flow/tui.py
```

`n`은 현재 단계를 통과시키고, `f`는 그 단계의 실패를 주입한다. 실패 뒤에는
후속 단계가 실행되지 않는지 상태와 산출물 목록으로 확인할 수 있다.
