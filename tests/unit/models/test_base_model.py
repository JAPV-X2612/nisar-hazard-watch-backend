from nisar_hazard_watch.models.base_model import CamelModel


class SampleDto(CamelModel):
    latency_ms: float
    reason_code: str


def test_fields_serialize_in_camel_case() -> None:
    # Arrange
    dto = SampleDto(latency_ms=1.5, reason_code="NOT_FOUND")

    # Act
    payload = dto.model_dump()

    # Assert
    assert payload == {"latencyMs": 1.5, "reasonCode": "NOT_FOUND"}


def test_models_accept_both_camel_and_snake_case_input() -> None:
    # Arrange / Act
    from_camel = SampleDto.model_validate({"latencyMs": 2.0, "reasonCode": "A"})
    from_snake = SampleDto(latency_ms=2.0, reason_code="A")

    # Assert
    assert from_camel == from_snake
