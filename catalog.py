import json
from pathlib import Path

from models import Catalog, CatalogItem, Category, Level

DEFAULT_CATALOG_PATH = Path(__file__).resolve().parent / "data" / "catalog.json"

LEVEL_ORDER = [Level.BEGINNER, Level.INTERMEDIATE, Level.ADVANCED]


def load_catalog(path: Path = DEFAULT_CATALOG_PATH) -> Catalog:
    data = json.loads(Path(path).read_text())
    categories = [Category.model_validate(c) for c in data["categories"]]
    items = [CatalogItem.model_validate(item) for item in data["items"]]

    known_ids = {c.id for c in categories}
    for item in items:
        if item.category not in known_ids:
            raise ValueError(
                f"catalog item {item.id!r} references unknown category {item.category!r}"
            )

    return Catalog(categories=categories, items=items)


def get_item(catalog: Catalog, item_id: str) -> CatalogItem:
    for item in catalog.items:
        if item.id == item_id:
            return item
    raise KeyError(f"No catalog item with id {item_id!r}")


def category_name(catalog: Catalog, category_id: str) -> str:
    for category in catalog.categories:
        if category.id == category_id:
            return category.name
    return category_id


def levels_within(level: Level, spread: int = 1) -> list[Level]:
    idx = LEVEL_ORDER.index(level)
    lo = max(0, idx - spread)
    hi = min(len(LEVEL_ORDER) - 1, idx + spread)
    return LEVEL_ORDER[lo : hi + 1]
