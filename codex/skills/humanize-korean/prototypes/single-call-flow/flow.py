"""PROTOTYPE: pure state machine for the proposed Codex single-call flow."""

from dataclasses import dataclass, replace


STAGES = (
    ("진입점 위임", "Codex", ()),
    ("요청 검증", "Codex", ()),
    ("run 준비", "결정적 도구", ("01_input.md",)),
    ("규칙 로드", "Codex", ()),
    ("윤문 초안", "Codex", (".draft.md",)),
    ("탐지 건수 집계", "결정적 도구", ("counts.json",)),
    ("변경률 gate", "결정적 도구", ()),
    ("최종 산출물 확정", "결정적 도구", ("final.md",)),
    ("사용자 응답", "Codex", ()),
)


@dataclass(frozen=True)
class State:
    stage: int = 0
    status: str = "진행 중"
    artifacts: tuple[str, ...] = ()
    history: tuple[str, ...] = ()


def advance(state: State, succeeds: bool) -> State:
    """Return the next state without performing I/O."""
    if state.status != "진행 중":
        return state

    name, owner, new_artifacts = STAGES[state.stage]
    if not succeeds:
        return replace(
            state,
            status=f"중단 — {name} 실패, 후속 단계 실행 안 함",
            history=state.history + (f"실패: {name} ({owner})",),
        )

    history = state.history + (f"통과: {name} ({owner})",)
    artifacts = state.artifacts + new_artifacts
    if state.stage == len(STAGES) - 1:
        return replace(
            state,
            status="완료",
            artifacts=artifacts,
            history=history,
        )

    return replace(
        state,
        stage=state.stage + 1,
        artifacts=artifacts,
        history=history,
    )
