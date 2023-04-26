from ._importlib import metadata

try:
    __version__ = metadata.version('setuptools') or 'unknown'
except Exception:
    __version__ = 'unknown'
