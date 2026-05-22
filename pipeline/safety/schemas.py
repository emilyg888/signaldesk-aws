from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Ticker = str
Bias = Literal["Bullish", "Bearish", "Neutral"]
Conviction = Literal["High", "Medium", "Low"]
Direction = Literal["Up", "Down", "Flat"]
SentimentLabel = Literal["Bullish", "Bearish", "Neutral"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SentimentRequest(StrictModel):
    ticker: Ticker = Field(min_length=1, max_length=24)
    source_name: str = Field(min_length=1, max_length=40)
    texts: list[str] = Field(min_length=1, max_length=20)

    @field_validator("texts")
    @classmethod
    def text_lengths(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item and item.strip()]
        if not cleaned:
            raise ValueError("at least one non-empty text is required")
        if any(len(item) > 2000 for item in cleaned):
            raise ValueError("individual text items must be 2000 characters or less")
        return cleaned


class SentimentResponse(StrictModel):
    score: int = Field(ge=0, le=100)
    label: SentimentLabel = "Neutral"
    key_themes: list[str] = Field(default_factory=list, max_length=8)


class ForecastDay(StrictModel):
    day: str = Field(pattern=r"^D\+[1-5]$")
    direction: Direction
    magnitude: str = Field(max_length=40)
    confidence: int = Field(ge=50, le=85)


class KeyLevels(StrictModel):
    support: list[str] = Field(default_factory=list, max_length=4)
    resistance: list[str] = Field(default_factory=list, max_length=4)


class AnalysisRequest(StrictModel):
    ticker: Ticker
    price_data: dict[str, Any]
    technicals: dict[str, Any]
    sentiment: dict[str, Any]
    macro: dict[str, Any]


class AnalysisResponse(StrictModel):
    bias: Bias
    conviction: Conviction
    narrative: str = Field(min_length=1, max_length=2000)
    key_risks: list[str] = Field(default_factory=list, max_length=8)
    key_catalysts: list[str] = Field(default_factory=list, max_length=8)
    forecast: list[ForecastDay] = Field(min_length=1, max_length=5)
    key_levels: KeyLevels = Field(default_factory=KeyLevels)
    suggested_action: str = Field(default="", max_length=500)


class SourceLink(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=1000)

    @field_validator("url")
    @classmethod
    def http_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("source links must use http or https")
        return value


class EarningsReport(StrictModel):
    report_date: str = Field(default="Not available", max_length=80)
    summary: str = Field(default="", max_length=2000)
    source_links: list[SourceLink] = Field(default_factory=list, max_length=5)


class EarningsStoryRequest(StrictModel):
    ticker: Ticker
    run_data: dict[str, Any]


class EarningsStoryResponse(StrictModel):
    headline: str = Field(min_length=1, max_length=220)
    dek: str = Field(min_length=1, max_length=500)
    body: list[str] = Field(min_length=1, max_length=6)
    latest_earnings_report: EarningsReport = Field(default_factory=EarningsReport)
    watch_items: list[str] = Field(default_factory=list, max_length=8)
    disclosure_note: str = Field(default="", max_length=1000)


class NewsDraftRequest(StrictModel):
    ticker: Ticker
    run_data: dict[str, Any]


class NewsDraftResponse(StrictModel):
    headline: str = Field(min_length=1, max_length=220)
    summary: str = Field(min_length=1, max_length=800)
    article: list[str] = Field(min_length=1, max_length=8)
    social_blurb: str = Field(default="", max_length=300)
    editor_checks: list[str] = Field(default_factory=list, max_length=8)


class ManualGenerationRequest(StrictModel):
    ticker: Ticker
    generation_type: Literal["earnings_story", "news_draft"]


class StoredRunPayload(StrictModel):
    ticker: Ticker
    run_date: str
    price_data: dict[str, Any]
    technicals: dict[str, Any]
    sentiment: dict[str, Any]
    macro: dict[str, Any]
    analysis: AnalysisResponse | dict[str, Any]
    aggregate_score: int = Field(ge=0, le=100)
    news: list[dict[str, Any]] = Field(default_factory=list)
    social: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_analysis_shape(self) -> "StoredRunPayload":
        if isinstance(self.analysis, dict):
            self.analysis = AnalysisResponse.model_validate(self.analysis)
        return self
