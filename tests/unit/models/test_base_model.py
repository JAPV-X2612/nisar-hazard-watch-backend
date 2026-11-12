from nisar_hazard_watch.models.base_model import CamelModel

LATENCY_MS = 1.5
REASON_CODE = "NOT_FOUND"


class SampleDto(CamelModel):
    latency_ms: float
    reason_code: str


def test_fields_serialize_in_camel_case() -> None:
    # Arrange
    dto = SampleDto(latency_ms=LATENCY_MS, reason_code=REASON_CODE)

    # Act
    payload = dto.model_dump()

    # Assert
    assert payload == {"latencyMs": LATENCY_MS, "reasonCode": REASON_CODE}


def test_models_accept_both_camel_and_snake_case_input() -> None:
    # Arrange
    camel_input = {"latencyMs": LATENCY_MS, "reasonCode": REASON_CODE}

    # Act
    from_camel = SampleDto.model_validate(camel_input)
    from_snake = SampleDto(latency_ms=LATENCY_MS, reason_code=REASON_CODE)

    # Assert
    assert from_camel == from_snake
