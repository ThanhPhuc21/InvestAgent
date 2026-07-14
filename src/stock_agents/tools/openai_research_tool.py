"""OpenAI Responses API wrapper with web_search for LangChain agents."""

from __future__ import annotations

from typing import TypeVar

from langchain_core.tools import tool
from openai import OpenAI
from pydantic import BaseModel

from stock_agents.config import DEFAULT_MODEL, TEMPERATURE, ensure_api_key

TModel = TypeVar("TModel", bound=BaseModel)


def _get_client() -> OpenAI:
    return OpenAI(api_key=ensure_api_key())


def research_with_web_search(
    prompt: str,
    model: str | None = None,
    temperature: float = TEMPERATURE,
    stream: bool = False,
) -> str:
    """Call OpenAI Responses API with web_search tool."""
    client = _get_client()
    model_name = model or DEFAULT_MODEL

    if stream:
        with client.responses.stream(
            model=model_name,
            temperature=temperature,
            tools=[{"type": "web_search"}],
            input=prompt,
        ) as response_stream:
            for event in response_stream:
                if event.type == "response.output_text.delta":
                    print(event.delta, end="", flush=True)
            print()
            return response_stream.get_final_response().output_text

    response = client.responses.create(
        model=model_name,
        temperature=temperature,
        tools=[{"type": "web_search"}],
        input=prompt,
    )
    return response.output_text


def extract_structured(
    analysis_markdown: str,
    schema: type[TModel],
    model: str | None = None,
    temperature: float = 0.0,
) -> TModel | None:
    """Extract structured data from analysis markdown using responses.parse.

    Returns a parsed pydantic instance, or None if extraction fails so the
    caller can fall back to the regex parser.
    """
    if not analysis_markdown:
        return None

    client = _get_client()
    model_name = model or DEFAULT_MODEL
    extraction_prompt = (
        "Duoi day la bao cao phan tich co phieu bang tieng Viet (markdown). "
        "Hay trich xuat CHINH XAC cac truong theo schema, khong bia them thong tin. "
        "Neu mot truong khong co trong bao cao, de trong hoac null.\n\n"
        f"{analysis_markdown}"
    )

    try:
        response = client.responses.parse(
            model=model_name,
            temperature=temperature,
            input=extraction_prompt,
            text_format=schema,
        )
        return response.output_parsed
    except Exception:
        return None


def research_structured(
    prompt: str,
    schema: type[TModel],
    model: str | None = None,
    temperature: float = TEMPERATURE,
    stream: bool = False,
) -> tuple[str, TModel | None]:
    """Run web-search research, then extract structured output.

    Step 1 keeps the markdown for humans; step 2 parses it into `schema`.
    """
    markdown = research_with_web_search(
        prompt=prompt, model=model, temperature=temperature, stream=stream
    )
    parsed = extract_structured(markdown, schema, model=model)
    return markdown, parsed


@tool
def openai_web_research(prompt: str, model: str = DEFAULT_MODEL) -> str:
    """Phan tich co phieu bang OpenAI ket hop web search.

    Args:
        prompt: Prompt day du chua du lieu vnstock va yeu cau output.
        model: Ten model OpenAI (mac dinh tu config).

    Returns:
        Phan tich markdown tu OpenAI.
    """
    return research_with_web_search(prompt=prompt, model=model, stream=False)


def build_langchain_research_tool(model: str | None = None):
    """Factory for research tool with bound model."""

    model_name = model or DEFAULT_MODEL

    @tool
    def bound_research(prompt: str) -> str:
        """Phan tich thi truong/co phieu voi OpenAI web_search."""
        return research_with_web_search(prompt=prompt, model=model_name)

    return bound_research
