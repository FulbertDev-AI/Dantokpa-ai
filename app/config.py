
import json
import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "app" / "storage"

PRODUCTS_FILE = STORAGE_DIR / "products.json"
ORDERS_FILE = STORAGE_DIR / "orders.json"

load_dotenv(BASE_DIR / ".env")

FRANKFURTER_API_URL = os.getenv(
    "FRANKFURTER_API_URL",
    "https://api.frankfurter.dev/v2/rate",
)
RODIUMAI_MODEL = os.getenv("RODIUMAI_MODEL", "openai/gpt-4o")
RODIUMAI_API_KEY = os.getenv("RODIUMAI_API_KEY", "")


def load_json(file_path: Path):
    """Charge un fichier JSON."""
    with file_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(file_path: Path, data):
    """Enregistre atomiquement des données JSON dans un fichier."""
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=file_path.parent,
            prefix=f".{file_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            temporary_path = Path(file.name)
            json.dump(data, file, ensure_ascii=False, indent=4)
        os.replace(temporary_path, file_path)
    except (OSError, TypeError, ValueError):
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass
        raise
