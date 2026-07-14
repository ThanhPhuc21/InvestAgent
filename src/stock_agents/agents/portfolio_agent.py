"""Agent 2: Portfolio management for held positions."""

from __future__ import annotations

from datetime import datetime

from langchain_core.runnables import RunnableLambda, RunnableSequence

from stock_agents.config import DEFAULT_MODEL, OUTPUT_DIR, ensure_api_key
from stock_agents.features.market_context import (
    build_index_context,
    get_foreign_snapshot,
)
from stock_agents.features.portfolio_features import build_portfolio_combined_summary
from stock_agents.prompts.parsers import (
    extraction_to_portfolio,
    parse_portfolio_decisions,
)
from stock_agents.prompts.short_term import build_portfolio_prompt
from stock_agents.reporting.chart_renderer import render_portfolio_chart
from stock_agents.reporting.markdown_report import build_portfolio_report, save_report
from stock_agents.reporting.validation import validate_analysis_output
from stock_agents.schemas import (
    PortfolioAgentInput,
    PortfolioAgentOutput,
    PortfolioExtraction,
)
from stock_agents.tools.openai_research_tool import research_structured
from stock_agents.tools.vnstock_tools import fetch_symbol_bundle


class PortfolioAgent:
    """LangChain-orchestrated portfolio advisory agent."""

    def __init__(self, model: str | None = None, stream: bool = True):
        ensure_api_key()
        self.model = model or DEFAULT_MODEL
        self.stream = stream
        self.pipeline = self._build_pipeline()

    def _build_pipeline(self) -> RunnableSequence:
        return RunnableLambda(self._fetch_data) | RunnableLambda(self._analyze)

    def _fetch_data(self, agent_input: PortfolioAgentInput) -> dict:
        end_dt = None
        if agent_input.as_of_date:
            end_dt = datetime.combine(agent_input.as_of_date, datetime.min.time())

        position_reports = []
        bundles = []
        failed = []

        index_context = build_index_context(
            source=agent_input.source,
            history_days=agent_input.history_days,
            end_date=end_dt,
        )
        index_df = index_context["df"] if index_context else None

        for pos in agent_input.positions:
            try:
                bundle = fetch_symbol_bundle(
                    symbol=pos.symbol,
                    source=agent_input.source,
                    history_days=agent_input.history_days,
                    end_date=end_dt,
                    quantity=pos.quantity,
                    avg_price=pos.avg_price,
                    index_df=index_df,
                )
                bundles.append(bundle)
                position_reports.append(
                    {
                        "symbol": bundle["symbol"],
                        "source": bundle["source"],
                        "indicators": bundle["indicators"],
                        "score": bundle["score"],
                        "position": bundle["position"],
                    }
                )
            except Exception as exc:
                failed.append((pos.symbol, str(exc)))

        if not position_reports:
            raise RuntimeError("Khong lay duoc du lieu cho vi the nao.")

        foreign_map = get_foreign_snapshot(
            [r["symbol"] for r in position_reports],
            source=agent_input.source,
            end_date=end_dt,
        )
        combined = build_portfolio_combined_summary(
            position_reports,
            as_of_date=end_dt,
            index_summary=index_context["summary_text"] if index_context else "",
            foreign_map=foreign_map,
            cash_available=agent_input.cash_available,
        )
        fundamentals_blocks = [
            b["fundamentals"].get("summary_text", "") for b in bundles
        ]
        combined += "\n\n" + "\n".join(f for f in fundamentals_blocks if f)

        return {
            "input": agent_input,
            "position_reports": position_reports,
            "bundles": bundles,
            "combined_summary": combined,
            "failed": failed,
            "end_dt": end_dt,
        }

    def _analyze(self, state: dict) -> dict:
        agent_input: PortfolioAgentInput = state["input"]
        combined = state["combined_summary"]
        symbols = [r["symbol"] for r in state["position_reports"]]

        prompt = build_portfolio_prompt(
            symbols=symbols,
            combined_summary=combined,
            as_of_date=state.get("end_dt"),
            cash_available=agent_input.cash_available,
        )

        raw, extraction = research_structured(
            prompt=prompt,
            schema=PortfolioExtraction,
            model=self.model,
            stream=self.stream,
        )

        if extraction is not None:
            decisions, summary = extraction_to_portfolio(
                extraction, state["position_reports"]
            )
        else:
            decisions, summary = parse_portfolio_decisions(
                raw, state["position_reports"]
            )

        as_of_str = (
            agent_input.as_of_date.isoformat()
            if agent_input.as_of_date
            else datetime.today().strftime("%Y-%m-%d")
        )

        output = PortfolioAgentOutput(
            as_of_date=as_of_str,
            positions=decisions,
            portfolio_summary=summary,
            raw_analysis=raw,
        )

        chart_paths = {}
        charts_dir = OUTPUT_DIR / "charts"
        for bundle in state["bundles"]:
            pos = bundle["position"]
            if pos and pos.get("avg_price"):
                path = render_portfolio_chart(
                    bundle["df"],
                    bundle["symbol"],
                    avg_price=pos["avg_price"],
                    output_dir=charts_dir,
                )
                if path:
                    chart_paths[bundle["symbol"]] = path

        validation = validate_analysis_output(
            raw, as_of_date=state.get("end_dt"), mode="portfolio"
        )

        report = build_portfolio_report(
            output,
            combined,
            chart_paths,
            validation=validation,
        )

        joined = "-".join(symbols[:5])
        run_ts = datetime.now().strftime("%H%M%S")
        filename = f"PORTFOLIO_{joined}_{as_of_str}_{run_ts}.md"
        report_path = save_report(report, filename)

        return {
            "output": output,
            "report_path": report_path,
            "chart_paths": chart_paths,
            "validation": validation,
            "failed": state.get("failed", []),
            "combined_summary": combined,
        }

    def run(self, agent_input: PortfolioAgentInput) -> dict:
        """Execute full pipeline."""
        return self.pipeline.invoke(agent_input)
