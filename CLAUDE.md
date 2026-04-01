# Palantir — Claude Code Instructions

## Project overview

Terminal news reader built with [Textual](https://textual.textualize.io/). Fetches RSS/Atom feeds, extracts full article text, and generates AI summaries via Ollama or Groq.

All source lives under `src/palantir/`. Entry point: `__main__.py` → `PalantirApp` in `app.py`.

## Environment

Use `uv` for everything:

```bash
uv sync          # install deps
uv run palantir  # run the app
```

Never use `pip`, `python -m venv`, or bare `python` invocations.

## File map

| File | Responsibility |
|------|---------------|
| `app.py` | Textual `App` subclass, all UI widgets, key bindings, layout, CSS |
| `fetcher.py` | `FeedFetcher` (async RSS fetch + article text extraction), `FeedCache`, `Article` dataclass |
| `summarize.py` | AI summary via Ollama (`/api/chat`) or Groq (`/v1/chat/completions`) |
| `config.py` | Loads `feeds.toml`; searches user config dir, then package dir, then project root |
| `highlight.py` | Keyword extraction and Rich markup highlighting |
| `__main__.py` | CLI arg parsing (`--width`, `--llm-model`), launches `PalantirApp` |

## Architecture notes

- The UI is three-pane: sidebar topic list (`#topic-list`) · article list (`#article-list`) · article view (`#article-view` / `#article-content`).
- `#article-list` height is set dynamically in `_update_layout()`: 70% when no full text is loaded, 20% when full text is present (giving the article pane 80%).
- AI summaries are triggered automatically in `_show_summary()` via `asyncio.ensure_future` after full text is fetched; guarded by `article.ai_attempted`.
- Feed results are cached in memory for 15 minutes (`FeedCache`). `r` key calls `invalidate_all()` then reloads.
- `_reflow()` in `app.py` wraps article body to fit the pane width, capped at `--width`.

## Key conventions

- All network I/O is async (`httpx.AsyncClient`). Use `@work` for Textual workers or `asyncio.ensure_future` for fire-and-forget tasks.
- Textual CSS lives as a single `CSS` class variable in `PalantirApp`. No external `.tcss` files.
- Rich markup is used throughout article rendering. Always `escape()` untrusted strings before embedding in markup.
- `Article` is a plain dataclass in `fetcher.py`; mutable fields (`full_text`, `ai_summary`, etc.) are updated in place.
