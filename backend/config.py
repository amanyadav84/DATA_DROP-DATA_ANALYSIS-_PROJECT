"""Application configuration — loads environment variables."""

from __future__ import annotations

import os
from pathlib import Path

_ENV_FILE = Path(__file__).resolve().parent / ".env"


def _load_dotenv() -> None:
    if not _ENV_FILE.exists():
        return
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            os.environ.setdefault(key, val)


_load_dotenv()


def get_api_key() -> str:
    return os.environ.get("AI_STUDIO_API_KEY", "")


def get_api_base_url() -> str:
    return os.environ.get("AI_STUDIO_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")


# ---------------------------------------------------------------------------
# Enterprise Upload Configuration
# ---------------------------------------------------------------------------

def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except (ValueError, TypeError):
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, str(default)))
    except (ValueError, TypeError):
        return default


# Upload size limits in MB per file type
UPLOAD_LIMITS_MB = {
    "csv":  _env_int("UPLOAD_LIMIT_CSV_MB",  2048),   # 2 GB
    "json": _env_int("UPLOAD_LIMIT_JSON_MB", 1024),   # 1 GB
    "tsv":  _env_int("UPLOAD_LIMIT_TSV_MB",  2048),   # 2 GB
    "txt":  _env_int("UPLOAD_LIMIT_TSV_MB",  2048),   # same as TSV
    "xlsx": _env_int("UPLOAD_LIMIT_XLSX_MB", 512),    # 500 MB
    "xls":  _env_int("UPLOAD_LIMIT_XLSX_MB", 512),    # 500 MB
    "parquet": _env_int("UPLOAD_LIMIT_PARQUET_MB", 5120),  # 5 GB
    "pbix": _env_int("UPLOAD_LIMIT_PBIX_MB", 512),  # 5 GB
    
}

# Maximum upload size (absolute ceiling across all types)
MAX_UPLOAD_MB = _env_int("MAX_UPLOAD_MB", 5120)  # 5 GB

# Chunk size for chunked uploads (in bytes)
CHUNK_SIZE_BYTES = _env_int("CHUNK_SIZE_BYTES", 5 * 1024 * 1024)  # 5 MB default chunk

# Maximum concurrent chunk uploads per file
MAX_CONCURRENT_CHUNKS = _env_int("MAX_CONCURRENT_CHUNKS", 3)

# Temporary directory for chunk assembly
TEMP_UPLOAD_DIR = Path(os.environ.get("TEMP_UPLOAD_DIR", str(Path(__file__).resolve().parent / "temp_uploads")))

# Processing timeout in seconds
PROCESSING_TIMEOUT_SECONDS = _env_int("PROCESSING_TIMEOUT_SECONDS", 600)  # 10 min

# Large file warning threshold in MB
LARGE_FILE_WARNING_MB = _env_int("LARGE_FILE_WARNING_MB", 1024)  # 1 GB

# Streaming processing threshold (files above this use streaming)
STREAMING_THRESHOLD_MB = _env_int("STREAMING_THRESHOLD_MB", 100)  # 100 MB

# Preview row limits
PREVIEW_ROWS_SAMPLE = _env_int("PREVIEW_ROWS_SAMPLE", 100)
PREVIEW_ROWS_TOTAL_MAX = _env_int("PREVIEW_ROWS_TOTAL_MAX", 500)


def get_max_upload_bytes() -> int:
    """Get the absolute maximum upload size in bytes."""
    return MAX_UPLOAD_MB * 1024 * 1024


def get_file_limit_mb(filename: str) -> int:
    """Get the upload limit in MB for a given file extension."""
    name_lower = filename.lower()
    for ext, limit in UPLOAD_LIMITS_MB.items():
        if name_lower.endswith(f".{ext}"):
            return limit
    return MAX_UPLOAD_MB  # fallback to global max


def get_chunk_size() -> int:
    """Get the chunk size in bytes."""
    return CHUNK_SIZE_BYTES


def is_streaming_threshold(file_size_mb: float) -> bool:
    """Check if a file should use streaming processing."""
    return file_size_mb > STREAMING_THRESHOLD_MB


def is_large_file_warning(file_size_mb: float) -> bool:
    """Check if a file should trigger a large file warning."""
    return file_size_mb > LARGE_FILE_WARNING_MB
