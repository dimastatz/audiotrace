"""The docs site can't fall behind the contract: every CallReport field and
every public name must appear in the reference."""

import re
import typing
from pathlib import Path

from pydantic import BaseModel

import audiotrace
from audiotrace.models import CallReport

SITE = Path(__file__).resolve().parent.parent / "docs" / "site"


def _models(model, seen=None):
    seen = seen if seen is not None else {}
    seen[model.__name__] = model
    for info in model.model_fields.values():
        for candidate in (info.annotation, *typing.get_args(info.annotation)):
            for inner in (candidate, *typing.get_args(candidate)):
                if (
                    isinstance(inner, type)
                    and issubclass(inner, BaseModel)
                    and inner.__name__ not in seen
                ):
                    _models(inner, seen)
    return seen


def test_callreport_reference_lists_every_model_and_field():
    page = (SITE / "reference" / "callreport.md").read_text(encoding="utf-8")
    sections = re.split(r"^#+ ", page, flags=re.M)
    by_title = {s.splitlines()[0].strip(): s for s in sections if s.strip()}
    for name, model in _models(CallReport).items():
        assert name in by_title, f"no section for {name}"
        for field in model.model_fields:
            assert f"`{field}`" in by_title[name], f"{name}.{field} missing from the reference"


def test_api_reference_covers_the_public_api():
    page = (SITE / "reference" / "api.md").read_text(encoding="utf-8")
    models = set(_models(CallReport))
    exported = (
        set(audiotrace.__all__)
        - models
        - {"__version__", "Metric", "Delta", "Regression", "ProvenanceChange", "DriftResult"}
    )
    for name in exported:
        assert re.search(rf"::: audiotrace(\.\w+)*\.{name}\b", page), f"{name} not in api.md"


def test_nav_pages_exist():
    config = (SITE.parent.parent / "mkdocs.yml").read_text(encoding="utf-8")
    for page in re.findall(r":\s+([\w/-]+\.md)", config):
        assert (SITE / page).exists(), page
