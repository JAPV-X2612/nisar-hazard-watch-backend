from datetime import date, datetime

from nisar_hazard_watch.constants.insar import GUNW_DATE_FORMAT, GUNW_TIMES
from nisar_hazard_watch.exceptions.pair_errors import InvalidPairError


def pair_dates(pair_id: str) -> tuple[date, date]:
    """Reference and secondary acquisition days, read from a GUNW granule name."""
    found = GUNW_TIMES.search(pair_id)
    if found is None:
        raise InvalidPairError(f"{pair_id!r} is not a NISAR GUNW granule name")
    try:
        reference, secondary = (
            datetime.strptime(day, GUNW_DATE_FORMAT).date() for day in found.groups()
        )
    except ValueError:
        raise InvalidPairError(f"{pair_id!r} holds an impossible acquisition date") from None
    if reference >= secondary:
        raise InvalidPairError(f"{pair_id!r} must acquire its reference before its secondary")
    return reference, secondary
