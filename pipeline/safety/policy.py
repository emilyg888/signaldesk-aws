from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_ALLOWED_TOPICS = (
    "market", "markets", "stock", "stocks", "ticker", "asset", "equity", "price",
    "ohlcv", "technical", "rsi", "macd", "ema", "bollinger", "atr", "volume",
    "sentiment", "news", "macro", "fred", "cpi", "gdp", "vix", "dxy", "yield",
    "earnings", "forecast", "support", "resistance", "portfolio", "watchlist",
    "signaldesk", "dashboard", "analysis", "financial", "finance", "trading",
    "risk", "catalyst", "crypto", "currency", "forex", "bond", "rate", "rates",
)

DEFAULT_FORBIDDEN_TERMS = (
    "api key", "secret key", "webhook url", "password", "credential", "private key",
    "system prompt", "developer message", "hidden prompt", "chain of thought",
    "ignore previous instructions", "ignore all previous", "bypass", "jailbreak",
    "prompt injection", "exfiltrate", "malware", "ransomware", "phishing",
    "insider trading", "market manipulation", "pump and dump", "front run",
    "sexual", "porn", "self-harm", "terrorist", "hate speech",
)

PROMPT_INJECTION_PATTERNS = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "disregard the policy",
    "reveal your system prompt",
    "show hidden instructions",
    "print the developer message",
    "bypass the validator",
    "disable safety",
    "act as unrestricted",
    "you are now",
    "do anything now",
    "exfiltrate",
)


@dataclass(frozen=True)
class SafetyPolicy:
    allowed_topics: tuple[str, ...] = field(default_factory=lambda: DEFAULT_ALLOWED_TOPICS)
    forbidden_terms: tuple[str, ...] = field(default_factory=lambda: DEFAULT_FORBIDDEN_TERMS)
    prompt_injection_patterns: tuple[str, ...] = field(default_factory=lambda: PROMPT_INJECTION_PATTERNS)

    @classmethod
    def from_settings(cls, *, allowed_topics: tuple[str, ...] = (), denied_terms: tuple[str, ...] = ()) -> "SafetyPolicy":
        return cls(
            allowed_topics=allowed_topics or DEFAULT_ALLOWED_TOPICS,
            forbidden_terms=denied_terms or DEFAULT_FORBIDDEN_TERMS,
        )
