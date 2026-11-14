from urllib.parse import urljoin, urlsplit

from nisar_hazard_watch.constants.explorations import LAYER_KINDS, LayerKind
from nisar_hazard_watch.constants.insar import LAYER_TITLES


def gateway_url(base_url: str, path: str) -> str:
    """The absolute URL of a gateway path; a redirect may only ever reach the gateway host."""
    base = base_url.rstrip("/")
    url = urljoin(base + "/", path)
    if urlsplit(url)[:2] != urlsplit(base)[:2]:
        raise ValueError(f"layer URL {url!r} is not served by the ML gateway")
    return url


def layer_kind(layer_id: str) -> str:
    for prefix, kind in LAYER_KINDS:
        if layer_id.startswith(prefix):
            return kind.value
    return LayerKind.GENERIC.value


def layer_title(layer_id: str) -> str:
    return LAYER_TITLES.get(layer_id) or layer_id.removeprefix("display_").replace("_", " ")
