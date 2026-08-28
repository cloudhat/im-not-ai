"""PROTOTYPE: terminal driver for the proposed Codex single-call flow."""

from flow import STAGES, State, advance


BOLD = "\x1b[1m"
DIM = "\x1b[2m"
RESET = "\x1b[0m"


def render(state: State) -> None:
    print("\x1b[2J\x1b[H", end="")
    print(f"{BOLD}PROTOTYPE — Codex single-call flow{RESET}\n")
    print(f"{BOLD}상태{RESET}: {state.status}")
    if state.status == "진행 중":
        name, owner, _ = STAGES[state.stage]
        print(f"{BOLD}현재 단계{RESET}: {state.stage + 1}/{len(STAGES)} {name}")
        print(f"{BOLD}책임{RESET}: {owner}")
    print(f"{BOLD}산출물{RESET}: {', '.join(state.artifacts) or '(없음)'}")
    print(f"{BOLD}등급{RESET}: {state.grade or '(아직 없음)'}")

    print(f"\n{BOLD}이력{RESET}")
    for item in state.history:
        print(f"- {item}")
    if not state.history:
        print(f"{DIM}(아직 실행된 단계 없음){RESET}")

    print(f"\n{BOLD}[n]{RESET} {DIM}통과{RESET}  "
          f"{BOLD}[f]{RESET} {DIM}실패 주입{RESET}  "
          f"{BOLD}[d]{RESET} {DIM}50% 초과 유지{RESET}  "
          f"{BOLD}[r]{RESET} {DIM}초기화{RESET}  "
          f"{BOLD}[q]{RESET} {DIM}종료{RESET}")


def main() -> None:
    state = State()
    while True:
        render(state)
        key = input("> ").strip().lower()
        if key == "q":
            return
        if key == "r":
            state = State()
        elif key == "n":
            state = advance(state, outcome="pass")
        elif key == "f":
            state = advance(state, outcome="fail")
        elif key == "d":
            state = advance(state, outcome="over_limit")


if __name__ == "__main__":
    main()
