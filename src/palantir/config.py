from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any


def get_feeds_path() -> Path:
    # 1. User override
    user = Path.home() / ".config" / "palantir" / "feeds.toml"
    if user.exists():
        return user
    # 2. Alongside this module (installed package)
    pkg = Path(__file__).parent / "feeds.toml"
    if pkg.exists():
        return pkg
    # 3. Project root (development)
    dev = Path(__file__).parent.parent.parent / "feeds.toml"
    if dev.exists():
        return dev
    raise FileNotFoundError(
        "feeds.toml not found. Put one at ~/.config/palantir/feeds.toml "
        "or at the project root."
    )


def load_topics() -> dict[str, Any]:
    path = get_feeds_path()
    with open(path, "rb") as fh:
        data = tomllib.load(fh)
    return data.get("topics", {})
