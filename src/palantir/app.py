from __future__ import annotations

import webbrowser
from datetime import datetime, timezone
from typing import Optional

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import Footer, Header, Label, ListItem, ListView, Static

from .config import load_topics
from .fetcher import Article, FeedFetcher


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


class TopicItem(ListItem):
    def __init__(self, topic_id: str, name: str) -> None:
        super().__init__()
        self.topic_id = topic_id
        self._name = name

    def compose(self) -> ComposeResult:
        yield Label(self._name)


class ArticleItem(ListItem):
    def __init__(self, article: Article) -> None:
        super().__init__()
        self.article = article

    def compose(self) -> ComposeResult:
        title = self.article.title
        if len(title) > 65:
            title = title[:62] + "…"
        age = _format_age(self.article.published)
        yield Label(title, classes="article-title")
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

    #right {
        width: 1fr;
        height: 1fr;
    }

    #article-list {
        height: 45%;
        border-bottom: solid $primary-darken-2;
    }

    #article-list > ListItem {
        padding: 0 1;
        height: auto;
    }

    .article-title {
        color: $text;
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

    #status {
        height: 1;
        background: $primary-darken-3;
        color: $text-muted;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
        Binding("f", "fetch_full", "Fetch full text"),
        Binding("o", "open_url", "Open in browser"),
        Binding("q", "quit", "Quit"),
    ]

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
        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        self.topics = load_topics()
        self.fetcher = FeedFetcher()
        self.articles: list[Article] = []
        self.current_article: Optional[Article] = None
        self._current_topic_id: Optional[str] = None

        topic_list = self.query_one("#topic-list", ListView)
        for topic_id, topic in self.topics.items():
            topic_list.append(TopicItem(topic_id, topic["name"]))

        if self.topics:
            first_id = next(iter(self.topics))
            self._current_topic_id = first_id
            topic_list.focus()
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

    @on(ListView.Selected, "#article-list")
    def on_article_selected(self, event: ListView.Selected) -> None:
        self._fetch_full_text()

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
            for article in articles:
                article_list.append(ArticleItem(article))
            self._set_status(f"{len(articles)} articles · {topic['name']}")
            self.current_article = articles[0]
            self._show_summary(articles[0])

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
            f"[bold]{article.title}[/bold]\n"
            f"[dim]{article.source}  ·  {article.url}[/dim]\n\n"
            "[dim]Fetching full article text…[/dim]"
        )

        text = await self.fetcher.fetch_article_text(article.url)
        if text:
            article.full_text = text
            self._show_summary(article)
            self._set_status("Article loaded.")
        else:
            content.update(
                f"[bold]{article.title}[/bold]\n"
                f"[dim]{article.source}[/dim]\n\n"
                "[red]Could not fetch article text.[/red]"
            )
            self._set_status("Failed to fetch article.")

    def _show_summary(self, article: Article) -> None:
        content = self.query_one("#article-content", Static)
        age = _format_age(article.published)
        lines = [
            f"[bold]{article.title}[/bold]",
            f"[dim]{article.source}  ·  {age}  ·  {article.url}[/dim]",
            "",
        ]
        if article.full_text:
            lines.append(article.full_text)
        elif article.summary:
            lines.append(article.summary)
            lines += ["", "[dim italic]Press Enter or f to fetch full article[/dim italic]"]
        else:
            lines.append("[dim]No preview available. Press Enter or f to fetch full article.[/dim]")
        content.update("\n".join(lines))

    def action_refresh(self) -> None:
        self.fetcher.cache.invalidate_all()
        if self._current_topic_id:
            self._load_topic(self._current_topic_id)

    def action_fetch_full(self) -> None:
        self._fetch_full_text()

    def action_open_url(self) -> None:
        if self.current_article and self.current_article.url:
            webbrowser.open(self.current_article.url)
            self._set_status(f"Opened: {self.current_article.url[:70]}")

    def _set_status(self, msg: str) -> None:
        self.query_one("#status", Static).update(msg)
