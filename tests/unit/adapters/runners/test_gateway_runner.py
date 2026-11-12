import json
from pathlib import Path

import httpx
import pytest

from nisar_hazard_watch.adapters.runners.gateway_runner import GatewayRunner
from nisar_hazard_watch.constants.explorations import Lens, RunnerState
from nisar_hazard_watch.constants.sar import Configuration, Maturity
from nisar_hazard_watch.exceptions.exploration_errors import QueueFullError, RunnerUnavailableError
from nisar_hazard_watch.ports.analysis_runner import RunnerJob
from tests.factories import make_plan, make_scene, make_series

FIXTURE = Path(__file__).parents[3] / "fixtures" / "ml_gateway_job.json"
BASE_URL = "https://gateway.example.test"
RUN_ID = "669a471d5c234a7b838d41715ff519fc"


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text())


def _job(**overrides: object) -> RunnerJob:
    return RunnerJob(lens=Lens.FLOOD_WETLAND, plan=make_plan(), **overrides)  # type: ignore[arg-type]


async def _run(handler, action):
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        return await action(GatewayRunner(client=client, base_url=BASE_URL))


async def test_the_plan_is_sent_as_granule_names_with_collections_and_a_window() -> None:
    # Arrange
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(
            status_code=202,
            json={"job_id": RUN_ID, "status": "queued", "cache": "miss", "result": None},
        )

    scenes = [
        *make_series(count=3, maturity=Maturity.PROVISIONAL),
        make_scene(
            acquired_at=make_series(count=4)[-1].acquired_at,
            maturity=Maturity.UNVALIDATED,
            configuration=Configuration.URGENT_RESPONSE,
        ),
    ]
    job = RunnerJob(lens=Lens.FLOOD_WETLAND, plan=make_plan(scenes=scenes))

    # Act
    ticket = await _run(handler, lambda runner: runner.submit(job=job))

    # Assert
    body = json.loads(sent[0].content)
    assert sent[0].url == f"{BASE_URL}/v2/jobs"
    assert body["operation"] == "explore"
    assert body["lens"] == "flood_wetland"
    assert [scene["collection"] for scene in body["scenes"]] == [
        "PROVISIONAL",
        "PROVISIONAL",
        "PROVISIONAL",
        "UR",
    ]
    assert body["window_pixels"] % 8 == 0
    assert 64 <= body["window_pixels"] <= 1024
    assert body["aoi"]["type"] == "Polygon"
    assert body["start_date"] == "2026-06-12"
    assert "optical_evidence" not in body
    assert ticket.state is RunnerState.QUEUED


async def test_optical_evidence_is_requested_only_when_asked() -> None:
    # Arrange
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(status_code=202, json={"job_id": RUN_ID, "status": "queued"})

    # Act
    await _run(handler, lambda runner: runner.submit(job=_job(optical_evidence=True)))

    # Assert
    assert json.loads(sent[0].content)["optical_evidence"] is True


async def test_a_succeeded_job_becomes_a_typed_result_with_absolute_layer_urls() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, json=_fixture())

    # Act
    ticket = await _run(handler, lambda runner: runner.poll(run_id=RUN_ID))

    # Assert
    assert ticket.state is RunnerState.SUCCEEDED
    result = ticket.result
    assert result is not None
    assert result.science_status == "complete"
    assert result.lens is not None
    assert result.lens["status"] == "evaluated"
    assert result.aoi_summary is not None
    assert result.aoi_summary["cells_in_area"] > 1_000_000
    assert [row["status"] for row in result.observations] == ["observed"] * 5
    assert result.timings["measure_s"] > 0
    assert result.timings["elapsed_s"] > result.timings["total_s"]
    assert result.quality["gridWidth"] == 1024
    observed, diagnostic = result.layers
    assert observed.kind == "observed"
    assert diagnostic.kind == "diagnostic"
    assert observed.url.startswith(f"{BASE_URL}/v2/jobs/")
    assert observed.url.endswith(".png")
    assert diagnostic.legend == {"0": "absent", "1": "present"}
    assert observed.value_range == (-30.0, 0.0)


@pytest.mark.parametrize(
    argnames=("gateway_status", "expected"),
    argvalues=[("queued", RunnerState.QUEUED), ("running", RunnerState.RUNNING)],
)
async def test_active_states_map_one_to_one(gateway_status: str, expected: RunnerState) -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, json={"job_id": RUN_ID, "status": gateway_status})

    # Act
    ticket = await _run(handler, lambda runner: runner.poll(run_id=RUN_ID))

    # Assert
    assert ticket.state is expected
    assert ticket.result is None


async def test_a_failed_job_keeps_the_service_error_code() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        body = {"job_id": RUN_ID, "status": "failed", "error": {"code": "deadline_exceeded"}}
        return httpx.Response(status_code=200, json=body)

    # Act
    ticket = await _run(handler, lambda runner: runner.poll(run_id=RUN_ID))

    # Assert
    assert ticket.state is RunnerState.FAILED
    assert ticket.error_code == "deadline_exceeded"


async def test_an_unknown_job_is_reported_as_failed_not_as_an_outage() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=404, json={"code": "job_not_found"})

    # Act
    ticket = await _run(handler, lambda runner: runner.poll(run_id=RUN_ID))

    # Assert
    assert ticket.state is RunnerState.FAILED
    assert ticket.error_code == "job_not_found"


@pytest.mark.parametrize(argnames="status", argvalues=[429, 503])
async def test_capacity_answers_become_a_queue_full_error(status: int) -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=status, json={"code": "queue_full"})

    # Act / Assert
    with pytest.raises(expected_exception=QueueFullError):
        await _run(handler, lambda runner: runner.submit(job=_job()))


@pytest.mark.parametrize(
    argnames="handler",
    argvalues=[
        lambda request: httpx.Response(status_code=500, json={"message": "boom"}),
        lambda request: httpx.Response(status_code=422, json={"code": "invalid_request"}),
        lambda request: httpx.Response(status_code=200, content=b"not json"),
        lambda request: httpx.Response(status_code=200, json={"unexpected": True}),
    ],
    ids=["server-error", "rejected", "invalid-json", "unexpected-shape"],
)
async def test_any_other_failure_is_an_unavailable_analysis_service(handler) -> None:
    # Arrange
    failing_handler = handler

    # Act / Assert
    with pytest.raises(expected_exception=RunnerUnavailableError):
        await _run(failing_handler, lambda runner: runner.submit(job=_job()))


async def test_a_network_failure_is_an_unavailable_analysis_service() -> None:
    # Arrange
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    # Act / Assert
    with pytest.raises(expected_exception=RunnerUnavailableError):
        await _run(unreachable, lambda runner: runner.poll(run_id=RUN_ID))
