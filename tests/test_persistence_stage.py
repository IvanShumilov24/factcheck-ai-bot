from app.database.base import Base
from app.database.models import (
    CheckModel,
    ClaimModel,
    EvidenceAnalysisModel,
    EvidenceModel,
    SourceModel,
    VerdictModel,
)
from app.domain.enums import EvidenceRelation, EvidenceStrength
from app.domain.enums import Verdict as VerdictStatus
from app.domain.schemas import Evidence, Source
from app.domain.verdict import Verdict


def test_stage6_tables_and_cascade_foreign_keys_are_declared() -> None:
    tables = Base.metadata.tables
    assert {
        "checks",
        "claims",
        "sources",
        "evidence",
        "evidence_analyses",
        "verdicts",
    } <= set(tables)
    assert next(iter(ClaimModel.__table__.c.check_id.foreign_keys)).ondelete == "CASCADE"
    assert next(iter(SourceModel.__table__.c.claim_id.foreign_keys)).ondelete == "CASCADE"
    assert next(iter(EvidenceModel.__table__.c.source_id.foreign_keys)).ondelete == "CASCADE"
    assert next(iter(EvidenceAnalysisModel.__table__.c.claim_id.foreign_keys)).ondelete == "CASCADE"
    assert next(iter(VerdictModel.__table__.c.claim_id.foreign_keys)).ondelete == "CASCADE"
    assert "ix_checks_input_hash" in {index.name for index in CheckModel.__table__.indexes}


def test_verdict_and_evidence_models_keep_report_fields() -> None:
    source = Source(
        source_id="source-1",
        title="WHO",
        url="https://www.who.int/example",
        domain="www.who.int",
    )
    evidence = Evidence(
        claim_id="claim-1",
        source_id="source-1",
        source_url=source.url,
        source_title=source.title,
        evidence_text="The source text.",
        evidence_summary="Summary.",
        relation=EvidenceRelation.SUPPORTS,
        evidence_strength=EvidenceStrength.STRONG,
        limitations=["Limited population"],
    )
    verdict = Verdict(
        claim_id="claim-1",
        status=VerdictStatus.CONFIRMED,
        confidence=0.9,
        short_reason="Supported.",
        detailed_reason="Supported by the source.",
        evidence_ids=["evidence-1"],
        source_ids=["source-1"],
    )
    assert evidence.limitations == ["Limited population"]
    assert verdict.status is VerdictStatus.CONFIRMED
