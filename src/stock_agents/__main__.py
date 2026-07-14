"""Allow running as python -m stock_agents."""

from stock_agents.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
