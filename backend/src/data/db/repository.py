"""Repository interface — generic CRUD + concrete request/outbox repos.

DDL katmanı (`data.schemas.*`) tabloları kurar, ORM modelleri
(`data.db.models`) mapping'i tutar, burası ise **use-case bazlı erişim**
sağlar.

Tasarım:
- `Repository[T]` async generic base → minimal API: `get`, `save`,
  `delete`, `session`.
- Concrete sınıflar use-case sorgularını encapsulate eder:
  - `RequestRepository.list_by_status(...)`, `get_by_ticket_id(...)`
  - `OutboxRepository.claim_next_due(...)` (worker dispatch hot-path)
- Transaction sınırı çağıran taraftadır (UoW deseni dış katmanı).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Generic, Optional, TypeVar

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import OutboxJob, Request, WorkerHeartbeat

T = TypeVar("T")


# Outbox status değerleri — `outbox_jobs.status` sütununda CHECK
# constraint ile eşdeğer. Backend ve worker tarafında aynı string'ler.
OUTBOX_PENDING = "pending"
OUTBOX_PROCESSING = "processing"
OUTBOX_RETRY = "retry"
OUTBOX_COMPLETED = "completed"
OUTBOX_DEAD_LETTER = "dead_letter"

OUTBOX_CLAIMABLE_STATUSES = (OUTBOX_PENDING, OUTBOX_RETRY)


class Repository(Generic[T]):
    """Generic CRUD. Concrete her repo bu sınıfı extend eder."""

    model: type[T]

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @property
    def session(self) -> AsyncSession:
        return self._session

    async def get(self, pk) -> Optional[T]:
        return await self._session.get(self.model, pk)

    async def save(self, entity: T) -> T:
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity: T) -> None:
        await self._session.delete(entity)
        await self._session.flush()

    async def list_all(self) -> Sequence[T]:
        stmt = select(self.model)
        result = await self._session.execute(stmt)
        return result.scalars().all()


class RequestRepository(Repository[Request]):
    """Talep tablosu için use-case access pattern'ları."""

    model = Request

    async def get_by_ticket_id(
        self, ticket_id: str, request_type: str,
    ) -> Optional[Request]:
        stmt = select(Request).where(
            Request.genai_orion_panel_ticket_id == ticket_id,
            Request.request_type == request_type,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_pending(self, limit: int = 50) -> Sequence[Request]:
        stmt = (
            select(Request)
            .where(Request.status.in_(("received", "waiting_approval", "assigned", "provisioning")))
            .order_by(Request.created_at.asc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()


class OutboxRepository(Repository[OutboxJob]):
    """Dispatcher worker tarafı için outbox erişimi."""

    model = OutboxJob

    async def insert(self, job: OutboxJob) -> OutboxJob:
        self._session.add(job)
        await self._session.flush()
        return job

    async def claim_next_pending(self) -> Optional[OutboxJob]:
        """`status='pending'` ilk satırı çeker.

        Tek worker varsa `FOR UPDATE OMIT` semantiği için PG'ye
        `with_for_update(skip_locked=True)` verilir; SQLite
        `BEGIN IMMEDIATE` ile eşdeğer davranmayı sağlar, ancak bu
        generic kod iki dialekte de çalışacak şekilde SELECT-only bırakıldı.
        Worker tarafı tek instance düşünülüyor.
        """
        stmt = (
            select(OutboxJob)
            .where(OutboxJob.status == "pending")
            .order_by(OutboxJob.available_at.asc(), OutboxJob.created_at.asc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def claim_next_due(
        self,
        *,
        worker_id: str,
        lease_duration: timedelta,
        now: datetime | None = None,
        batch_size: int = 1,
    ) -> list[OutboxJob]:
        """`pending`/`retry` ve `available_at <= now` olan job'ları atomik olarak
        `processing`'e geçirir ve lease'ini `worker_id`'ye bağlar.

        Davranış (cross-dialect):
        1. Uygun adayları sırayla seç (`available_at` ASC, `created_at` ASC).
        2. Her biri için ayrı UPDATE — `id=? AND status IN (claimable)`
           koşulu ile race'i DB'ye bırakır. Concurrent claim'lerde yalnızca
           ilk davranan `RETURNING` alır; diğerleri 0-row update.
        3. `attempts` sayacı her claim'de +1.

        Lease timeout'u kaçırırsa bir sonraki tick'te stale row'lar tekrar
        claimable olur (ajan `available_at <= now` filtresi geçer; `status`
        yine `pending` veya `retry`'dir çünkü timeout'ta transaction rollback
        OUTBOX_PROCESSING flip'ini geri alır).
        """
        lease_until = (now or datetime.now(timezone.utc).replace(tzinfo=None)) + lease_duration
        candidates_stmt = (
            select(OutboxJob.id)
            .where(
                OutboxJob.status.in_(OUTBOX_CLAIMABLE_STATUSES),
                OutboxJob.available_at <= (now or datetime.now(timezone.utc).replace(tzinfo=None)),
            )
            .order_by(OutboxJob.available_at.asc(), OutboxJob.created_at.asc())
            .limit(batch_size)
        )
        candidate_ids = (await self._session.execute(candidates_stmt)).scalars().all()
        if not candidate_ids:
            return []

        claimed: list[OutboxJob] = []
        for row_id in candidate_ids:
            stmt = (
                update(OutboxJob)
                .where(
                    OutboxJob.id == row_id,
                    OutboxJob.status.in_(OUTBOX_CLAIMABLE_STATUSES),
                )
                .values(
                    status=OUTBOX_PROCESSING,
                    lease_owner=worker_id,
                    leased_until=lease_until,
                    attempts=OutboxJob.attempts + 1,
                    updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
                )
                .returning(OutboxJob)
            )
            row = (await self._session.execute(stmt)).scalars().one_or_none()
            if row is not None:
                claimed.append(row)
        return claimed

    async def mark_completed(self, job_id: object) -> None:
        """Job'ı başarıyla tamamlandı olarak işaretle.

        Atomik: yalnız `processing` durumdaki bir row update edilir; stale
        claim'lerde (timeout sonrası başka iş tarafından tekrar alınmış)
        rowcount 0 olur ve session rollback çağıranın inisiyatifine bırakılır.
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        await self._session.execute(
            update(OutboxJob)
            .where(
                OutboxJob.id == job_id,
                OutboxJob.status == OUTBOX_PROCESSING,
            )
            .values(
                status=OUTBOX_COMPLETED,
                completed_at=now,
                updated_at=now,
                lease_owner=None,
                leased_until=None,
                last_error_code=None,
                last_error_message=None,
            )
        )

    async def mark_retry(
        self,
        job_id: object,
        *,
        available_at: datetime,
        error_code: str,
        error_message: str,
    ) -> None:
        """Job'ı `retry`'ye çevir; sonraki uygun zamanı set et.

        `max_attempts` aşıldıysa burada dönüştürme YAPMA — dispatcher'ın
        boundary logic kararı. Bu fonksiyon sadece schedule flip'idir.
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        await self._session.execute(
            update(OutboxJob)
            .where(
                OutboxJob.id == job_id,
                OutboxJob.status == OUTBOX_PROCESSING,
            )
            .values(
                status=OUTBOX_RETRY,
                available_at=available_at,
                lease_owner=None,
                leased_until=None,
                last_error_code=error_code,
                last_error_message=error_message,
                updated_at=now,
            )
        )

    async def mark_dead_letter(
        self,
        job_id: object,
        *,
        error_code: str,
        error_message: str,
    ) -> None:
        """Job'ı `dead_letter`'a çek; monitoring admin acknowledge'ı bekliyor."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        await self._session.execute(
            update(OutboxJob)
            .where(
                OutboxJob.id == job_id,
                OutboxJob.status == OUTBOX_PROCESSING,
            )
            .values(
                status=OUTBOX_DEAD_LETTER,
                completed_at=now,
                lease_owner=None,
                leased_until=None,
                last_error_code=error_code,
                last_error_message=error_message,
                updated_at=now,
            )
        )

    async def release_processing(
        self,
        job_id: object,
        *,
        error_code: str,
        error_message: str,
    ) -> None:
        """Worker beklenmedik şekilde ölürse lease'i serbest bırakır.

        Transaction akışı: bir executor crash'i sonrası row `processing`
        durumda kalır ve lease timeout'u bekler; bu metod elapsed'ın
        eşiğine gelmeden manuel geri bırakma (backoff ile) için kullanılır.
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        await self._session.execute(
            update(OutboxJob)
            .where(
                OutboxJob.id == job_id,
                OutboxJob.status == OUTBOX_PROCESSING,
            )
            .values(
                status=OUTBOX_RETRY,
                available_at=now,
                lease_owner=None,
                leased_until=None,
                last_error_code=error_code,
                last_error_message=error_message,
                updated_at=now,
            )
        )

    async def find(self, job_id: object) -> Optional[OutboxJob]:
        return await self._session.get(OutboxJob, job_id)


class WorkerHeartbeatRepository(Repository[WorkerHeartbeat]):
    """Worker per-process heartbeat upsert'leri.

    `worker_id` PK; upsert semantiği cross-dialect (`SELECT-then-INSERT/UPDATE`)
    çünkü Postgres'in `ON CONFLICT DO UPDATE` ile SQLite'in
    `INSERT OR REPLACE`'i aynı satırı tutmuyor (UUID vs autoinc conflict).

    Race: çoklu worker instance'ı farklı `worker_id` ile insert eder —
    birbirlerinin satırına dokunmaz.
    """

    model = WorkerHeartbeat

    async def upsert(
        self,
        *,
        worker_id: str,
        version: str,
        started_at: datetime,
        last_seen_at: datetime,
        active_job_id: object | None = None,
        scheduler_last_run_at: datetime | None = None,
    ) -> WorkerHeartbeat:
        existing = await self._session.get(WorkerHeartbeat, worker_id)
        if existing is None:
            row = WorkerHeartbeat(
                worker_id=worker_id,
                version=version,
                started_at=started_at,
                last_seen_at=last_seen_at,
                active_job_id=active_job_id,
                scheduler_last_run_at=scheduler_last_run_at,
            )
            self._session.add(row)
            await self._session.flush()
            return row
        existing.version = version
        existing.started_at = started_at
        existing.last_seen_at = last_seen_at
        existing.active_job_id = active_job_id
        existing.scheduler_last_run_at = scheduler_last_run_at
        await self._session.flush()
        return existing


__all__ = [
    "OUTBOX_CLAIMABLE_STATUSES",
    "OUTBOX_COMPLETED",
    "OUTBOX_DEAD_LETTER",
    "OUTBOX_PENDING",
    "OUTBOX_PROCESSING",
    "OUTBOX_RETRY",
    "OutboxRepository",
    "Repository",
    "RequestRepository",
    "WorkerHeartbeatRepository",
]
