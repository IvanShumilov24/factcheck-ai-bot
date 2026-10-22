import pytest
from pydantic import ValidationError

from app.domain.enums import ClaimType, Verdict
from app.domain.schemas import Claim, FactCheckResult


def test_claim_and_result_are_typed() -> None:
    claim = Claim(text="Claim", claim_type=ClaimType.MEDICAL_CLAIM)
    result = FactCheckResult(claim=claim, verdict=Verdict.CONFIRMED, confidence=90)
    assert result.verdict is Verdict.CONFIRMED
    assert result.confidence == 90


def test_confidence_is_bounded() -> None:
    claim = Claim(text="Claim", claim_type=ClaimType.FACT)
    with pytest.raises(ValidationError):
        FactCheckResult(claim=claim, verdict=Verdict.CONFIRMED, confidence=101)
