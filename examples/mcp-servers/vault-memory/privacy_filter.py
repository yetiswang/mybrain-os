"""
privacy_filter — pre-output redaction for the vault-memory MCP server.

Design contract (per 2026-05-09 plan + Codex audit fixes):
  * Pure stdlib. No external deps.
  * redact(obj, mode) takes any JSON-serialisable object and returns a redacted copy
    plus a structured RedactionLog. Filters paths, filenames, frontmatter, snippets.
  * Modes: "strict" (default), "lenient" (currency + <my-institution> emails allow-listed),
    "off" requires VAULT_PRIVACY_OVERRIDE=true env var, NOT exposed to public schema.
  * Fail-closed: callers must wrap in safe_redact() so any exception returns sentinel.
  * <private>...</private> blocks always redacted.
  * Frontmatter private:true / pii:true blanks body before snippet extraction.
  * Allow-list structured by type + value + required context tag.
  * Dutch IBAN mod-97, BSN 11-proof, KvK, postcode, BTW.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REDACT = "[REDACTED]"
REDACT_SENTINEL = "[REDACTED: privacy filter error]"
DEFAULT_PRIVACY_JSON = Path.home() / ".local/share/vault-watcher/privacy.json"


# Patterns
_RE_PRIVATE_BLOCK = re.compile(r"<private>.*?</private>", re.DOTALL | re.IGNORECASE)

_RE_API_KEY = re.compile(
    r"(?i)(?:api[_-]?key|token|secret|bearer|password|passwd|pwd)\s*[:=]\s*"
    r"['\"]?([A-Za-z0-9_\-+/=]{20,})['\"]?"
)
_RE_KNOWN_KEY_PREFIX = re.compile(
    r"\b(?:sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|sk-ant-[A-Za-z0-9_-]{20,}|"
    r"AIza[A-Za-z0-9_-]{20,}|xoxb-[A-Za-z0-9-]{20,})\b"
)

_RE_CURRENCY = re.compile(
    r"(?P<sym>[€$£¥])\s*(?P<num>\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?)"
    r"\s*(?P<suf>[KkMmBb]|million|billion|thousand|/yr|/year|/mo)?"
)

_RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

_RE_PHONE_NL = re.compile(
    r"(?:(?<=\D)|^)(?:\+31|0031|0)[\s\-]?\d{1,3}[\s\-]?\d{6,8}(?=\D|$)"
)
_RE_PHONE_INTL = re.compile(r"\+\d{1,3}[\s\-]?\d{2,4}[\s\-]?\d{3,4}[\s\-]?\d{3,4}\b")

_RE_NL_IBAN = re.compile(r"\bNL\d{2}[A-Z]{4}\d{10}\b")
_RE_BSN_CANDIDATE = re.compile(r"(?<!\d)(?:\d{9}|\d{8})(?!\d)")
_RE_KVK = re.compile(r"(?i)\bKvK[\s.:-]*?(\d{8})\b|\bkamer\s+van\s+koophandel[^\d]{0,20}(\d{8})\b")
_RE_NL_POSTCODE = re.compile(r"\b[1-9]\d{3}\s?[A-Z]{2}\b")
_RE_NL_BTW = re.compile(r"\bNL\d{9}B\d{2}\b")


def _validate_iban_nl(iban: str) -> bool:
    iban = iban.replace(" ", "").upper()
    if not re.fullmatch(r"NL\d{2}[A-Z]{4}\d{10}", iban):
        return False
    rearranged = iban[4:] + iban[:4]
    numeric = "".join(str(ord(c) - 55) if c.isalpha() else c for c in rearranged)
    try:
        return int(numeric) % 97 == 1
    except ValueError:
        return False


def _validate_bsn(s: str) -> bool:
    if not s.isdigit():
        return False
    if len(s) == 8:
        s = "0" + s
    if len(s) != 9:
        return False
    digits = [int(c) for c in s]
    weights = [9, 8, 7, 6, 5, 4, 3, 2, -1]
    total = sum(d * w for d, w in zip(digits, weights))
    return total % 11 == 0 and digits[0] != 0


@dataclass
class AllowRule:
    type: str
    value: str
    context_tags: list = field(default_factory=list)
    expires: str | None = None

    def applies(self, raw_match: str, source_tags: list, today: str) -> bool:
        if self.expires and today > self.expires:
            return False
        if self.context_tags and not any(t in source_tags for t in self.context_tags):
            return False
        return True


@dataclass
class PrivacyConfig:
    allow_rules: list = field(default_factory=list)
    deny_names: list = field(default_factory=list)
    allow_email_domains: list = field(default_factory=lambda: ["<email-domain>"])
    currency_threshold: float = 1_000_000.0

    @classmethod
    def load(cls, path: Path = DEFAULT_PRIVACY_JSON):
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            raise RuntimeError(f"privacy.json malformed at {path}: {e}") from e
        rules = [AllowRule(**{k:v for k,v in r.items() if not k.startswith("_")}) for r in raw.get("allow_rules", [])]
        return cls(
            allow_rules=rules,
            deny_names=raw.get("deny_names", []),
            allow_email_domains=raw.get("allow_email_domains", ["<email-domain>"]),
            currency_threshold=float(raw.get("currency_threshold", 1_000_000.0)),
        )


@dataclass
class Redaction:
    pattern: str
    snippet: str


@dataclass
class RedactionLog:
    redactions: list = field(default_factory=list)
    error: str | None = None

    def add(self, pattern: str, span: str) -> None:
        self.redactions.append(Redaction(pattern=pattern, snippet=span[:24]))

    @property
    def count(self) -> int:
        return len(self.redactions)


def _today_iso() -> str:
    from datetime import date
    return date.today().isoformat()


def _currency_to_cents(num_str: str, suffix: str) -> int:
    s = num_str.replace(",", ".") if num_str.count(",") == 1 and "." not in num_str else num_str.replace(",", "")
    try:
        val = float(s)
    except ValueError:
        return 0
    suf = suffix.lower() if suffix else ""
    if suf in ("k", "thousand"):
        val *= 1_000
    elif suf in ("m", "million"):
        val *= 1_000_000
    elif suf in ("b", "billion"):
        val *= 1_000_000_000
    return int(round(val * 100))


def _redact_text(text, *, mode, config, source_tags, log):
    if mode not in ("strict", "lenient", "off"):
        raise ValueError(f"invalid mode: {mode!r}")

    # 1. <private> blocks — always
    def _private_sub(m):
        log.add("private_block", m.group(0)); return REDACT
    text = _RE_PRIVATE_BLOCK.sub(_private_sub, text)

    if mode == "off":
        def _key_sub(m):
            log.add("known_api_key", m.group(0)); return REDACT
        return _RE_KNOWN_KEY_PREFIX.sub(_key_sub, text)

    # 2. API keys
    def _key_sub(m):
        log.add("api_key", m.group(0))
        return m.group(0).split(":")[0].split("=")[0].rstrip() + ": " + REDACT
    text = _RE_API_KEY.sub(_key_sub, text)

    def _known_key_sub(m):
        log.add("known_api_key", m.group(0)); return REDACT
    text = _RE_KNOWN_KEY_PREFIX.sub(_known_key_sub, text)

    # 3. Dutch identifiers — MUST come before phone (phone regex would consume IBAN/BSN digits)
    def _iban_sub(m):
        if _validate_iban_nl(m.group(0)):
            log.add("nl_iban", m.group(0)); return REDACT
        # invalid mod-97 but pattern-matches → still redact (privacy-cautious)
        log.add("nl_iban_unvalidated", m.group(0)); return REDACT
    text = _RE_NL_IBAN.sub(_iban_sub, text)

    def _btw_sub(m):
        log.add("nl_btw", m.group(0)); return REDACT
    text = _RE_NL_BTW.sub(_btw_sub, text)

    def _kvk_sub(m):
        log.add("kvk", m.group(0)); return REDACT
    text = _RE_KVK.sub(_kvk_sub, text)

    def _bsn_sub(m):
        if _validate_bsn(m.group(0)):
            log.add("bsn", m.group(0)); return REDACT
        return m.group(0)
    text = _RE_BSN_CANDIDATE.sub(_bsn_sub, text)

    def _postcode_sub(m):
        log.add("nl_postcode", m.group(0)); return REDACT
    text = _RE_NL_POSTCODE.sub(_postcode_sub, text)

    # 4. Currency
    today = _today_iso()
    def _currency_sub(m):
        sym = m.group("sym"); num = m.group("num"); suf = m.group("suf") or ""
        cents = _currency_to_cents(num, suf)
        if mode == "lenient" and cents < int(config.currency_threshold * 100):
            return m.group(0)
        for rule in config.allow_rules:
            if rule.type == "currency" and rule.value == str(cents):
                if rule.applies(m.group(0), source_tags, today):
                    return m.group(0)
        log.add("currency", m.group(0)); return REDACT
    text = _RE_CURRENCY.sub(_currency_sub, text)

    # 5. Email
    def _email_sub(m):
        addr = m.group(0).lower()
        domain = addr.split("@", 1)[1]
        if mode == "lenient" and domain in config.allow_email_domains:
            return m.group(0)
        log.add("email", m.group(0)); return REDACT
    text = _RE_EMAIL.sub(_email_sub, text)

    # 6. Phones — strict only (lenient keeps them)
    if mode == "strict":
        def _phone_sub(m):
            log.add("phone", m.group(0)); return REDACT
        text = _RE_PHONE_NL.sub(_phone_sub, text)
        text = _RE_PHONE_INTL.sub(_phone_sub, text)

    # 7. Deny-list names
    for name in config.deny_names:
        pat = re.compile(r"" + re.escape(name) + r"", re.IGNORECASE)
        def _name_sub(m, _pat=pat):  # default-arg captures pat by value, not by name
            log.add("deny_name", m.group(0)); return REDACT
        text = pat.sub(_name_sub, text)

    return text


def redact(obj, *, mode="strict", config=None, source_tags=None):
    if mode == "off" and os.environ.get("VAULT_PRIVACY_OVERRIDE", "").lower() != "true":
        raise PermissionError("mode='off' requires VAULT_PRIVACY_OVERRIDE=true env var")

    cfg = config if config is not None else PrivacyConfig.load()
    tags = source_tags or []
    log = RedactionLog()

    def _walk(v):
        if isinstance(v, str):
            return _redact_text(v, mode=mode, config=cfg, source_tags=tags, log=log)
        if isinstance(v, dict):
            fm = v.get("frontmatter") if isinstance(v.get("frontmatter"), dict) else {}
            is_private = bool(fm.get("private")) or bool(fm.get("pii"))
            out = {}
            for k, val in v.items():
                if is_private and k in ("body", "snippet", "snippets", "content"):
                    log.add("frontmatter_private", str(k))
                    out[k] = REDACT
                else:
                    out[k] = _walk(val)
            return out
        if isinstance(v, list):
            return [_walk(x) for x in v]
        if isinstance(v, tuple):
            return tuple(_walk(x) for x in v)
        return v

    return _walk(obj), log


def safe_redact(obj, *, mode="strict", config=None, source_tags=None):
    try:
        return redact(obj, mode=mode, config=config, source_tags=source_tags)
    except Exception as e:
        log = RedactionLog(error=f"{type(e).__name__}: {e}")
        return REDACT_SENTINEL, log


__all__ = [
    "redact", "safe_redact", "PrivacyConfig", "AllowRule",
    "RedactionLog", "REDACT", "REDACT_SENTINEL",
]
