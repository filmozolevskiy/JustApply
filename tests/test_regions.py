import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from src.web.server import app

client = TestClient(app)

def test_get_regions_returns_grouped_map():
    resp = client.get("/api/regions")
    assert resp.status_code == 200
    data = resp.json()
    
    assert "US" in data
    assert "CA" in data
    assert "DE" in data
    assert "GB" in data
    
    # US curated subset
    assert "California" in data["US"]
    assert "New York" in data["US"]
    assert "Texas" in data["US"]
    assert len(data["US"]) < 50  # curated subset, not all 50 states
    
    # CA divisions
    assert "Ontario" in data["CA"]
    assert "British Columbia" in data["CA"]
    
    # DE divisions
    assert "Berlin" in data["DE"]
    assert "Bavaria" in data["DE"]
    
    # GB divisions
    assert "England" in data["GB"]
    assert "Scotland" in data["GB"]

def test_remote_is_not_a_valid_region():
    from src.core.regions import is_valid_region
    assert is_valid_region("US", "Remote") is False
    assert is_valid_region("CA", "Remote") is False
    assert is_valid_region("DE", "Remote") is False
    assert is_valid_region("GB", "Remote") is False

def test_is_valid_region_helper():
    from src.core.regions import is_valid_region
    assert is_valid_region("US", "California") is True
    assert is_valid_region("US", "Ontario") is False
    assert is_valid_region("CA", "Ontario") is True
    assert is_valid_region("XX", "Unknown") is False
