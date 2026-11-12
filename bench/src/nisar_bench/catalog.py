from datetime import UTC, datetime, timedelta
from typing import Any

import asf_search as asf
import pandas as pd

DAYS_PER_MONTH = 30.4
MAX_RESULTS = 2000


def search_catalog(
    lab: Any, aoi_wkt: str, months: int = 5, now: datetime | None = None
) -> pd.DataFrame:
    """Public ASF search of NISAR GCOV for the last months: no maturity or configuration filter."""
    end = now or datetime.now(UTC)
    start = end - timedelta(days=round(months * DAYS_PER_MONTH))
    options = asf.ASFSearchOptions(
        dataset=["NISAR"],
        processingLevel=["GCOV"],
        intersectsWith=aoi_wkt,
        start=start,
        end=end,
        maxResults=MAX_RESULTS,
    )
    return lab.catalogo_online(search_options=options, aoi_wkt=aoi_wkt)
