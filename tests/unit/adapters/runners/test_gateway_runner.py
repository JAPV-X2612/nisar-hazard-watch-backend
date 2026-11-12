import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from nisar_hazard_watch.adapters.runners.gateway_runner import GatewayRunner
from nisar_hazard_watch.constants.explorations import Lens, RunnerState
from nisar_hazard_watch.constants.sar import Configuration, Maturity
from nisar_hazard_watch.exceptions.exploration_errors import QueueFullError, RunnerUnavailableError
from nisar_hazard_watch.ports.analysis_runner import InsarSelection, RunnerJob
from tests.factories import make_plan, make_scene, make_series

FIXTURE = Path(__file__).parents[3] / "fixtures" / "ml_gateway_job.json"
BASE_URL = "https://gateway.example.test"
RUN_ID = "669a471d5c234a7b838d41715ff519fc"
FOREIGN_LAYER_URL = "https://evil.example.test/layer.png"


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


async def test_an_unknown_job_on_submit_is_an_unavailable_service_not_a_lost_job() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=404, json={"detail": "Not Found"})

    # Act / Assert
    with pytest.raises(expected_exception=RunnerUnavailableError):
        await _run(handler, lambda runner: runner.submit(job=_job()))


async def test_a_lost_job_keeps_the_id_it_was_polled_with() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=404, content=b"<html>Not Found</html>")

    # Act
    ticket = await _run(handler, lambda runner: runner.poll(run_id=RUN_ID))

    # Assert
    assert ticket.run_id == RUN_ID
    assert ticket.state is RunnerState.FAILED
    assert ticket.error_code == "job_not_found"


async def test_the_run_id_is_encoded_into_a_single_path_segment() -> None:
    # Arrange
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(status_code=200, json={"job_id": RUN_ID, "status": "queued"})

    # Act
    await _run(handler, lambda runner: runner.poll(run_id="../admin?x=1"))

    # Assert
    assert sent[0].url.raw_path == b"/v2/jobs/..%2Fadmin%3Fx%3D1"


@pytest.mark.parametrize(
    argnames="body",
    argvalues=[
        [{"status": "succeeded"}],
        {"job_id": RUN_ID, "status": "teleported"},
        {"job_id": RUN_ID, "status": ["queued"]},
        {"job_id": RUN_ID, "status": "succeeded", "result": {"layers": [{"id": "display_x"}]}},
        {"job_id": RUN_ID, "status": "succeeded", "result": {"elapsed_seconds": "soon"}},
    ],
    ids=[
        "not-an-object",
        "unknown-status",
        "unhashable-status",
        "layer-without-bounds",
        "bad-number",
    ],
)
async def test_a_malformed_answer_is_an_unavailable_service_never_a_crash(body: object) -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, json=body)

    # Act / Assert
    with pytest.raises(expected_exception=RunnerUnavailableError):
        await _run(handler, lambda runner: runner.poll(run_id=RUN_ID))


@pytest.mark.parametrize(
    argnames="png_url",
    argvalues=[
        FOREIGN_LAYER_URL,
        "//evil.example.test/layer.png",
        "http://gateway.example.test/x.png",
    ],
    ids=["other-host", "scheme-relative-other-host", "other-scheme"],
)
async def test_a_layer_served_from_another_origin_is_never_trusted(png_url: str) -> None:
    # Arrange
    payload = _fixture()
    payload["result"]["layers"][0]["png_url"] = png_url

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, json=payload)

    # Act / Assert
    with pytest.raises(expected_exception=RunnerUnavailableError):
        await _run(handler, lambda runner: runner.poll(run_id=RUN_ID))


INSAR_FIXTURE = Path(__file__).parents[3] / "fixtures" / "ml_gateway_insar_pair_job.json"
KUMAMOTO_PAIR = (
    "NISAR_L2_PR_GUNW_026_024_A_018_028_4000_SH_20260721T202900_20260721T202934_"
    "20260814T202858_20260814T202933_P05023_N_F_J_001"
)
INSAR_RUN_ID = "c8c891da8469426c8a40ba60eb9612ea"
COHERENT_CELLS = 62500
PHASE_CELLS = 39584
MEDIAN_COHERENCE = 0.42586714029312134


def _insar_job(threshold: float = 0.35) -> RunnerJob:
    plan = make_plan(
        scenes=[],
        window_start=datetime(2026, 7, 21, tzinfo=UTC),
        window_end=datetime(2026, 8, 14, tzinfo=UTC),
    )
    return RunnerJob(
        lens=Lens.INSAR,
        plan=plan,
        pair=InsarSelection(pair_id=KUMAMOTO_PAIR, coherence_threshold=threshold),
    )


def _insar_answer(**science: object) -> dict:
    answer = json.loads(INSAR_FIXTURE.read_text())
    answer["result"]["science"] = {**answer["result"]["science"], **science}
    return answer


async def test_an_insar_pair_is_sent_as_the_pair_the_window_and_the_threshold() -> None:
    # Arrange
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(status_code=202, json={"job_id": INSAR_RUN_ID, "status": "queued"})

    # Act
    await _run(handler, lambda runner: runner.submit(job=_insar_job(threshold=0.5)))

    # Assert
    body = json.loads(sent[0].content)
    assert body["operation"] == "insar-pair"
    assert body["pair_id"] == KUMAMOTO_PAIR
    assert (body["start_date"], body["end_date"]) == ("2026-07-21", "2026-08-14")
    assert body["coherence_threshold"] == 0.5
    assert {"scenes", "lens", "aoi", "window_pixels"}.isdisjoint(body)


async def test_a_real_insar_answer_becomes_two_layers_and_a_summary_with_no_displacement() -> None:
    # Arrange
    answer = json.loads(INSAR_FIXTURE.read_text())
    handler = lambda request: httpx.Response(status_code=200, json=answer)  # noqa: E731

    # Act
    ticket = await _run(handler, lambda runner: runner.poll(run_id=INSAR_RUN_ID))

    # Assert
    assert ticket.state is RunnerState.SUCCEEDED
    result = ticket.result
    assert result is not None
    assert result.science_status == "complete"
    assert result.lens is None
    assert [row["date"] for row in result.observations] == ["2026-07-21", "2026-08-14"]
    assert [layer.title for layer in result.layers] == [
        "Interferometric coherence",
        "Wrapped phase",
    ]
    assert [layer.kind for layer in result.layers] == ["coherence", "phase"]
    assert result.layers[1].colormap == "twilight"
    assert result.layers[1].value_range == pytest.approx((-3.1415926536, 3.1415926536))
    summary = result.insar
    assert summary is not None
    assert summary.pair_id == KUMAMOTO_PAIR
    assert summary.polarization == "HH"
    assert summary.median_coherence == MEDIAN_COHERENCE
    assert (summary.coherent_cells, summary.phase_cells) == (COHERENT_CELLS, PHASE_CELLS)
    assert summary.window_cells == COHERENT_CELLS
    assert summary.point_wrapped_phase_rad is None
    assert summary.corrections_applied == []
    assert summary.los_displacement_cm is None
    assert result.quality["postingMeters"] == 20.0
    assert result.timings["measure_s"] > 0


async def test_a_pair_the_catalog_no_longer_lists_is_a_no_data_answer_without_layers() -> None:
    # Arrange
    answer = _insar_answer(status="no_data", reason="pair_unavailable")
    answer["result"]["science_status"] = "no_data"
    answer["result"]["layers"] = []
    answer["result"]["science"].pop("grid", None)
    handler = lambda request: httpx.Response(status_code=200, json=answer)  # noqa: E731

    # Act
    ticket = await _run(handler, lambda runner: runner.poll(run_id=INSAR_RUN_ID))

    # Assert
    assert ticket.result is not None
    assert ticket.result.science_status == "no_data"
    assert ticket.result.layers == []
    assert ticket.result.observations == []
    assert ticket.result.insar is not None
    assert ticket.result.insar.reason == "pair_unavailable"
    assert ticket.result.insar.window_cells is None
