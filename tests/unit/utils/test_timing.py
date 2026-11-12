import time

from nisar_hazard_watch.utils.timing import elapsed_ms

SECONDS_AGO = 0.25
MIN_ELAPSED_MS = 250
MAX_ELAPSED_MS = 1000


def test_elapsed_ms_is_a_rounded_positive_number_of_milliseconds() -> None:
    # Arrange
    started = time.perf_counter() - SECONDS_AGO

    # Act
    result = elapsed_ms(started=started)

    # Assert
    assert MIN_ELAPSED_MS <= result < MAX_ELAPSED_MS
    assert result == round(result, 1)
