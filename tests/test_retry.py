from app.worker import _should_release_dedupe


def test_dedupe_is_kept_when_retry_is_scheduled() -> None:
    assert _should_release_dedupe(True) is False
    assert _should_release_dedupe(False) is True
