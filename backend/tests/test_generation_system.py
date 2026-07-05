import asyncio
from pathlib import Path
import json
import os
import pytest

from app.api.communication import _safe_write_json_with_retries
from app.services.generation_history import get_generation_history


@pytest.mark.asyncio
async def test_safe_write_json_with_retries(tmp_path: Path):
    payload = {"hello": "world", "n": 1}
    target = tmp_path / "out.json"
    res = await _safe_write_json_with_retries(target, payload, attempts=2, delay=0.1)
    assert res["success"] is True, f"write failed: {res}"
    assert target.exists()
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["hello"] == "world"


@pytest.mark.asyncio
async def test_generation_history_create_list(tmp_path: Path, monkeypatch):
    # перенаправляем базовую директорию истории на tmp_path
    from app.services import generation_history as gh_mod
    hist = gh_mod.GenerationHistory(base_dir=tmp_path, ttl_seconds=0)
    # подменяем глобальный синглтон
    monkeypatch.setattr(gh_mod, "_history", hist, raising=False)
    monkeypatch.setattr(gh_mod, "get_generation_history", lambda: hist, raising=False)

    h = get_generation_history()
    rec_id = await h.create(event_type="holiday_male", segment="VIP", total=4, params={"limit": 4})
    await h.update_progress(rec_id, processed=2, success=2, errors=0)
    await h.complete(rec_id, saved_file=str(tmp_path / "file.json"), result={"status": "success", "count": 2})

    total, items = await h.list()
    assert total >= 1
    rec = await h.get(rec_id)
    assert rec is not None
    assert rec["status"] in ("completed", "failed")
    assert rec["event_type"] == "holiday_male"
