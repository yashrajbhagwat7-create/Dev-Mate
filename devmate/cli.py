import argparse
from pathlib import Path
from .config import Config
from .tools import ToolBox
from .agent import Agent


def main():
    parser=argparse.ArgumentParser(prog="devmate")
    parser.add_argument("--root",default=".")
    parser.add_argument("--provider",choices=["openrouter","google"])
    parser.add_argument("--mode",choices=["ask","edit","engineer","autonomous"])
    args=parser.parse_args()
    root=Path(args.root).resolve()
    cfg=Config(root=root)
    if args.provider: cfg.provider=args.provider
    if args.mode: cfg.mode=args.mode
    approve=lambda q: input(q).strip().lower() in {"y","yes"}
    box=ToolBox(cfg,approve); agent=Agent(cfg,box)
    print(f"\nDev-Mate v0.1.0 | {root}")
    print(f"Provider: {cfg.provider} | Mode: {cfg.mode}")
    print("Commands: /provider openrouter|google, /mode ask|edit|engineer|autonomous, /status, /diff, /exit")
    while True:
        try: prompt=input("\ndevmate > ").strip()
        except (EOFError,KeyboardInterrupt): print(); break
        if not prompt: continue
        if prompt in {"/exit","/quit"}: break
        if prompt.startswith("/provider "):
            cfg.provider=prompt.split(None,1)[1]; agent=Agent(cfg,box); print(f"Provider: {cfg.provider}"); continue
        if prompt.startswith("/mode "):
            cfg.mode=prompt.split(None,1)[1]; print(f"Mode: {cfg.mode}"); continue
        if prompt=="/status": print(box.git_status()); continue
        if prompt=="/diff": print(box.git_diff()); continue
        if cfg.mode in {"engineer","autonomous"}:
            agent.engineer(prompt,autonomous=cfg.mode=="autonomous")
        else:
            print("\n"+agent.run(prompt,cfg.mode))
