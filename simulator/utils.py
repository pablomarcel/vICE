from __future__ import annotations
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, Type, TypeVar
import json

T = TypeVar("T")


def ensure_dir(path: str | Path) -> None:
    p = Path(path)
    if p.is_dir():
        p.mkdir(parents=True, exist_ok=True)
    else:
        p.parent.mkdir(parents=True, exist_ok=True)


def dataclass_from_dict(cls: Type[T], data: Dict[str, Any]) -> T:
    field_names = {f.name for f in getattr(cls, "__dataclass_fields__", {}).values()}
    filtered = {k: v for k, v in data.items() if k in field_names}
    return cls(**filtered)  # type: ignore[arg-type]


def load_json(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str | Path, data: dict) -> None:
    ensure_dir(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def log_call(func: Callable[..., T]) -> Callable[..., T]:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        name = func.__qualname__
        print(f"[simulator] -> {name}")
        result = func(*args, **kwargs)
        print(f"[simulator] <- {name}")
        return result

    return wrapper
