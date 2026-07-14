"""Agent 1: Short-term swing trade scanner (1-2 months)."""

from __future__ import annotations

from datetime import datetime

from langchain_core.runnables import RunnableLambda, RunnableSequence

from stock_agents.config import DEFAULT_MODEL, OUTPUT_DIR, ensure_api_key
from stock_agents.features.market_context import (
    build_index_context,
    get_foreign_snapshot,
)
from stock_agents.features.technical_features import (
    build_combined_summary,
    build_trade_levels,
    is_missing_text,
)
from stock_agents.prompts.parsers import (
    extraction_to_short_term,
    parse_short_term_decisions,
)
from stock_agents.prompts.short_term import build_short_term_prompt
from stock_agents.reporting.chart_renderer import render_symbol_chart
from stock_agents.reporting.markdown_report import build_short_term_report, save_report
from stock_agents.reporting.recommendation_log import log_short_term_recommendations
from stock_agents.reporting.validation import validate_analysis_output
from stock_agents.schemas import (
    ShortTermAgentInput,
    ShortTermAgentOutput,
    ShortTermExtraction,
)
from stock_agents.tools.openai_research_tool import research_structured
from stock_agents.tools.vnstock_tools import fetch_symbol_bundle


class ShortTermAgent:
    """LangChain-orchestrated swing trade agent."""

    def __init__(self, model: str | None = None, stream: bool = True):
        ensure_api_key()
        self.model = model or DEFAULT_MODEL
        self.stream = stream
        self.pipeline = self._build_pipeline()

    def _build_pipeline(self) -> RunnableSequence:
        return RunnableLambda(self._fetch_data) | RunnableLambda(self._analyze)

    def _fetch_data(self, agent_input: ShortTermAgentInput) -> dict:
        end_dt = None
        if agent_input.as_of_date:
            end_dt = datetime.combine(agent_input.as_of_date, datetime.min.time())

        symbol_reports = []
        bundles = []
        failed = []

        index_context = build_index_context(
            source=agent_input.source,
            history_days=agent_input.history_days,
            end_date=end_dt,
        )
        index_df = index_context["df"] if index_context else None

        for symbol in agent_input.symbols:
            try:
                bundle = fetch_symbol_bundle(
                    symbol=symbol,
                    source=agent_input.source,
                    history_days=agent_input.history_days,
                    end_date=end_dt,
                    index_df=index_df,
                )
                bundles.append(bundle)
                symbol_reports.append(
                    {
                        "symbol": bundle["symbol"],
                        "source": bundle["source"],
                        "indicators": bundle["indicators"],
                        "score": bundle["score"],
                    }
                )
            except Exception as exc:
                failed.append((symbol, str(exc)))

        if not symbol_reports:
            raise RuntimeError("Khong lay duoc du lieu cho ma nao.")

        foreign_map = get_foreign_snapshot(
            [r["symbol"] for r in symbol_reports],
            source=agent_input.source,
            end_date=end_dt,
        )
        combined = build_combined_summary(
            symbol_reports,
            as_of_date=end_dt,
            index_summary=index_context["summary_text"] if index_context else "",
            foreign_map=foreign_map,
        )
        fundamentals_blocks = [
            b["fundamentals"].get("summary_text", "") for b in bundles
        ]
        combined += "\n\n" + "\n".join(f for f in fundamentals_blocks if f)

        return {
            "input": agent_input,
            "symbol_reports": symbol_reports,
            "bundles": bundles,
            "combined_summary": combined,
            "failed": failed,
            "end_dt": end_dt,
        }

    def _analyze(self, state: dict) -> dict:
        agent_input: ShortTermAgentInput = state["input"]
        combined = state["combined_summary"]
        symbols = [r["symbol"] for r in state["symbol_reports"]]

        prompt = build_short_term_prompt(
            symbols=symbols,
            combined_summary=combined,
            top_n=agent_input.top_n,
            as_of_date=state.get("end_dt"),
        )

        raw, extraction = research_structured(
            prompt=prompt,
            schema=ShortTermExtraction,
            model=self.model,
            stream=self.stream,
        )

        if extraction is not None:
            market, decisions, conclusion = extraction_to_short_term(
                extraction, symbols
            )
        else:
            market, decisions, conclusion = parse_short_term_decisions(raw, symbols)
        levels_by_symbol = {
            report["symbol"]: build_trade_levels(report["indicators"])
            for report in state["symbol_reports"]
        }
        for decision in decisions:
            levels = levels_by_symbol.get(decision.symbol, {})
            if is_missing_text(decision.early_buy_zone):
                decision.early_buy_zone = levels.get("early_buy_zone", decision.early_buy_zone)
            if is_missing_text(decision.safe_buy_zone):
                decision.safe_buy_zone = levels.get("safe_buy_zone", decision.safe_buy_zone)
            if is_missing_text(decision.stop_loss):
                decision.stop_loss = levels.get("stop_loss", decision.stop_loss)
            if is_missing_text(decision.target_1_2m):
                decision.target_1_2m = levels.get("target_1_2m", decision.target_1_2m)
            if is_missing_text(decision.risk_reward):
                decision.risk_reward = levels.get("risk_reward", decision.risk_reward)

        as_of_str = (
            agent_input.as_of_date.isoformat()
            if agent_input.as_of_date
            else datetime.today().strftime("%Y-%m-%d")
        )

        output = ShortTermAgentOutput(
            as_of_date=as_of_str,
            market=market,
            symbols=decisions,
            deployment_conclusion=conclusion,
            raw_analysis=raw,
        )

        chart_paths = {}
        charts_dir = OUTPUT_DIR / "charts"
        for bundle, decision in zip(state["bundles"], decisions):
            path = render_symbol_chart(
                bundle["df"],
                bundle["symbol"],
                decision=decision,
                output_dir=charts_dir,
            )
            if path:
                chart_paths[bundle["symbol"]] = path

        validation = validate_analysis_output(
            raw, as_of_date=state.get("end_dt"), mode="short_term"
        )

        report = build_short_term_report(
            output,
            combined,
            chart_paths,
            validation=validation,
        )

        score_map = {
            r["symbol"]: r["score"]["score_total"] for r in state["symbol_reports"]
        }
        log_short_term_recommendations(
            output,
            score_map=score_map,
            source=agent_input.source,
            model=self.model,
        )

        joined = "-".join(symbols[:5])
        if len(symbols) > 5:
            joined += f"-and-{len(symbols) - 5}-more"
        run_ts = datetime.now().strftime("%H%M%S")
        filename = f"SHORT_TERM_{joined}_{as_of_str}_{run_ts}.md"
        report_path = save_report(report, filename)

        return {
            "output": output,
            "report_path": report_path,
            "chart_paths": chart_paths,
            "validation": validation,
            "failed": state.get("failed", []),
            "combined_summary": combined,
        }

    def run(self, agent_input: ShortTermAgentInput) -> dict:
        """Execute full pipeline."""
        return self.pipeline.invoke(agent_input)
