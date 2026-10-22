from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.database.models import (
    CheckModel,
    ClaimModel,
    EvidenceAnalysisModel,
    EvidenceModel,
    SourceModel,
    UserModel,
    VerdictModel,
)
from app.domain.claims import Claim
from app.domain.schemas import Evidence, EvidenceAnalysis, Source
from app.domain.verdict import Verdict


@dataclass(frozen=True)
class ClaimCheckResult:
    claim: Claim
    sources: Sequence[Source]
    evidence: Sequence[Evidence]
    analysis: EvidenceAnalysis
    verdict: Verdict


class CheckRepository:
    """Persistence boundary for a complete fact-check result."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_check(
        self,
        *,
        telegram_id: int,
        status: str,
        input_type: str,
        input_hash: str,
        pipeline_version: str,
        model_version: str,
        claims: Sequence[ClaimCheckResult],
    ) -> CheckModel:
        user = await self._get_or_create_user(telegram_id)
        check = CheckModel(
            user_id=user.id,
            status=status,
            input_type=input_type,
            input_hash=input_hash,
            pipeline_version=pipeline_version,
            model_version=model_version,
            completed_at=datetime.now(UTC) if status == "COMPLETED" else None,
        )
        self._session.add(check)
        await self._session.flush()
        await self._store_claims(check, claims)
        await self._session.flush()
        return check

    async def create_queued_check(
        self,
        *,
        telegram_id: int,
        input_type: str,
        input_hash: str,
        pipeline_version: str,
        model_version: str,
        job_payload: dict[str, object],
    ) -> CheckModel:
        user = await self._get_or_create_user(telegram_id)
        check = CheckModel(
            user_id=user.id,
            status="QUEUED",
            input_type=input_type,
            input_hash=input_hash,
            pipeline_version=pipeline_version,
            model_version=model_version,
            job_payload=job_payload,
        )
        self._session.add(check)
        await self._session.flush()
        return check

    async def complete_check(
        self, check_id: int, claims: Sequence[ClaimCheckResult]
    ) -> CheckModel | None:
        check = await self.get_check_with_details(check_id)
        if check is None or check.status == "CANCELLED":
            return None
        for claim in list(check.claims):
            await self._session.delete(claim)
        await self._session.flush()
        check.status = "COMPLETED"
        check.completed_at = datetime.now(UTC)
        check.last_error = None
        await self._store_claims(check, claims)
        await self._session.flush()
        return check

    async def fail_check(self, check_id: int, error: str) -> None:
        check = await self._session.get(CheckModel, check_id)
        if check is not None:
            check.status = "FAILED"
            check.last_error = error[:500]
            await self._session.flush()

    async def mark_processing(self, check_id: int) -> None:
        check = await self._session.get(CheckModel, check_id)
        if check is not None and check.status == "QUEUED":
            check.status = "PROCESSING"
            check.attempt_count += 1
            await self._session.flush()

    async def get_active_check(self, telegram_id: int) -> CheckModel | None:
        result = await self._session.execute(
            select(CheckModel)
            .join(UserModel, UserModel.id == CheckModel.user_id)
            .where(
                UserModel.telegram_id == telegram_id,
                CheckModel.status.in_(("QUEUED", "PROCESSING")),
            )
            .order_by(CheckModel.created_at.desc(), CheckModel.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def cancel_check(self, check_id: int) -> CheckModel | None:
        check = await self._session.get(CheckModel, check_id)
        if check is not None and check.status in {"QUEUED", "PROCESSING"}:
            check.status = "CANCELLED"
            check.last_error = None
            await self._session.flush()
        return check

    async def set_job_payload(self, check_id: int, payload: dict[str, object]) -> None:
        check = await self._session.get(CheckModel, check_id)
        if check is not None:
            check.job_payload = payload
            await self._session.flush()

    async def _store_claims(self, check: CheckModel, claims: Sequence[ClaimCheckResult]) -> None:
        for position, result in enumerate(claims):
            claim_model = ClaimModel(
                check_id=check.id,
                claim_key=result.claim.claim_id,
                text=result.claim.text,
                claim_type=result.claim.claim_type.value,
                category=result.claim.category.value,
                extraction_confidence=result.claim.confidence,
                claim_order=position,
            )
            self._session.add(claim_model)
            await self._session.flush()
            source_models: dict[str, SourceModel] = {}
            for source in result.sources:
                source_key = source.source_id or self._source_key(str(source.url))
                source_model = SourceModel(
                    claim_id=claim_model.id,
                    source_key=source_key,
                    url=str(source.url),
                    title=source.title,
                    domain=source.domain,
                    source_type=source.source_type.value,
                    authority_level=source.authority_level.value,
                    relevance_score=source.relevance_score,
                    quality_score=source.quality_score,
                    published_at=source.published_at,
                    retrieved_at=source.retrieved_at,
                    content_status=source.content_status.value,
                    fetch_error=source.fetch_error,
                )
                self._session.add(source_model)
                source_models[source_key] = source_model
            await self._session.flush()
            for item in result.evidence:
                matched_source = source_models.get(item.source_id)
                if matched_source is None:
                    continue
                self._session.add(
                    EvidenceModel(
                        claim_id=claim_model.id,
                        source_id=matched_source.id,
                        evidence_text=item.evidence_text,
                        evidence_summary=item.evidence_summary,
                        relation=item.relation.value,
                        evidence_strength=item.evidence_strength.value,
                        directness=item.directness.value,
                        scope=item.scope.value,
                        usable=item.usable,
                        limitations=item.limitations,
                    )
                )
            self._session.add(
                EvidenceAnalysisModel(
                    claim_id=claim_model.id,
                    overall_evidence_strength=result.analysis.overall_evidence_strength.value,
                    evidence_consistency=result.analysis.evidence_consistency.value,
                    conflict_detected=result.analysis.conflict_detected,
                    analysis_failed=result.analysis.analysis_failed,
                    supporting_evidence=result.analysis.supporting_evidence,
                    contradicting_evidence=result.analysis.contradicting_evidence,
                    neutral_evidence=result.analysis.neutral_evidence,
                    limitations=result.analysis.limitations,
                )
            )
            self._session.add(
                VerdictModel(
                    claim_id=claim_model.id,
                    status=result.verdict.status.value,
                    confidence=result.verdict.confidence,
                    short_reason=result.verdict.short_reason,
                    detailed_reason=_persisted_detailed_reason(result.verdict),
                    evidence_ids=result.verdict.evidence_ids,
                    source_ids=result.verdict.source_ids,
                    limitations=result.verdict.limitations,
                )
            )
        await self._session.flush()

    async def get_check_with_details(self, check_id: int) -> CheckModel | None:
        result = await self._session.execute(
            select(CheckModel)
            .where(CheckModel.id == check_id)
            .options(
                selectinload(CheckModel.claims).selectinload(ClaimModel.sources),
                selectinload(CheckModel.claims).selectinload(ClaimModel.evidence),
                selectinload(CheckModel.claims).selectinload(ClaimModel.analysis),
                selectinload(CheckModel.claims).selectinload(ClaimModel.verdict),
            )
        )
        return result.scalar_one_or_none()

    async def get_user_by_telegram_id(self, telegram_id: int) -> UserModel | None:
        result = await self._session.execute(
            select(UserModel).where(UserModel.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def get_user_history(
        self, telegram_id: int, *, offset: int = 0, limit: int = 5
    ) -> tuple[list[CheckModel], bool]:
        user = await self.get_user_by_telegram_id(telegram_id)
        if user is None:
            return [], False
        result = await self._session.execute(
            select(CheckModel)
            .where(CheckModel.user_id == user.id)
            .order_by(CheckModel.created_at.desc(), CheckModel.id.desc())
            .offset(max(0, offset))
            .limit(limit + 1)
            .options(selectinload(CheckModel.claims).selectinload(ClaimModel.verdict))
        )
        items = list(result.scalars().all())
        return items[:limit], len(items) > limit

    async def get_user_check_with_details(
        self, telegram_id: int, check_id: int
    ) -> CheckModel | None:
        result = await self._session.execute(
            select(CheckModel)
            .join(UserModel, UserModel.id == CheckModel.user_id)
            .where(UserModel.telegram_id == telegram_id, CheckModel.id == check_id)
            .options(
                selectinload(CheckModel.claims).selectinload(ClaimModel.sources),
                selectinload(CheckModel.claims).selectinload(ClaimModel.evidence),
                selectinload(CheckModel.claims).selectinload(ClaimModel.analysis),
                selectinload(CheckModel.claims).selectinload(ClaimModel.verdict),
            )
        )
        return result.scalar_one_or_none()

    async def get_user_checks(self, user_id: int, limit: int = 20) -> list[CheckModel]:
        result = await self._session.execute(
            select(CheckModel)
            .where(CheckModel.user_id == user_id)
            .order_by(CheckModel.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def _get_or_create_user(self, telegram_id: int) -> UserModel:
        result = await self._session.execute(
            select(UserModel).where(UserModel.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            user = UserModel(telegram_id=telegram_id)
            self._session.add(user)
            await self._session.flush()
        return user

    @staticmethod
    def _source_key(url: str) -> str:
        return sha256(url.encode()).hexdigest()[:16]


class CheckPersistenceService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def persist(
        self,
        *,
        telegram_id: int,
        input_type: str,
        input_hash: str,
        pipeline_version: str,
        model_version: str,
        claims: Sequence[ClaimCheckResult],
    ) -> int:
        async with self._session_factory() as session:
            async with session.begin():
                check = await CheckRepository(session).create_check(
                    telegram_id=telegram_id,
                    status="COMPLETED",
                    input_type=input_type,
                    input_hash=input_hash,
                    pipeline_version=pipeline_version,
                    model_version=model_version,
                    claims=claims,
                )
            return check.id

    async def create_queued(
        self,
        *,
        telegram_id: int,
        input_type: str,
        input_hash: str,
        pipeline_version: str,
        model_version: str,
        job_payload: dict[str, object],
    ) -> int:
        async with self._session_factory() as session:
            async with session.begin():
                check = await CheckRepository(session).create_queued_check(
                    telegram_id=telegram_id,
                    input_type=input_type,
                    input_hash=input_hash,
                    pipeline_version=pipeline_version,
                    model_version=model_version,
                    job_payload=job_payload,
                )
            return check.id

    async def complete(self, check_id: int, claims: Sequence[ClaimCheckResult]) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                check = await CheckRepository(session).complete_check(check_id, claims)
            return check is not None

    async def mark_processing(self, check_id: int) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await CheckRepository(session).mark_processing(check_id)

    async def get_active(self, telegram_id: int) -> CheckModel | None:
        async with self._session_factory() as session:
            return await CheckRepository(session).get_active_check(telegram_id)

    async def cancel(self, check_id: int) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                check = await CheckRepository(session).cancel_check(check_id)
            return check is not None and check.status == "CANCELLED"

    async def set_job_payload(self, check_id: int, payload: dict[str, object]) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await CheckRepository(session).set_job_payload(check_id, payload)

    async def fail(self, check_id: int, error: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await CheckRepository(session).fail_check(check_id, error)


def _persisted_detailed_reason(verdict: Verdict) -> str:
    sections: list[str] = []
    if verdict.supported_summary:
        sections.append(f"Что удалось установить: {verdict.supported_summary}")
    if verdict.unresolved_summary:
        sections.append(f"Что не установлено: {verdict.unresolved_summary}")
    sections.append(verdict.detailed_reason)
    return "\n".join(sections)
