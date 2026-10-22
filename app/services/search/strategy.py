import re

from app.domain.claims import Claim, ClaimCategory
from app.domain.enums import ClaimType
from app.domain.search import SearchStrategy


def choose_strategies(claim: Claim) -> list[SearchStrategy]:
    text = (claim.normalized_text or claim.text).casefold()
    strategies = [SearchStrategy.PRIMARY, SearchStrategy.NEUTRAL, SearchStrategy.COUNTER]
    if claim.claim_type in {ClaimType.MEDICAL_CLAIM, ClaimType.FACT, ClaimType.ADVICE}:
        strategies.extend([SearchStrategy.AUTHORITATIVE, SearchStrategy.RESEARCH])
    if claim.category is ClaimCategory.TRANSMISSION or any(
        term in text for term in ("передав", "зараз", "transmi", "infection")
    ):
        strategies.extend([SearchStrategy.AUTHORITATIVE, SearchStrategy.COUNTER])
    if re.search(r"risk|harm|side effect|опасн|вред|побочн|риск", text):
        strategies.append(SearchStrategy.SAFETY_RISKS)
    return list(dict.fromkeys(strategies))
