"""Favorite UI prototypes must be gone after production favorites landed."""
import os

from fastapi.testclient import TestClient
from src.web.server import app

client = TestClient(app)

_WEB_ROOT = os.path.join(os.path.dirname(__file__), "..", "src", "web")


def test_favorite_card_prototype_route_returns_404():
    resp = client.get("/prototype/favorite-card")
    assert resp.status_code == 404


def test_favorites_filter_prototype_route_returns_404():
    resp = client.get("/prototype/favorites-filter")
    assert resp.status_code == 404


def test_favorite_prototype_assets_removed():
    paths = [
        os.path.join(_WEB_ROOT, "prototype-favorite-card.html"),
        os.path.join(_WEB_ROOT, "prototype-favorites-filter.html"),
        os.path.join(_WEB_ROOT, "static", "css", "prototype-favorite-card.css"),
        os.path.join(_WEB_ROOT, "static", "css", "prototype-favorites-filter.css"),
        os.path.join(_WEB_ROOT, "static", "js", "prototypeFavoriteCard.js"),
        os.path.join(_WEB_ROOT, "static", "js", "prototypeFavoritesFilter.js"),
    ]
    for path in paths:
        assert not os.path.exists(path), f"Prototype artifact must be deleted: {path}"


def test_server_has_no_favorite_prototype_routes():
    path = os.path.join(_WEB_ROOT, "server.py")
    with open(path, encoding="utf-8") as f:
        content = f.read()
    assert "/prototype/favorite-card" not in content
    assert "/prototype/favorites-filter" not in content


def test_prototype_notes_verdicts_retained():
    notes = os.path.join(_WEB_ROOT, "prototype", "NOTES.md")
    assert os.path.exists(notes)
    with open(notes, encoding="utf-8") as f:
        content = f.read()
    assert "C — Top bar + header chip" in content
    assert "A — Amber filled icon button" in content
