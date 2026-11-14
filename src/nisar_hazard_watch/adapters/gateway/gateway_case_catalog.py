import logging
import re
from http import HTTPStatus
from typing import Any

import httpx
from pydantic import ValidationError

from nisar_hazard_watch.constants.cases import (
    CASE_FALLBACK_LIMITATIONS,
    CASES_PATH,
    CASES_UNAVAILABLE_DETAIL,
    FORBIDDEN_EVIDENCE_WORDS,
)
from nisar_hazard_watch.exceptions.case_errors import CasesUnavailableError
from nisar_hazard_watch.models.case import CaseView
from nisar_hazard_watch.utils.gateway_layers import gateway_url, layer_kind, layer_title

logger = logging.getLogger(__name__)

WORD = re.compile(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])")
# Provenance holds kilobytes of optical tags and licence text per case; the dates, family and
# checksum next to it are enough to cite the reference.
DROPPED_REFERENCE_KEYS = ("provenance",)


def _is_forbidden(key: str) -> bool:
    return bool({word.lower() for word in WORD.findall(key)} & FORBIDDEN_EVIDENCE_WORDS)


def _scrub(value: Any) -> Any:
    """Second guard behind the DTO: nested science keys change often and are relayed as JSON."""
    if isinstance(value, dict):
        return {key: _scrub(item) for key, item in value.items() if not _is_forbidden(str(key))}
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    return value


def _file_name(path: str) -> str:
    return path.rsplit("/", 1)[-1]


class GatewayCaseCatalog:
    """The known cases measured ahead of time and served by the ML gateway."""

    def __init__(self, client: httpx.AsyncClient, base_url: str) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")

    async def cases(self) -> list[CaseView]:
        try:
            response = await self._client.get(self._base_url + CASES_PATH)
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("known cases request failed: %s", type(exc).__name__)
            raise CasesUnavailableError(CASES_UNAVAILABLE_DETAIL) from exc
        if response.status_code != HTTPStatus.OK or not isinstance(payload, list):
            logger.warning("known cases answered %s", response.status_code)
            raise CasesUnavailableError(CASES_UNAVAILABLE_DETAIL)
        found: list[CaseView] = []
        for item in payload:
            try:
                found.append(self._case(item=item))
            except (KeyError, TypeError, ValueError, ValidationError):
                logger.warning("skipped a malformed known case")
        if not found:
            raise CasesUnavailableError(CASES_UNAVAILABLE_DETAIL)
        return found

    def _image(self, image: dict[str, Any]) -> dict[str, Any]:
        return {
            **image,
            "url": gateway_url(base_url=self._base_url, path=str(image["png_url"])),
            "value_range": image.get("range"),
        }

    def _visualization(self, view: dict[str, Any]) -> dict[str, Any]:
        cog = view.get("cog_url")
        return {
            **self._image(image=view),
            "png": _file_name(str(view["png_url"])),
            "cog": _file_name(str(cog)) if cog else None,
        }

    def _layer(self, layer: dict[str, Any]) -> dict[str, Any]:
        # Named like the exploration layers, so the front can draw both with one schema.
        identifier = str(layer["id"])
        return {
            **self._image(image=layer),
            "title": layer_title(identifier),
            "kind": layer_kind(identifier),
        }

    def _case(self, item: dict[str, Any]) -> CaseView:
        evidence = dict(item["evidence"])
        reference = evidence.get("independent_reference")
        if isinstance(reference, dict):
            evidence["independent_reference"] = {
                key: value for key, value in reference.items() if key not in DROPPED_REFERENCE_KEYS
            }
        evidence = _scrub(evidence)
        return CaseView.model_validate(
            {
                "id": item["id"],
                "title": item["title"],
                "point": item["point"],
                "status": item["status"],
                "baseline_dates": item["baseline_dates"],
                "assessment_dates": item["assessment_dates"],
                "grid": item["grid"],
                "series_key": item["series_key"],
                "evidence": evidence,
                "layers": [self._layer(layer=layer) for layer in item["layers"]],
                "visualizations": [
                    self._visualization(view=view) for view in item.get("visualizations") or []
                ],
                "is_demo": item["isDemo"],
                "limitations": evidence.get("limitations") or list(CASE_FALLBACK_LIMITATIONS),
            }
        )
