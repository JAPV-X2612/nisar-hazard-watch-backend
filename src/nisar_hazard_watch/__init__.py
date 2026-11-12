from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("nisar-hazard-watch-backend")
except PackageNotFoundError:
    __version__ = "0.0.0"
