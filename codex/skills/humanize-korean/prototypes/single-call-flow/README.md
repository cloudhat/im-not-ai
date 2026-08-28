# PROTOTYPE — Codex single-call flow

이 prototype은 한 번의 Codex 호출에서 설치 진입점부터 최종 응답까지의 절차가
fail-fast 상태 전이로 충분한지 확인한다. 실제 파일을 만들거나 윤문하지 않으며,
최종 구현 계약도 아니다.

## 진입 SKILL 초안

설치 진입 SKILL은 선언 파일의 디렉터리를 기준으로 고정 상대경로 하나를 열어
구현 SKILL을 처음부터 끝까지 읽으라고 지시한다. 경로가 깨지면 선언 위치와
상대경로를 알리고 종료한다. 다른 경로를 찾거나 대체 구현을 사용하지 않는다.

## 구현 SKILL 초안

1. 입력이 한국어인지 확인하고 `장르`, `강도`, `최소심각도`를 확정한다. 사용자가
   번역문 또는 번역 요약이라고 명시한 경우에만 `translated=true`로 둔다.
2. 준비 도구를 호출한다. 파일 입력은 `--input-file`, 붙여넣은 텍스트는 stdin으로
   전달한다. 도구는 당일 마지막 번호 다음 `run_id`를 원자적으로 확보하고 원문을
   그대로 `_workspace/{run_id}/01_input.md`에 저장한 뒤 관련 경로를 JSON 하나로
   반환한다.
3. 구현 SKILL의 선언 위치를 기준으로 `references/quick-rules.md`를 직접 연다.
   `최소심각도: S3`일 때만 `references/s3-rules.md`를 추가로 연다. 실패하면 찾기나
   우회 없이 종료한다.
4. Codex가 탐지와 윤문을 수행한다. 자체검증 위반은 해당 edit을 롤백하고 한 번만
   다시 처리한다.
5. Codex가 임시 윤문본과 `review.json`을 쓴다. `review.json`에는 자체검증 1·3·4·6
   판정과 변경 하이라이트 3~5건만 담는다.
6. 최종화 도구를 한 번 호출한다. 이 도구가 내부에서
   `report_detection_counts.py`와 변경률 gate를 차례로 실행하고, 자체검증 2·5를
   다시 계산하며, `review.json`의 형식과 하이라이트 길이를 검증한다.
7. 최종화 도구가 등급과 경고를 결정하고 `HUMANIZE-SUMMARY`를 조립한다. 변경률이
   30% 초과·50% 이하면 등급 상한은 C다. 50%를 초과하면 등급 D와 경고를 남기되
   윤문본을 유지한다.
8. 최종화 도구가 `final.md`를 원자적으로 확정한다. 원본 반영을 명시한 파일
   입력이면 `HUMANIZE-SUMMARY`를 제외한 윤문 본문만 원본에 원자적으로 반영한다.
   이 동작은 변경률이 50%를 초과해도 같다.
9. 성공한 run에서는 임시 윤문본과 `review.json`을 삭제해 `01_input.md`와
   `final.md`만 남긴다. 도구 오류로 실패한 run에서는 진단을 위해 임시 파일을
   남긴다.
10. 최종화 도구는 `final.md` 경로, 상태, 표시 대상 카테고리 건수, 하이라이트
    1건, 권고 문구를 JSON 하나로 반환한다. Codex는 값을 재계산하지 않고 사용자
    응답 형식에 그대로 옮긴다.

경로나 도구 오류는 후속 단계를 중단한다. 일부 집계, 모델이 대신 센 수치,
대체 경로 결과는 만들지 않는다.

50% 초과 정책은 Codex 전용 override가 아니다. 생성 원본인
`references/quick-rules.header.md`를 수정하고 `build_quick_rules.py`로 공유
`quick-rules.md`를 재생성해 `humanize-monolith`에도 같은 정책을 적용한다.

## 상태 전이 확인

실행:

```bash
python3 codex/skills/humanize-korean/prototypes/single-call-flow/tui.py
```

`n`은 현재 단계를 통과시키고, `f`는 그 단계의 실패를 주입한다. 변경률 gate에서
`d`를 누르면 50% 초과 결과를 등급 D로 유지한다. 도구 실패 뒤에는 후속 단계가
실행되지 않는지 상태와 산출물 목록으로 확인할 수 있다.
