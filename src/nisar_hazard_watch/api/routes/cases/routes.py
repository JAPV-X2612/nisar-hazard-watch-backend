from typing import Annotated

from fastapi import APIRouter, Path
from fastapi.responses import RedirectResponse

from nisar_hazard_watch.api.dependencies import CaseServiceDep, RateLimit
from nisar_hazard_watch.constants.cases import CASE_ID_PATTERN
from nisar_hazard_watch.models.case import CasesView, CaseView

router = APIRouter(tags=["cases"])

CaseId = Annotated[str, Path(pattern=CASE_ID_PATTERN)]
LayerId = Annotated[str, Path(pattern=r"^[A-Za-z0-9._-]{1,120}$")]


@router.get("", response_model=CasesView, dependencies=[RateLimit])
async def list_cases(service: CaseServiceDep) -> CasesView:
    return await service.cases()


@router.get("/{case_id}", response_model=CaseView, dependencies=[RateLimit])
async def get_case(case_id: CaseId, service: CaseServiceDep) -> CaseView:
    return await service.get(case_id=case_id)


# Not rate-limited: opening one case asks for every one of its layers at once.
@router.get("/{case_id}/layers/{layer_id}", response_class=RedirectResponse)
async def get_case_layer(
    case_id: CaseId, layer_id: LayerId, service: CaseServiceDep
) -> RedirectResponse:
    url = await service.layer_url(case_id=case_id, layer_id=layer_id)
    return RedirectResponse(url=url, status_code=307)
