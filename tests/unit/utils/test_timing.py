import time

from nisar_hazard_watch.utils.timing import elapsed_ms


def test_elapsed_ms_is_a_rounded_positive_number_of_milliseconds() -> None:
    # Arrange
    started = time.perf_counter() - 0.25

    # Act
    result = elapsed_ms(started)

    # Assert
    assert 250 <= result < 1000
    assert result == round(result, 1)
