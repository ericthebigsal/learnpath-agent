import json
from pathlib import Path

from models import Catalog, CatalogItem, Level

DEFAULT_CATALOG_PATH = Path(__file__).resolve().parent / "data" / "catalog.json"

LEVEL_ORDER = [Level.BEGINNER, Level.INTERMEDIATE, Level.ADVANCED]


def load_catalog(path: Path = DEFAULT_CATALOG_PATH) -> Catalog:
    data = json.loads(Path(path).read_text())
    return Catalog(items=[CatalogItem.model_validate(item) for item in data])


def get_item(catalog: Catalog, item_id: str) -> CatalogItem:
    for item in catalog.items:
        if item.id == item_id:
            return item
    raise KeyError(f"No catalog item with id {item_id!r}")


def levels_within(level: Level, spread: int = 1) -> list[Level]:
    idx = LEVEL_ORDER.index(level)
    lo = max(0, idx - spread)
    hi = min(len(LEVEL_ORDER) - 1, idx + spread)
    return LEVEL_ORDER[lo : hi + 1]
