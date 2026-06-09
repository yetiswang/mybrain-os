# Helpers: niche but reusable

Three scripts that aren't core to the multiagent OS but are
useful on their own.

| File | Purpose |
|------|---------|
| `import_rabobank.py` | Parse Rabobank Dutch bank/credit-card PDFs into SQLite with auto-categorisation. |
| `fetch_market_data.py` | Fetch CBS CPI / house price index, ECB rates, Yahoo Finance indices. Drives a home-finance dashboard. |
| `transcribe_memos.py` | Transcribe Apple Voice Memos with Apple's transcript first, mlx-whisper fallback. Routes content to vault inbox. |

## Adapting

- `import_rabobank.py`: populate `CATEGORY_KEYWORDS` with patterns
  from your own statements. PDF layout is specific to Rabobank;
  adapt the parser for other banks.
- `fetch_market_data.py`: CBS endpoints are NL-specific. Swap for
  your country's open statistics body (e.g. ONS for UK, FRED for US).
- `transcribe_memos.py`: macOS-only (reads from `~/Library/Application
  Support/com.apple.voicememos`).
