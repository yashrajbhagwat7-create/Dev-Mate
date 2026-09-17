import argparse
import json
from pathlib import Path

from .config import Config
from .tools import ToolBox
from .agent import Agent


def main():
    parser = argparse.ArgumentParser(prog="devmate")

    parser.add_argument(
        "--root",
        default="."
    )

    parser.add_argument(
        "--provider",
        choices=["openrouter", "google"]
    )

    parser.add_argument(
        "--mode",
        choices=["ask", "edit", "engineer", "autonomous"]
    )

    args = parser.parse_args()

    root = Path(args.root).resolve()

    cfg = Config(root=root)

    if args.provider:
        cfg.provider = args.provider

    if args.mode:
        cfg.mode = args.mode

    approve = lambda q: input(q).strip().lower() in {"y", "yes"}

    box = ToolBox(cfg, approve)
    agent = Agent(cfg, box)

    print(f"\nDev-Mate v0.1.0 | {root}")
    print(f"Provider: {cfg.provider} | Mode: {cfg.mode}")

    print(
        "Commands: "
        "/provider openrouter|google, "
        "/mode ask|edit|engineer|autonomous, "
        "/status, /diff, /memory, /history, /exit"
    )

    while True:
        try:
            prompt = input("\ndevmate > ").strip()

        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not prompt:
            continue

        if prompt in {"/exit", "/quit"}:
            break

        # Provider
        if prompt.startswith("/provider "):
            provider = prompt.split(None, 1)[1].strip()

            if provider not in {"openrouter", "google"}:
                print("Provider must be: openrouter or google")
                continue

            cfg.provider = provider
            agent = Agent(cfg, box)

            print(f"Provider: {cfg.provider}")
            continue

        # Mode
        if prompt.startswith("/mode "):
            mode = prompt.split(None, 1)[1].strip()

            if mode not in {
                "ask",
                "edit",
                "engineer",
                "autonomous"
            }:
                print(
                    "Mode must be: "
                    "ask, edit, engineer, autonomous"
                )
                continue

            cfg.mode = mode

            print(f"Mode: {cfg.mode}")
            continue

        # Git status
        if prompt == "/status":
            print(box.git_status())
            continue

        # Git diff
        if prompt == "/diff":
            print(box.git_diff())
            continue

        # Show project memory
        if prompt == "/memory":
            memory = box.memory.load()

            print("\nPROJECT MEMORY")
            print("=" * 60)
            print(
                json.dumps(
                    memory,
                    indent=2,
                    ensure_ascii=False
                )
            )
            continue

        # Show recent activity
        if prompt == "/history":
            activity = box.memory.recent_activity(limit=30)

            print("\nRECENT ACTIVITY")
            print("=" * 60)

            if not activity:
                print("No activity recorded yet.")
                continue

            for entry in activity:
                timestamp = entry.get("timestamp", "")
                action = entry.get("action", "")
                details = entry.get("details", "")
                status = entry.get("status", "")

                status_text = (
                    f" [{status}]"
                    if status
                    else ""
                )

                print(
                    f"{timestamp} | "
                    f"{action}{status_text} | "
                    f"{details}"
                )

            continue

        # Engineering modes
        if cfg.mode in {"engineer", "autonomous"}:
            agent.engineer(
                prompt,
                autonomous=cfg.mode == "autonomous"
            )

        # Normal modes
        else:
            print(
                "\n" + agent.run(
                    prompt,
                    cfg.mode
                )
            )


if __name__ == "__main__":
    main()