"""``UnitOfWork`` (application.ports.unit_of_work) şemasının minimal
skeleton'su.

Bu iskelet **DB bağımlı handler'lar yazılmadan önce** çağıran tarafa
gerekli yüzeyi sağlar; ``approval_actions.py``, ``internal.py`` gibi
import edilebilen modüller bu yüzeyi kullanır. Davranış:

* ``async with state.new_uow() as uow`` → yeni session açar, request
  sonunda commit/rollback + close yapar.
* ``uow.requests``, ``uow.audit``, ``uow.revisions`` sub-repo'ları için
  ``None`` default döner; somut repo wiring'i refactor turunda eklenir.
* ``new_uow()`` tek-akış senaryosunu karşılar; paralel transaction
  senaryoları (worker dispatch) için ek session factory kullanılır.

Davranış sözleşmesiyle (``backend.src.application.ports.unit_of_work`` —
henüz yazılmadı) **1:1 aynı surface** sunar; ``Protocol`` tanımı
eklendiğinde bu sınıf doğrudan uyumlu olur.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class SqlAlchemyUnitOfWork:
    """Async SQLAlchemy session + sub-repo iskeleti."""

    # Sub-repo tipleri; domain katmanı yazıldığında Protocol olarak
    # resolver burada ``REQUEST_REPO = ...`` ile bağlanır. Şimdilik sadece
    # "olası alan adlarını" sıralarız ki getattr hataları görünür kalsın.
    REPO_SLOTS = ("requests", "audit", "revisions", "outbox", "secrets")

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self.session: Optional[AsyncSession] = None
        for slot in self.REPO_SLOTS:
            # AttributeError gürültüsünü en aza indirmek için None ile
            # dolduruyoruz; route handler'ları ``is None`` kontrolü
            # yapabilsin. İçeriği sonraki refactor turlarında dolar.
            self.__dict__[slot] = None

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        self.session = self._session_factory()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self.session is None:
            return
        try:
            if exc_type is None:
                await self.session.commit()
            else:
                await self.session.rollback()
        finally:
            await self.session.close()
            self.session = None

    async def commit(self) -> None:
        if self.session is None:
            raise RuntimeError("UoW transaction yok (context dışı commit)")
        await self.session.commit()

    async def rollback(self) -> None:
        if self.session is None:
            return
        await self.session.rollback()


def build_unit_of_work(
    session_factory: async_sessionmaker[AsyncSession],
) -> SqlAlchemyUnitOfWork:
    """Factory yardımcısı — ``state.new_uow`` yerine geçer.

    ``AppState`` içindeki ``new_uow`` metodu bu factory'i çağırır. Burada
    ayrı bir fonksiyon tutmak, test'lerde alternate session factory
    bağlamayı kolaylaştırır.
    """
    return SqlAlchemyUnitOfWork(session_factory)


__all__ = ["SqlAlchemyUnitOfWork", "build_unit_of_work"]
