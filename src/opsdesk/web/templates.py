from pathlib import Path

from fastapi.templating import Jinja2Templates

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=PACKAGE_ROOT / "templates")
