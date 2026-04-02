from __future__ import annotations

import asyncio
import re
import textwrap
import webbrowser
from datetime import datetime, timezone
from typing import Optional

from rich.console import Group
from rich.markup import escape
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import Footer, Header, Label, ListItem, ListView, Select, Static

from .config import load_topics
from .fetcher import Article, FeedFetcher
from .highlight import extract_keywords, highlight_keywords
from .summarize import extract_keywords_batch, list_ollama_models, probe_ollama, summarize_article


def _format_age(dt: Optional[datetime]) -> str:
    if dt is None:
        return "?"
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    secs = (now - dt).total_seconds()
    if secs < 0:
        return "now"
    if secs < 3600:
        return f"{int(secs / 60)}m"
    if secs < 86400:
        return f"{int(secs / 3600)}h"
    return f"{int(secs / 86400)}d"


def _word_count(article: "Article") -> str:
    text = article.full_text or article.summary or ""
    count = len(text.split()) if text else 0
    if count == 0:
        return ""
    return f"{count:,}w"


def _reflow(text: str, width: int) -> str:
    if width == 0 or not text:
        return text
    paragraphs = re.split(r"\n+", text)
    filled = [textwrap.fill(" ".join(p.split()), width=width) for p in paragraphs if p.strip()]
    return "\n\n".join(filled)


class TopicItem(ListItem):
    def __init__(self, topic_id: str, name: str) -> None:
        super().__init__()
        self.topic_id = topic_id
        self._name = name

    def compose(self) -> ComposeResult:
        yield Label(self._name)


class ArticleItem(ListItem):
    def __init__(self, article: Article, highlight: bool = False, stripe: bool = False) -> None:
        super().__init__(classes="stripe" if stripe else "")
        self.article = article
        self._highlight = highlight

    def compose(self) -> ComposeResult:
        age = _format_age(self.article.published)
        if self._highlight:
            keywords = self.article.keywords or extract_keywords(self.article.title, max_keywords=3)
            title_markup = highlight_keywords(self.article.title, keywords)
        else:
            title_markup = escape(self.article.title)
        yield Label(title_markup, classes="article-title")
        yield Label(f"  {self.article.source}  ·  {age}", classes="article-meta")


class PalantirApp(App):
    TITLE = "Palantir"
    SUB_TITLE = "News Reader"

    CSS = """
    Screen {
        background: $surface;
    }

    #layout {
        height: 1fr;
    }

    #sidebar {
        width: 22;
        border-right: solid $primary-darken-2;
        height: 1fr;
    }

    #sidebar ListView {
        height: 1fr;
        background: $surface;
    }

    #sidebar ListView:focus {
        background-tint: transparent;
    }

    #right {
        width: 1fr;
        height: 1fr;
    }

    #article-list {
        height: 70%;
        border-bottom: solid $primary-darken-2;
    }

    #article-list > ListItem {
        padding: 0 1;
        height: auto;
    }

    .stripe {
        background: $surface-lighten-2;
    }

    #article-list:focus {
        background-tint: transparent;
    }

    #article-list > ListItem.stripe.-highlight {
        background: $block-cursor-background;
    }

    .article-title {
        color: $text;
        overflow: hidden hidden;
    }

    .article-meta {
        color: $text-muted;
        text-style: italic;
    }

    #article-view {
        height: 1fr;
        padding: 1 2;
        overflow-y: scroll;
    }

    #bottom-bar {
        height: 1;
        background: $primary-darken-3;
        color: $text-muted;
    }

    #status {
        width: 1fr;
        height: 1;
        color: $text-muted;
        padding: 0 1;
    }

    #model-select {
        width: 26;
        height: 1;
        background: $primary-darken-3;
        border: none;
        color: $text-muted;
        padding: 0;
    }

    #model-select > SelectCurrent {
        background: $primary-darken-3;
        border: none;
        color: $text-muted;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
        Binding("f", "fetch_full", "Fetch full text"),
        Binding("h", "toggle_list_highlight", "Highlight list"),
        Binding("o", "open_url", "Open in browser"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, max_width: int = 120, llm_model: str = "llama3.2", **kwargs) -> None:
        super().__init__(**kwargs)
        self.max_width = max_width
        self.llm_model = llm_model

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="layout"):
            with Vertical(id="sidebar"):
                yield ListView(id="topic-list")
            with Vertical(id="right"):
                yield ListView(id="article-list")
                yield ScrollableContainer(
                    Static("", id="article-content"),
                    id="article-view",
                )
        with Horizontal(id="bottom-bar"):
            yield Static("", id="status")
            yield Select([], id="model-select", prompt="no models", allow_blank=True, compact=True)
        yield Footer()

    async def on_mount(self) -> None:
        self.topics = load_topics()
        self.fetcher = FeedFetcher()
        self.articles: list[Article] = []
        self.current_article: Optional[Article] = None
        self._current_topic_id: Optional[str] = None
        import os
        self._status_msg = "Starting…"
        self._ai_backend = "none"
        self._highlight_list = False

        models = await list_ollama_models()
        model_select = self.query_one("#model-select", Select)
        if models:
            model_select.set_options([(m, m) for m in models])
            default = "gemma4:latest"
            self.llm_model = default if default in models else models[0]
            model_select.value = self.llm_model
            self._ai_backend = f"Ollama ({self.llm_model})"
        elif os.environ.get("GROQ_API_KEY"):
            self._ai_backend = "Groq"

        topic_list = self.query_one("#topic-list", ListView)
        for topic_id, topic in self.topics.items():
            topic_list.append(TopicItem(topic_id, topic["name"]))

        self._update_status()

        if self.topics:
            first_id = next(iter(self.topics))
            self._current_topic_id = first_id
            topic_list.focus()
            topic_list.index = 0
            self._load_topic(first_id)

    @on(ListView.Highlighted, "#topic-list")
    def on_topic_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item is None or not isinstance(event.item, TopicItem):
            return
        if event.item.topic_id != self._current_topic_id:
            self._current_topic_id = event.item.topic_id
            self._load_topic(event.item.topic_id)

    @on(ListView.Highlighted, "#article-list")
    def on_article_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item is None or not isinstance(event.item, ArticleItem):
            return
        self.current_article = event.item.article
        self._show_summary(event.item.article)
        # Keep 1-2 items visible below cursor
        article_list = self.query_one("#article-list", ListView)
        idx = article_list.index
        if idx is not None:
            children = list(article_list.query(ListItem))
            target_idx = min(idx + 2, len(children) - 1)
            if target_idx > idx:
                article_list.scroll_to_widget(children[target_idx], animate=False)

    @on(ListView.Selected, "#article-list")
    def on_article_selected(self, event: ListView.Selected) -> None:
        self._fetch_full_text()

    @on(Select.Changed, "#model-select")
    def on_model_selected(self, event: Select.Changed) -> None:
        if event.value is not Select.BLANK:
            self.llm_model = str(event.value)
            self._ai_backend = f"Ollama ({self.llm_model})"
            self._update_status()

    @work(exclusive=True)
    async def _load_topic(self, topic_id: str) -> None:
        topic = self.topics[topic_id]
        article_list = self.query_one("#article-list", ListView)
        content = self.query_one("#article-content", Static)

        article_list.clear()
        content.update("[dim]Loading…[/dim]")
        self.current_article = None
        self._set_status(f"Fetching {topic['name']}…")

        articles = await self.fetcher.fetch_topic(topic["feeds"])
        self.articles = articles

        article_list.clear()
        if not articles:
            article_list.append(ListItem(Label("[dim]No articles found.[/dim]")))
            content.update("[dim]No articles found.[/dim]")
            self._set_status(f"No articles · {topic['name']}")
        else:
            for i, article in enumerate(articles):
                article_list.append(ArticleItem(article, highlight=self._highlight_list, stripe=i % 2 == 1))
            article_list.index = 0
            self._set_status(f"{len(articles)} articles · {topic['name']}")
            self.current_article = articles[0]
            self._show_summary(articles[0])
            self._extract_article_keywords(articles)

    @work(exclusive=True)
    async def _fetch_full_text(self) -> None:
        article = self.current_article
        if article is None:
            return
        if article.full_text:
            self._show_summary(article)
            return

        content = self.query_one("#article-content", Static)
        self._set_status("Fetching full text…")
        content.update(
            f"[bold]{escape(article.title)}[/bold]\n"
            f"[dim]{escape(article.source)}  ·  {escape(article.url)}[/dim]\n\n"
            "[dim]Fetching full article text…[/dim]"
        )

        text = await self.fetcher.fetch_article_text(article.url)
        if text:
            article.full_text = text
            article.ai_attempted = False
            article.ai_summary = None
            self._show_summary(article)
            words = len(text.split())
            byte_size = len(text.encode())
            if byte_size >= 1024:
                size_str = f"{byte_size / 1024:.1f} KB"
            else:
                size_str = f"{byte_size} B"
            mins = max(1, round(words / 200))
            read_str = f"{mins} min read"
            age = _format_age(article.published)
            self._set_status(f"Article: {size_str}  ·  {words:,} words  ·  {read_str}  ·  {age} old")
        else:
            content.update(
                f"[bold]{escape(article.title)}[/bold]\n"
                f"[dim]{escape(article.source)}[/dim]\n\n"
                "[red]Could not fetch article text.[/red]"
            )
            self._set_status("Failed to fetch article.")

    def _update_layout(self) -> None:
        article_list = self.query_one("#article-list")
        if self.current_article and self.current_article.full_text:
            article_list.styles.height = "20%"
        else:
            article_list.styles.height = "70%"

    def _show_summary(self, article: Article) -> None:
        content = self.query_one("#article-content", Static)
        article_view = self.query_one("#article-view")
        available_width = article_view.size.width - 5  # 4 for padding:1 2, 1 for scrollbar
        if self.max_width and available_width > 0:
            reflow_width = min(self.max_width, available_width)
        else:
            reflow_width = available_width if available_width > 0 else self.max_width
        age = _format_age(article.published)

        meta = f"{escape(article.source)}  ·  {age}"
        if article.full_text:
            wc = _word_count(article)
            if wc:
                meta += f"  ·  {wc}"
        parts: list = [
            f"[bold]{escape(article.title)}[/bold]",
            f"[dim]{meta}[/dim]",
            "",
        ]

        if article.summary:
            parts += [f"[dim]{escape(article.summary)}[/dim]", ""]

        heuristic_kws = extract_keywords(article.title)
        kw_set = dict.fromkeys((article.keywords or []) + heuristic_kws)
        keywords = list(kw_set)
        if article.full_text:
            if article.ai_summary:
                bar_width = max(reflow_width - 2, 20)
                reflowed = _reflow(article.ai_summary, bar_width)
                lines = escape(reflowed).splitlines() or [""]
                bar = "\n".join(f"[orange1]▌[/orange1] {line}" for line in lines)
                parts += ["[bold orange1]AI Summary[/bold orange1]", bar, ""]
            elif article.ai_loading:
                parts += ["[dim]Generating AI summary…[/dim]", ""]
            body = _reflow(article.full_text, reflow_width)
            parts.append(highlight_keywords(body, keywords))
        elif not article.summary:
            parts.append("[bright_green]>> [/bright_green][dim]No preview available. Press Enter or f to fetch full article.[/dim]")
        else:
            parts += ["[bright_green]>> [/bright_green][dim italic]Press Enter or f to fetch full article[/dim italic]"]

        parts += ["", f"[dim]{escape(article.url)}[/dim]"]

        content.update(Group(*parts))
        self._update_layout()

        if not article.ai_attempted:
            article.ai_attempted = True
            asyncio.ensure_future(self._generate_ai_summary(article))

    @work(exclusive=False)
    async def _extract_article_keywords(self, articles: list[Article]) -> None:
        if self._ai_backend == "none":
            return
        titles = [a.title for a in articles]
        keyword_lists = await extract_keywords_batch(titles, self.llm_model)
        for article, kws in zip(articles, keyword_lists):
            if kws:
                article.keywords = kws
        if self.articles is articles:
            if self._highlight_list:
                self._rebuild_article_list()
            if self.current_article and self.current_article in articles:
                self._show_summary(self.current_article)

    async def _generate_ai_summary(self, article: Article) -> None:
        article.ai_loading = True
        self._show_summary(article)
        try:
            text = article.full_text or article.summary or ""
            if text:
                article.ai_summary = await summarize_article(
                    article.title, text, self.llm_model
                )
        finally:
            article.ai_loading = False
        if self.current_article is article:
            self._show_summary(article)

    def _rebuild_article_list(self) -> None:
        article_list = self.query_one("#article-list", ListView)
        current_index = article_list.index
        article_list.clear()
        for i, article in enumerate(self.articles):
            article_list.append(ArticleItem(article, highlight=self._highlight_list, stripe=i % 2 == 1))
        if self.articles and current_index is not None:
            article_list.index = current_index

    def action_toggle_list_highlight(self) -> None:
        self._highlight_list = not self._highlight_list
        self._rebuild_article_list()
        state = "on" if self._highlight_list else "off"
        self._set_status(f"List keyword highlight {state}")

    def action_refresh(self) -> None:
        self.fetcher.cache.invalidate_all()
        if self._current_topic_id:
            self._load_topic(self._current_topic_id)

    def on_resize(self, event) -> None:
        if getattr(self, "_ai_backend", None):
            self._update_status()
        if getattr(self, "current_article", None):
            self._show_summary(self.current_article)

    def action_fetch_full(self) -> None:
        self._fetch_full_text()

    def action_open_url(self) -> None:
        if self.current_article and self.current_article.url:
            webbrowser.open(self.current_article.url)
            self._set_status(f"Opened: {self.current_article.url[:70]}")

    def _set_status(self, msg: str) -> None:
        self._status_msg = msg
        self._update_status()

    def _update_status(self) -> None:
        self.query_one("#status", Static).update(self._status_msg)
