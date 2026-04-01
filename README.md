# Palantir

A terminal-based RSS/Atom news reader with AI-powered article summaries.

## Features

- Browse multiple topic feeds in a three-pane TUI (topics · article list · article view)
- Fetches and merges RSS/Atom feeds per topic, sorted newest-first
- Full article text extraction via [trafilatura](https://trafilatura.readthedocs.io/)
- AI summaries via local [Ollama](https://ollama.com/) or [Groq](https://groq.com/) (fallback)
- Keyword highlighting in article body
- 15-minute feed cache; manual refresh with `r`

## Installation

Requires Python 3.11+. Uses [uv](https://docs.astral.sh/uv/) for environment management.

```bash
git clone <repo>
cd palantir
uv sync
```

Run directly:

```bash
uv run palantir
```

Or install as a tool:

```bash
uv tool install .
palantir
```

## Usage

```
palantir [--width N] [--llm-model MODEL]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--width N` | `120` | Max line width for article body (`0` = no limit) |
| `--llm-model MODEL` | `llama3.2` | Ollama model for AI summaries |

### Key bindings

| Key | Action |
|-----|--------|
| `↑`/`↓` | Navigate topics / articles |
| `Enter` | Fetch full article text |
| `f` | Fetch full article text |
| `r` | Refresh feeds (clears cache) |
| `o` | Open article URL in browser |
| `q` | Quit |

## Feed configuration

Feeds are defined in `feeds.toml`. Palantir looks for the config in this order:

1. `~/.config/palantir/feeds.toml` (user override)
2. Installed package directory
3. Project root (development)

To customise, copy `feeds.toml` to `~/.config/palantir/feeds.toml`:

```toml
[topics.my_topic]
name = "My Topic"
feeds = [
    {name = "Example", url = "https://example.com/feed.rss"},
]
```

Each topic can have any number of feeds. Failed or slow feeds are silently skipped.

## AI summaries

Summaries are generated automatically after fetching full article text.

- **Ollama** (local): Palantir auto-detects a running Ollama instance at `http://localhost:11434` and picks the best available model (prefers `llama3.2`).
- **Groq** (cloud fallback): Set the `GROQ_API_KEY` environment variable. Uses `llama-3.1-8b-instant`.

If neither is available, summaries are skipped silently.

## Dependencies

- [textual](https://textual.textualize.io/) — TUI framework
- [feedparser](https://feedparser.readthedocs.io/) — RSS/Atom parsing
- [httpx](https://www.python-httpx.org/) — async HTTP client
- [trafilatura](https://trafilatura.readthedocs.io/) — article text extraction
