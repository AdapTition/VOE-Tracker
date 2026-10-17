"""Entry point: python -m voe_explorer (and the PyInstaller exe)."""
from __future__ import annotations

import os
import sys
import threading
from datetime import date, datetime
from pathlib import Path

import webview

from . import __version__, config
from .api import Api
from .install import is_transient_location
from .net import Net
from .resolver import Resolver
from .service import Service
from .storage import AddressStore, Db, MemoryStore
from .updates import cached_update
from .voe_client import VoeClient


def ui_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "voe_explorer" / "ui" / "index.html"
    return Path(__file__).parent / "ui" / "index.html"


def check_updates(service: Service, memory: MemoryStore) -> None:
    info = cached_update(memory, config.RELEASES_REPO, __version__, date.today().isoformat())
    if info:
        service.update = info


def main() -> None:
    app_dir = config.APP_DIR
    app_dir.mkdir(parents=True, exist_ok=True)
    addresses = AddressStore(app_dir / "addresses.json")
    memory = MemoryStore(app_dir / "memory.json")
    db = Db(app_dir / "voe.sqlite3")
    db.prune(datetime.now(), {a.id for a in addresses.all()})

    client = VoeClient(Net())
    service = Service(client, Net(), addresses, db, app_dir / "samples")
    resolver = Resolver(client, memory)
    service.install_offer = bool(
        getattr(sys, "frozen", False)
        and is_transient_location(Path(sys.executable), os.environ)
        and not memory.get("__install_dismissed"))

    holder: dict = {}
    api = Api(service, resolver, client, addresses, db, lambda: holder.get("window"), memory=memory)
    holder["window"] = webview.create_window(
        f"VOE Explorer {__version__}", url=str(ui_path()), js_api=api,
        width=480, height=780, min_size=(380, 520), background_color="#f6f6f3")

    def on_start():
        service.start()
        threading.Thread(target=check_updates, args=(service, memory), daemon=True).start()

    try:
        webview.start(on_start)
    finally:
        service.stop()


if __name__ == "__main__":
    main()
