from typing import Annotated

from fastapi import APIRouter, Path, Response
from fastapi.responses import RedirectResponse

from nisar_hazard_watch.api.dependencies import ExplorationServiceDep, RateLimit
from nisar_hazard_watch.constants.routes import LAYER_ID_PATTERN
from nisar_hazard_watch.models.exploration import ExplorationRequest, ExplorationView

router = APIRouter(tags=["explorations"])

ExplorationId = Annotated[str, Path(pattern=r"^exp_[0-9a-f]{16}$")]
LayerId = Annotated[str, Path(pattern=LAYER_ID_PATTERN)]


@router.post(
    "",
    response_model=ExplorationView,
    status_code=202,
    responses={200: {"model": ExplorationView}},
    dependencies=[RateLimit],
)
async def create_exploration(
    body: ExplorationRequest, service: ExplorationServiceDep, response: Response
) -> ExplorationView:
    view, final = await service.create(request=body)
    if final:
        response.status_code = 200
    return view


@router.get("/{exploration_id}", response_model=ExplorationView)
async def get_exploration(
    exploration_id: ExplorationId, service: ExplorationServiceDep
) -> ExplorationView:
    return await service.get(exploration_id=exploration_id)


@router.delete("/{exploration_id}", response_model=ExplorationView)
async def cancel_exploration(
    exploration_id: ExplorationId, service: ExplorationServiceDep
) -> ExplorationView:
    return await service.cancel(exploration_id=exploration_id)


@router.get("/{exploration_id}/layers/{layer_id}", response_class=RedirectResponse)
async def get_layer(
    exploration_id: ExplorationId, layer_id: LayerId, service: ExplorationServiceDep
) -> RedirectResponse:
    url = await service.layer_url(exploration_id=exploration_id, layer_id=layer_id)
    return RedirectResponse(url=url, status_code=307)
