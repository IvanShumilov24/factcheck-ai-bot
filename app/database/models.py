from datetime import UTC, datetime

from sqlalchemy import JSON, BigInteger, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin


class UserModel(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)


class CheckModel(Base):
    __tablename__ = "checks"
    __table_args__ = (
        Index("ix_checks_user_id", "user_id"),
        Index("ix_checks_created_at", "created_at"),
        Index("ix_checks_input_hash", "input_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    input_type: Mapped[str] = mapped_column(String(32), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pipeline_version: Mapped[str] = mapped_column(String(32), nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    job_payload: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped[UserModel | None] = relationship()
    claims: Mapped[list["ClaimModel"]] = relationship(
        back_populates="check", cascade="all, delete-orphan"
    )


class ClaimModel(Base):
    __tablename__ = "claims"
    __table_args__ = (Index("ix_claims_check_id", "check_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    check_id: Mapped[int] = mapped_column(
        ForeignKey("checks.id", ondelete="CASCADE"), nullable=False
    )
    claim_key: Mapped[str] = mapped_column(String(64), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    claim_type: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False, default="UNKNOWN")
    extraction_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    claim_order: Mapped[int] = mapped_column(Integer, nullable=False)

    check: Mapped[CheckModel] = relationship(back_populates="claims")
    sources: Mapped[list["SourceModel"]] = relationship(
        back_populates="claim", cascade="all, delete-orphan"
    )
    evidence: Mapped[list["EvidenceModel"]] = relationship(
        back_populates="claim", cascade="all, delete-orphan"
    )
    analysis: Mapped["EvidenceAnalysisModel | None"] = relationship(
        back_populates="claim", cascade="all, delete-orphan", uselist=False
    )
    verdict: Mapped["VerdictModel | None"] = relationship(
        back_populates="claim", cascade="all, delete-orphan", uselist=False
    )


class SourceModel(Base):
    __tablename__ = "sources"
    __table_args__ = (Index("ix_sources_claim_id", "claim_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[int] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), nullable=False
    )
    source_key: Mapped[str] = mapped_column(String(64), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    authority_level: Mapped[str] = mapped_column(String(32), nullable=False)
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_status: Mapped[str] = mapped_column(String(32), nullable=False)
    fetch_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    claim: Mapped[ClaimModel] = relationship(back_populates="sources")
    evidence: Mapped[list["EvidenceModel"]] = relationship(back_populates="source")


class EvidenceModel(Base):
    __tablename__ = "evidence"
    __table_args__ = (
        Index("ix_evidence_claim_id", "claim_id"),
        Index("ix_evidence_source_id", "source_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[int] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_summary: Mapped[str] = mapped_column(Text, nullable=False)
    relation: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_strength: Mapped[str] = mapped_column(String(32), nullable=False)
    directness: Mapped[str] = mapped_column(String(32), nullable=False)
    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    usable: Mapped[bool] = mapped_column(nullable=False)
    limitations: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    claim: Mapped[ClaimModel] = relationship(back_populates="evidence")
    source: Mapped[SourceModel] = relationship(back_populates="evidence")


class EvidenceAnalysisModel(Base):
    __tablename__ = "evidence_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[int] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    overall_evidence_strength: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_consistency: Mapped[str] = mapped_column(String(32), nullable=False)
    conflict_detected: Mapped[bool] = mapped_column(nullable=False)
    analysis_failed: Mapped[bool] = mapped_column(nullable=False, default=False)
    supporting_evidence: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    contradicting_evidence: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    neutral_evidence: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    limitations: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    claim: Mapped[ClaimModel] = relationship(back_populates="analysis")


class VerdictModel(Base):
    __tablename__ = "verdicts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[int] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    short_reason: Mapped[str] = mapped_column(Text, nullable=False)
    detailed_reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    source_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    limitations: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    claim: Mapped[ClaimModel] = relationship(back_populates="verdict")
