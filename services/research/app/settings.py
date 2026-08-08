from pathlib import Path
import os


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./arkana_metadata.db")
DATA_ROOT = Path(os.getenv("DATA_ROOT", "../../data/processed")).resolve()
MAX_BARS_PER_REQUEST = int(os.getenv("MAX_BARS_PER_REQUEST", "5000"))
