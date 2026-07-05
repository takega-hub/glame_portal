import asyncio
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class GenerationRecord:
    id: str
    status: str  # running|completed|failed
    event_type: str
    segment: Optional[str]
    started_at: str
    completed_at: Optional[str] = None
    total: int = 0
    processed: int = 0
    success: int = 0
    errors: int = 0
    params: Dict[str, Any] = field(default_factory=dict)
    saved_file: Optional[str] = None
    error_message: Optional[str] = None


class GenerationHistory:
    """
    Хранилище истории генераций.
    - Runtime: память + файл-индекс history.jsonl для быстрых листингов.
    - Кэш: TTL, чтобы не перечитывать файл на каждом запросе.
    """
    def __init__(self, base_dir: Optional[Path] = None, ttl_seconds: int = 30):
        project_root = Path(__file__).parent.parent.parent
        self.base_dir = base_dir or (project_root / "backend" / "generated_messages")
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.base_dir / "history.jsonl"
        self._records: Dict[str, GenerationRecord] = {}
        self._cache_list: List[GenerationRecord] = []
        self._cache_time: float = 0.0
        self._ttl = ttl_seconds
        self._lock = asyncio.Lock()

    async def create(self, event_type: str, segment: Optional[str], total: int, params: Dict[str, Any]) -> str:
        rec_id = str(uuid4())
        rec = GenerationRecord(
            id=rec_id,
            status="running",
            event_type=event_type,
            segment=segment,
            started_at=datetime.utcnow().isoformat(),
            total=total,
            processed=0,
            success=0,
            errors=0,
            params=params or {},
        )
        async with self._lock:
            self._records[rec_id] = rec
        logger.info(f"Создана запись генерации {rec_id} ({event_type}, segment={segment})")
        return rec_id

    async def update_progress(self, rec_id: str, processed: int, success: int, errors: int):
        async with self._lock:
            rec = self._records.get(rec_id)
            if not rec:
                return
            rec.processed = processed
            rec.success = success
            rec.errors = errors

    async def set_total(self, rec_id: str, total: int):
        async with self._lock:
            rec = self._records.get(rec_id)
            if not rec:
                return
            rec.total = total

    async def complete(self, rec_id: str, saved_file: Optional[str], result: Dict[str, Any]):
        async with self._lock:
            rec = self._records.get(rec_id)
            if not rec:
                return
            rec.status = "completed"
            rec.completed_at = datetime.utcnow().isoformat()
            rec.saved_file = saved_file
        await self._append_to_index(rec)
        # Завершаем жизненный цикл задачи в памяти, чтобы не было дублей при list()
        async with self._lock:
            self._records.pop(rec_id, None)

    async def fail(self, rec_id: str, error_message: str):
        async with self._lock:
            rec = self._records.get(rec_id)
            if not rec:
                # создаём заглушку, чтобы зафиксировать ошибку
                rec = GenerationRecord(
                    id=rec_id,
                    status="failed",
                    event_type="unknown",
                    segment=None,
                    started_at=datetime.utcnow().isoformat(),
                )
                self._records[rec_id] = rec
            rec.status = "failed"
            rec.completed_at = datetime.utcnow().isoformat()
            rec.error_message = error_message
        await self._append_to_index(rec)
        # Убираем из активных, чтобы list() не дублировал записи
        async with self._lock:
            self._records.pop(rec_id, None)

    async def list(self, status: Optional[str] = None, event_type: Optional[str] = None,
                   date_from: Optional[str] = None, date_to: Optional[str] = None,
                   search: Optional[str] = None, sort_by: str = "started_at", desc: bool = True,
                   limit: int = 1000, offset: int = 0) -> Tuple[int, List[Dict[str, Any]]]:
        # обновляем кэш, если TTL вышел
        now = datetime.utcnow().timestamp()
        if now - self._cache_time > self._ttl:
            try:
                items: List[GenerationRecord] = []
                if self.index_file.exists():
                    with self.index_file.open("r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                d = json.loads(line)
                                items.append(GenerationRecord(**d))
                            except Exception:
                                continue
                async with self._lock:
                    # добавляем активные задачи из памяти
                    items.extend(list(self._records.values()))
                # Дедупликация по id, последнее встретившееся значение выигрывает
                unique: Dict[str, GenerationRecord] = {}
                for rec in items:
                    unique[rec.id] = rec
                self._cache_list = list(unique.values())
                self._cache_time = now
            except Exception as e:
                logger.exception(f"Ошибка обновления кэша истории генераций: {e}")
        items = list(self._cache_list)

        # фильтры
        def _match(rec: GenerationRecord) -> bool:
            if status and rec.status != status:
                return False
            if event_type and rec.event_type != event_type:
                return False
            if search:
                s = search.lower()
                if not (s in (rec.segment or "").lower() or s in (rec.event_type or "").lower() or s in rec.id.lower()):
                    return False
            # date filters: сравниваем started_at в ISO
            if date_from and rec.started_at < date_from:
                return False
            if date_to and rec.started_at > date_to:
                return False
            return True

        filtered = [r for r in items if _match(r)]
        # сортировка
        reverse = desc
        key_map = {
            "started_at": lambda r: r.started_at,
            "completed_at": lambda r: r.completed_at or "",
            "status": lambda r: r.status,
            "event_type": lambda r: r.event_type,
        }
        key_fn = key_map.get(sort_by, key_map["started_at"])
        filtered.sort(key=key_fn, reverse=reverse)
        total = len(filtered)
        page = filtered[offset: offset + limit]
        return total, [asdict(r) for r in page]

    async def get(self, rec_id: str) -> Optional[Dict[str, Any]]:
        # сперва проверяем в памяти
        async with self._lock:
            if rec_id in self._records:
                return asdict(self._records[rec_id])
        # затем ищем в index
        if self.index_file.exists():
            try:
                last: Optional[Dict[str, Any]] = None
                with self.index_file.open("r", encoding="utf-8") as f:
                    for line in f:
                        d = json.loads(line)
                        if d.get("id") == rec_id:
                            last = d
                if last is not None:
                    return last
            except Exception:
                pass
        return None

    async def _append_to_index(self, rec: GenerationRecord):
        try:
            line = json.dumps(asdict(rec), ensure_ascii=False)
            # Пишем синхронно в отдельном потоке, сериализуя доступ к index_file
            async with self._lock:
                await asyncio.to_thread(self._write_line, line)
            self._cache_time = 0.0  # сбрасываем кэш
        except Exception as e:
            logger.exception(f"Не удалось записать историю генераций: {e}")

    def _write_line(self, line: str):
        with self.index_file.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    async def delete_records(self, rec_ids: List[str]) -> int:
        """
        Полностью удаляет записи (все версии) из history.jsonl по указанным id.
        Перезаписывает файл безопасно через временный файл и атомарную замену.
        """
        ids = {i for i in (rec_ids or []) if i}
        if not ids:
            return 0

        async with self._lock:
            # Удаляем из активной памяти
            for rid in ids:
                self._records.pop(rid, None)

            if not self.index_file.exists():
                self._cache_time = 0.0
                return 0

            removed = await asyncio.to_thread(self._rewrite_index_without_ids, ids)
            self._cache_time = 0.0
            return removed

    def _rewrite_index_without_ids(self, ids: set) -> int:
        removed = 0
        src = self.index_file
        with src.open("r", encoding="utf-8") as fin:
            with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", dir=str(src.parent)) as tmp:
                tmp_path = Path(tmp.name)
                for raw in fin:
                    line = raw.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        if d.get("id") in ids:
                            removed += 1
                            continue
                    except Exception:
                        pass
                    tmp.write(line + "\n")
        tmp_path.replace(src)
        return removed

    async def mark_file_deleted(self, rec_id: str):
        """
        Помечает файл результата как удалённый (saved_file=None) посредством записи новой версии в индекс.
        Последняя версия выигрывает при list()/get().
        """
        # Получаем актуальную запись любым способом
        data = await self.get(rec_id)
        if not data:
            return False
        try:
            rec = GenerationRecord(**data)
        except Exception:
            # минимальная защита, если структура изменилась
            rec = GenerationRecord(
                id=data.get("id", rec_id),
                status=data.get("status", "completed"),
                event_type=data.get("event_type", "unknown"),
                segment=data.get("segment"),
                started_at=data.get("started_at") or datetime.utcnow().isoformat(),
                completed_at=data.get("completed_at"),
                total=data.get("total", 0),
                processed=data.get("processed", 0),
                success=data.get("success", 0),
                errors=data.get("errors", 0),
                params=data.get("params") or {},
                saved_file=None,
                error_message=data.get("error_message"),
            )
        # Меняем saved_file на None и записываем как новую версию
        rec.saved_file = None
        await self._append_to_index(rec)
        self._cache_time = 0.0
        return True


_history = GenerationHistory()


def get_generation_history() -> GenerationHistory:
    return _history
