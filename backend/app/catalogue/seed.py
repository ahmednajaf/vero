from importlib.resources import files

from app.catalogue.contracts import Catalogue

CATALOGUE_VERSION = "1.0.0"


def load_catalogue() -> Catalogue:
    return Catalogue.model_validate_json(
        files("app.catalogue").joinpath("data/v1.json").read_text(encoding="utf-8")
    )
