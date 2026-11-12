import time


def elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)
