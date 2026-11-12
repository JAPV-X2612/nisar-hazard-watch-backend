import itertools
from dataclasses import asdict, dataclass
from typing import Any, Self

AOI_SIDE_KM = 10.24


@dataclass(frozen=True)
class Site:
    lat: float
    lon: float


SITES: dict[str, Site] = {
    "qadirabad": Site(lat=32.329, lon=73.713),
    "chokwe": Site(lat=-24.52, lon=32.99),
    "richmond": Site(lat=39.83, lon=-84.89),
}


@dataclass(frozen=True)
class CaseSpec:
    site: str
    threads: int = 5
    block_mb: float = 1.0
    multilook: int = 2
    n_images: int = 5
    use_mask: bool = True
    reader: str = "pyfive"

    @property
    def half_side_km(self) -> float:
        return AOI_SIDE_KM / 2

    @property
    def location(self) -> Site:
        return SITES[self.site]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(**data)


def build_matrix(
    sites: list[str],
    threads: list[int],
    readers: list[str],
    block_mb: float,
    multilook: int,
) -> list[CaseSpec]:
    return [
        CaseSpec(site=site, threads=count, reader=reader, block_mb=block_mb, multilook=multilook)
        for site, count, reader in itertools.product(sites, threads, readers)
    ]
