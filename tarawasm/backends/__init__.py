from .base import BackendError, Command, LanguageBackend
from .c import CBackend
from .go import GoBackend
from .javascript import JavaScriptBackend
from .python import PythonBackend
from .rust import RustBackend

_BACKENDS: dict[str, LanguageBackend] = {
    backend.name: backend
    for backend in (
        PythonBackend(),
        GoBackend(),
        JavaScriptBackend(),
        RustBackend(),
        CBackend(),
    )
}


def backend_names() -> tuple[str, ...]:
    return tuple(_BACKENDS)


def get_backend(name: str) -> LanguageBackend:
    try:
        return _BACKENDS[name]
    except KeyError as exc:
        raise BackendError(
            f"Unsupported language '{name}'; expected one of: {', '.join(_BACKENDS)}."
        ) from exc


__all__ = [
    "BackendError",
    "Command",
    "LanguageBackend",
    "backend_names",
    "get_backend",
]
