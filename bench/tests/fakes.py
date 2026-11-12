import numpy as np
import pandas as pd
import xarray as xr

TOKEN = "super-secret-token"
AOI = "POLYGON((0 0, 0 1, 1 1, 1 0, 0 0))"
DATES = pd.to_datetime(["2026-07-01", "2026-08-01", "2026-09-01", "2026-10-01", "2026-10-22"])


def catalog_frame() -> pd.DataFrame:
    rows = [
        {
            "fecha": date,
            "pista": 84,
            "direccion": "A",
            "frame": 18,
            "pol": "DHDH",
            "cobertura_aoi": 1.0,
            "url": f"https://example.test/{date:%Y%m%d}.h5",
            "nombre": f"scene_{date:%Y%m%d}.h5",
            "ruta_local": None,
        }
        for date in DATES
    ]
    return pd.DataFrame(rows)


class FakeLab:
    """Stands in for DSSA's nisac_ts module; records what it was called with."""

    def __init__(self, fail_in: str | None = None) -> None:
        self.fail_in = fail_in
        self.calls: dict[str, dict] = {}

    def aoi_desde_punto(self, lat, lon, radio_km=2.0):
        self.calls["aoi"] = {"lat": lat, "lon": lon, "radio_km": radio_km}
        return AOI

    def servicio_en_linea(self, token, url_prueba, timeout=15):
        if self.fail_in == "probe":
            raise RuntimeError(f"probe failed with {token}")
        self.calls["probe"] = {"url": url_prueba}
        return True, "ok"

    def crear_fs_http(self, token, block_size=1024 * 1024, cache_type="blockcache", max_bloques=64):
        self.calls["fs"] = {"block_size": block_size}
        return object()

    def construir_pila(
        self,
        escenas,
        aoi_wkt,
        modo,
        fs=None,
        frecuencia="A",
        pols=("HHHH", "HVHV"),
        multilook=1,
        min_validos=0.3,
        hilos=4,
        usar_mask=True,
        perfilar=False,
        al_avanzar=None,
    ):
        if self.fail_in == "read":
            raise RuntimeError("no scene could be read")
        self.calls["stack"] = {"hilos": hilos, "multilook": multilook, "usar_mask": usar_mask}
        rng = np.random.default_rng(0)
        data = rng.gamma(shape=4.0, scale=0.05, size=(len(escenas), 6, 6)).astype("float32")
        stack = xr.Dataset(
            {"HHHH": (("time", "y", "x"), data)},
            coords={"time": pd.to_datetime(escenas["fecha"]).to_numpy()},
        )
        log = pd.DataFrame(
            {
                "estado": ["ok"] * len(escenas),
                "validos": [0.99] * len(escenas),
                "peticiones_http": [50] * len(escenas),
                "MB_descargados": [15.0] * len(escenas),
                "MB_leidos_h5": [14.0] * len(escenas),
            }
        )
        return stack, log

    def log_ratio(self, pila, pol, fecha0, fecha1):
        return pila[pol].isel(time=-1) / pila[pol].isel(time=0)

    def metricas_serie(self, da):
        return da.mean("time")
