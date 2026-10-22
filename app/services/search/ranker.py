from app.domain.schemas import Source


class SourceRanker:
    """Ranks source quality and search relevance, never claim truth."""

    def rank(self, sources: list[Source]) -> list[Source]:
        return sorted(
            sources,
            key=lambda source: (
                0.65 * source.quality_score + 0.35 * source.relevance_score,
                source.published_at is not None,
            ),
            reverse=True,
        )
