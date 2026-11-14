import logging
import re
from http import HTTPStatus
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
from pydantic import ValidationError

from nisar_hazard_watch.constants.cases import (
    CASES_PATH,
    CASES_UNAVAILABLE_DETAIL,
    FORBIDDEN_EVIDENCE_WORDS,
)
from nisar_hazard_watch.exceptions.case_errors import CasesUnavailableError
from nisar_hazard_watch.models.case import CaseView

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

    def _url(self, path: str) -> str:
        url = urljoin(self._base_url + "/", path)
        if urlsplit(url)[:2] != urlsplit(self._base_url)[:2]:
            raise ValueError(f"layer URL {url!r} is not served by the ML gateway")
        return url

    def _layer(self, layer: dict[str, Any]) -> dict[str, Any]:
        return {
            **layer,
            "url": self._url(path=str(layer["png_url"])),
            "value_range": layer.get("range"),
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
                    self._layer(layer=view) for view in item.get("visualizations") or []
                ],
                "is_demo": item["isDemo"],
                "limitations": evidence.get("limitations") or [],
            }
        )
