# plaud-db MCP server

A stdio MCP server that exposes a searchable SQLite + FTS5
corpus of meeting transcripts (produced by the local Plaud →
mlx-whisper → pyannote pipeline in `examples/meeting-capture/`).

## Tools

| Tool | Purpose |
|------|---------|
| `transcript_search` | FTS5 search across all transcripts. |
| `transcript_get_meeting` | Full transcript by meeting ID. |
| `transcript_list_meetings` | Recent meetings with metadata. |

FTS5 is configured with a trigram tokenizer (handles ZH+EN mixed text).

## Adapting

Point `PLAUD_DB_PATH` at the SQLite file your ingestion pipeline
populates. The schema is documented at the top of
`plaud_db_mcp_server.py`.
