"""Data Drop — FastAPI backend.

Run with:  uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

import io
import json
import os
import gzip
import zipfile
import csv
import tempfile
import time
import threading
import asyncio
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from charts import build_chart
from cleaner import apply_clean, analyze_missing, impute_knn, impute_interpolation, convert_datatypes, detect_invalid_values, detect_outliers, treat_outliers, normalize_text, analyze_duplicates, generate_cleaning_report, auto_clean
from correlation import (
    build_heatmap,
    build_network_graph,
    build_scatter,
    compute_correlation,
    export_correlation_csv,
    export_correlation_json,
)
from distribution import (
    build_comparison_overlay,
    build_distribution_chart,
    build_transform_preview,
    compute_distribution,
    export_distribution_csv,
    export_distribution_json,
)
from processor import preview_dataframe, profile_dataframe, suggest_charts
from quality_report import analyze_dataset_quality
from session import store
from ai_service import ai_analyze, ai_chat, ai_analyze_json, ai_check_connection
from eda_report import generate_eda_report, export_json, export_markdown, export_excel_summary
from report_template import build_html_report
from ai_insights_engine import generate_ai_insights, get_cached_insights, clear_cache
from ai_insights_export import (
    export_markdown as export_insights_markdown,
    export_html as export_insights_html,
    export_json as export_insights_json,
    export_csv as export_insights_csv,
)
from nlq_engine import process_question, suggest_questions
from feature_engineering import (
    encode_onehot, encode_label, encode_ordinal, encode_frequency, encode_target,
    scale_standard, scale_minmax, scale_robust,
    transform_log, transform_sqrt, transform_power,
    create_date_features, create_polynomial, create_interactions, create_binning, create_missing_indicator,
    recommend_features,
)
from statistical_tests import (
    run_all_normality_tests, ttest_ind, ttest_paired, anova_one_way, chi_square_test,
    mann_whitney_u, descriptive_stats, pearson_test, spearman_test,
)
from sql_generator import generate_sql
from code_generator import generate_code
from chart_advisor import recommend_charts
from dashboard import (
    dashboard_store,
    build_dashboard_chart,
    generate_ai_dashboard,
    generate_chart_insight,
    DASHBOARD_TEMPLATES,
)
from project import project_store
from chunked_upload import chunk_manager
from config import (
    get_file_limit_mb, get_max_upload_bytes, get_chunk_size,
    is_streaming_threshold, is_large_file_warning, STREAMING_THRESHOLD_MB,
    UPLOAD_LIMITS_MB, LARGE_FILE_WARNING_MB, TEMP_UPLOAD_DIR,
)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="Data Drop API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Legacy compatibility — keep old variable for any code referencing it
MAX_FILE_MB = 50


# ---------------------------------------------------------------------------
# Upload progress tracking (in-memory, per session)
# ---------------------------------------------------------------------------
_upload_progress: dict[str, dict] = {}
_progress_lock = threading.Lock()


def _set_progress(upload_id: str, data: dict) -> None:
    with _progress_lock:
        _upload_progress[upload_id] = data


def _get_progress(upload_id: str) -> Optional[dict]:
    with _progress_lock:
        return _upload_progress.get(upload_id)


def _clear_progress(upload_id: str) -> None:
    with _progress_lock:
        _upload_progress.pop(upload_id, None)


# ---------------------------------------------------------------------------
# File validation
# ---------------------------------------------------------------------------

SUPPORTED_EXTENSIONS = {".csv", ".json", ".tsv", ".txt", ".xlsx", ".xls", ".parquet"}

# CSV sniffer delimiters
_DELIMITER_HINTS = [",", "\t", ";", "|"]


def validate_file_bytes(raw: bytes, filename: str) -> None:
    """Validate file content for common issues. Raises ValueError on problems."""
    name_lower = filename.lower()

    if name_lower.endswith(".csv") or name_lower.endswith(".tsv") or name_lower.endswith(".txt"):
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            try:
                raw.decode("latin-1")
            except Exception:
                raise ValueError(
                    "File encoding not recognized. Supported: UTF-8, Latin-1. "
                    "Please re-save with UTF-8 encoding."
                )
        # Check for empty file
        if not text.strip():
            raise ValueError("File is empty — no data found.")
        # Check for single column (possible wrong delimiter)
        lines = text.split("\n")
        if len(lines) > 1:
            first_line = lines[0]
            for delim in _DELIMITER_HINTS:
                count = first_line.count(delim)
                if count > 2:
                    break
            # If no delimiter found in header, warn
            if not any(first_line.count(d) > 0 for d in _DELIMITER_HINTS):
                pass  # Single column is valid

    elif name_lower.endswith(".json"):
        try:
            data = json.loads(raw.decode("utf-8", errors="replace"))
            if not isinstance(data, (list, dict)):
                raise ValueError("JSON must be an array of objects or a nested object.")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")

    elif name_lower.endswith((".xlsx", ".xls")):
        # Quick magic number check
        if len(raw) < 4:
            raise ValueError("File too small to be a valid Excel file.")
        # ZIP-based check for xlsx
        if name_lower.endswith(".xlsx"):
            if raw[:2] != b"PK":
                raise ValueError("File does not appear to be a valid .xlsx file.")

    elif name_lower.endswith(".parquet"):
        if raw[:4] != b"PAR1":
            raise ValueError("File does not appear to be a valid Parquet file.")


def detect_compression(filename: str) -> Optional[str]:
    """Detect if a file is compressed. Returns type or None."""
    name_lower = filename.lower()
    if name_lower.endswith(".gz") or name_lower.endswith(".gzip"):
        return "gzip"
    if name_lower.endswith(".zip"):
        return "zip"
    if name_lower.endswith(".bz2"):
        return "bz2"
    if name_lower.endswith(".xz"):
        return "xz"
    return None


def decompress_file(raw: bytes, filename: str) -> tuple[bytes, str]:
    """Decompress file if needed. Returns (decompressed_bytes, inner_filename)."""
    comp = detect_compression(filename)
    if comp is None:
        return raw, filename

    if comp == "gzip":
        decompressed = gzip.decompress(raw)
        # Strip .gz extension
        inner_name = filename[:-3] if filename.lower().endswith(".gz") else filename[:-5]
        return decompressed, inner_name

    if comp == "zip":
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = zf.namelist()
            # Filter out __MACOSX, hidden files
            data_files = [
                n for n in names
                if not n.startswith("__MACOSX")
                and not n.startswith(".")
                and not n.endswith("/")
            ]
            if not data_files:
                raise ValueError("ZIP archive contains no data files.")
            if len(data_files) > 1:
                # Prefer CSV/JSON/XLSX
                preferred = [n for n in data_files if any(n.lower().endswith(e) for e in (".csv", ".json", ".tsv", ".xlsx"))]
                if preferred:
                    data_files = preferred
            inner_name = data_files[0]
            decompressed = zf.read(inner_name)
            return decompressed, inner_name

    raise ValueError(f"Decompression for {comp} is not supported.")


# ---------------------------------------------------------------------------
# Streaming file parsing (for large files)
# ---------------------------------------------------------------------------

def parse_upload_streaming(filename: str, filepath: str, file_size: int) -> pd.DataFrame:
    """Parse large files using streaming/chunked reading to avoid memory spikes."""
    name = filename.lower()
    chunk_size = 100_000  # rows per chunk for pandas

    if name.endswith(".csv") or name.endswith(".tsv") or name.endswith(".txt"):
        sep = "\t" if (name.endswith(".tsv") or name.endswith(".txt")) else None
        # Use chunked reading for large CSVs
        chunks = []
        for chunk in pd.read_csv(
            filepath,
            sep=sep,
            engine="python" if sep is None else "c",
            chunksize=chunk_size,
            on_bad_lines="warn",
            low_memory=False,
        ):
            chunks.append(chunk)
            # Memory safety: stop at 50 chunks (5M rows) for profiling
            if len(chunks) >= 50:
                break
        df = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
    elif name.endswith(".json"):
        # For large JSON, read line by line
        records = []
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(10 * 1024 * 1024)  # Read first 10MB for structure
        data = json.loads(content)
        if isinstance(data, list):
            df = pd.DataFrame(data)
        elif isinstance(data, dict):
            for key in ("data", "records", "rows", "results"):
                if key in data and isinstance(data[key], list):
                    df = pd.DataFrame(data[key])
                    break
            else:
                df = pd.DataFrame(data)
        else:
            raise ValueError("Unsupported JSON structure")
    elif name.endswith(".xlsx"):
        # For large Excel, read with openpyxl in read_only mode
        df = pd.read_excel(filepath, engine="openpyxl")
    elif name.endswith(".parquet"):
        df = pd.read_parquet(filepath)
    else:
        raise ValueError("Unsupported file type. Use CSV, JSON, TSV, XLSX, or Parquet.")

    if df.empty:
        raise ValueError("The uploaded file contains no data rows.")
    return df


# ---------------------------------------------------------------------------
# File parsing (kept for backward compatibility)
# ---------------------------------------------------------------------------

def parse_upload(filename: str, raw: bytes) -> pd.DataFrame:
    name = filename.lower()
    text = raw.decode("utf-8", errors="replace")

    if name.endswith(".csv"):
        try:
            df = pd.read_csv(io.StringIO(text), sep=None, engine="python")
        except Exception:
            df = pd.read_csv(io.StringIO(text))
    elif name.endswith(".json"):
        data = json.loads(text)
        if isinstance(data, list):
            df = pd.DataFrame(data)
        elif isinstance(data, dict):
            for key in ("data", "records", "rows", "results"):
                if key in data and isinstance(data[key], list):
                    df = pd.DataFrame(data[key])
                    break
            else:
                df = pd.DataFrame(data)
        else:
            raise ValueError("Unsupported JSON structure")
    elif name.endswith((".tsv", ".txt")):
        df = pd.read_csv(io.StringIO(text), sep="\t")
    elif name.endswith(".xlsx"):
        df = pd.read_excel(io.BytesIO(raw))
    elif name.endswith(".parquet"):
        df = pd.read_parquet(io.BytesIO(raw))
    else:
        raise ValueError("Unsupported file type. Use CSV, JSON, TSV, XLSX, or Parquet.")

    if df.empty:
        raise ValueError("The uploaded file contains no data rows.")
    return df


# ---------------------------------------------------------------------------
# Background processing (for large files)
# ---------------------------------------------------------------------------

def _process_large_upload_background(session_id: str, df: pd.DataFrame, filename: str) -> None:
    """Process a large upload in the background — profile, preview, suggest charts."""
    try:
        profile = profile_dataframe(df)
        preview = preview_dataframe(df, 20)
        suggestions = suggest_charts(df, profile)
        _set_progress(session_id, {
            "status": "processing_complete",
            "session_id": session_id,
            "profile": profile,
            "preview": preview,
            "suggestions": suggestions,
        })
    except Exception as e:
        _set_progress(session_id, {
            "status": "processing_error",
            "session_id": session_id,
            "error": str(e),
        })


# ---------------------------------------------------------------------------
# API routes — Upload
# ---------------------------------------------------------------------------

@app.get("/api/upload/limits")
def get_upload_limits():
    """Return upload limits and configuration for the frontend."""
    return {
        "limits_mb": UPLOAD_LIMITS_MB,
        "max_upload_mb": get_max_upload_bytes() // (1024 * 1024),
        "chunk_size": get_chunk_size(),
        "supported_extensions": list(SUPPORTED_EXTENSIONS),
        "large_file_warning_mb": LARGE_FILE_WARNING_MB,
        "streaming_threshold_mb": STREAMING_THRESHOLD_MB,
    }


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Legacy single-upload endpoint — kept for backward compatibility.
    Handles files up to the per-type limit using streaming processing.
    """
    raw = await file.read()
    limit_mb = get_file_limit_mb(file.filename or "upload.csv")
    if len(raw) > limit_mb * 1024 * 1024:
        raise HTTPException(413, f"File exceeds {limit_mb} MB limit for this file type.")

    # Decompress if needed
    try:
        raw, actual_filename = decompress_file(raw, file.filename or "upload.csv")
    except ValueError as e:
        raise HTTPException(422, str(e))

    # Validate content
    try:
        validate_file_bytes(raw, actual_filename)
    except ValueError as e:
        raise HTTPException(422, str(e))

    # Parse
    try:
        df = parse_upload(actual_filename, raw)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except Exception as exc:
        raise HTTPException(422, f"Could not parse file: {exc}")

    session_id = store.create(df, file.filename or "upload.csv", len(raw))
    profile = profile_dataframe(df)
    preview = preview_dataframe(df, 20)
    suggestions = suggest_charts(df, profile)

    return {
        "session_id": session_id,
        "filename": file.filename,
        "profile": profile,
        "preview": preview,
        "suggestions": suggestions,
        "file_size": len(raw),
        "processing_mode": "standard",
    }


# ---------------------------------------------------------------------------
# Chunked Upload API
# ---------------------------------------------------------------------------

@app.post("/api/upload/chunked/init")
async def init_chunked_upload(body: dict):
    """Initialize a chunked upload session."""
    filename = body.get("filename", "upload.csv")
    file_size = body.get("file_size", 0)
    total_chunks = body.get("total_chunks", 0)
    file_hash = body.get("file_hash", "")

    if not filename:
        raise HTTPException(422, "filename is required")
    if file_size <= 0:
        raise HTTPException(422, "file_size must be positive")

    # Check per-type limit
    limit_mb = get_file_limit_mb(filename)
    if file_size > limit_mb * 1024 * 1024:
        raise HTTPException(413, f"File exceeds {limit_mb} MB limit for this file type.")

    # Check absolute limit
    if file_size > get_max_upload_bytes():
        raise HTTPException(413, f"File exceeds maximum upload size of {get_max_upload_bytes() // (1024*1024)} MB.")

    # Check for existing session with same hash (resume support)
    if file_hash:
        existing = chunk_manager.get_active_sessions()
        for s in existing:
            if s.get("file_hash") == file_hash and s.get("filename") == filename:
                return {
                    "upload_id": s["upload_id"],
                    "status": "resuming",
                    "chunks_received": s["chunks_received"],
                    "total_chunks": s["total_chunks"],
                    "progress_pct": s["progress_pct"],
                }

    session = chunk_manager.create_session(filename, file_size, total_chunks, file_hash)

    return {
        "upload_id": session.upload_id,
        "status": "created",
        "total_chunks": total_chunks,
        "chunk_size": get_chunk_size(),
    }


@app.post("/api/upload/chunked/{upload_id}/chunk/{chunk_number}")
async def upload_chunk(
    upload_id: str,
    chunk_number: int,
    total_chunks: int = Query(...),
    file: UploadFile = File(...),
):
    """Upload a single chunk."""
    chunk_data = await file.read()
    result = chunk_manager.receive_chunk(upload_id, chunk_number, chunk_data, total_chunks)

    if result.get("status") == "error":
        raise HTTPException(404 if "not found" in result.get("error", "").lower() else 400, result["error"])

    # Update progress tracking
    session = chunk_manager.get_session(upload_id)
    if session:
        _set_progress(upload_id, {
            "status": "uploading",
            "upload_id": upload_id,
            "filename": session.filename,
            "file_size": session.file_size,
            "chunks_received": len(session.chunks_received),
            "total_chunks": session.total_chunks,
            "progress_pct": session.progress_pct,
            "bytes_received": session.bytes_received,
        })

    return result


@app.post("/api/upload/chunked/{upload_id}/complete")
async def complete_chunked_upload(upload_id: str):
    """Assemble chunks and process the final file."""
    session = chunk_manager.get_session(upload_id)
    if session is None:
        raise HTTPException(404, "Upload session not found")

    # Check if all chunks received
    missing = chunk_manager.get_missing_chunks(upload_id)
    if missing:
        raise HTTPException(400, f"Missing chunks: {missing[:20]}{'...' if len(missing) > 20 else ''}")

    # Set processing status
    _set_progress(upload_id, {
        "status": "processing",
        "upload_id": upload_id,
        "filename": session.filename,
        "file_size": session.file_size,
        "progress_pct": 100,
        "message": "Assembling file...",
    })

    # Assemble
    filepath = chunk_manager.assemble_file(upload_id)
    if filepath is None:
        raise HTTPException(500, "Failed to assemble file chunks")

    # Decompress if needed
    try:
        raw_bytes = filepath.read_bytes()
        raw_bytes, actual_filename = decompress_file(raw_bytes, session.filename)
    except ValueError as e:
        chunk_manager.cancel_upload(upload_id)
        raise HTTPException(422, str(e))

    # Validate
    try:
        validate_file_bytes(raw_bytes, actual_filename)
    except ValueError as e:
        chunk_manager.cancel_upload(upload_id)
        raise HTTPException(422, str(e))

    # Parse — use streaming for large files
    _set_progress(upload_id, {
        "status": "processing",
        "upload_id": upload_id,
        "filename": session.filename,
        "file_size": session.file_size,
        "progress_pct": 100,
        "message": "Parsing data...",
    })

    try:
        file_size_mb = len(raw_bytes) / (1024 * 1024)
        if is_streaming_threshold(file_size_mb):
            df = parse_upload_streaming(actual_filename, str(filepath), len(raw_bytes))
        else:
            df = parse_upload(actual_filename, raw_bytes)
    except ValueError as exc:
        chunk_manager.cancel_upload(upload_id)
        raise HTTPException(422, str(exc))
    except Exception as exc:
        chunk_manager.cancel_upload(upload_id)
        raise HTTPException(422, f"Could not parse file: {exc}")

    # Create session
    session_id = store.create(df, session.filename, session.file_size)

    # Process (background for large files, synchronous for small)
    file_size_mb = session.file_size / (1024 * 1024)
    is_large = file_size_mb > 100  # 100 MB threshold for background processing

    if is_large:
        # Background processing
        _set_progress(upload_id, {
            "status": "processing_background",
            "upload_id": upload_id,
            "session_id": session_id,
            "filename": session.filename,
            "file_size": session.file_size,
            "progress_pct": 100,
            "message": "Processing in background...",
        })
        thread = threading.Thread(
            target=_process_large_upload_background,
            args=(session_id, df, session.filename),
            daemon=True,
        )
        thread.start()

        # Clean up chunks
        chunk_manager.cancel_upload(upload_id)

        return {
            "session_id": session_id,
            "filename": session.filename,
            "file_size": session.file_size,
            "processing_mode": "background",
            "message": "File uploaded. Processing in background. Use /api/session/{id} to check status.",
        }
    else:
        # Synchronous processing
        profile = profile_dataframe(df)
        preview = preview_dataframe(df, 20)
        suggestions = suggest_charts(df, profile)

        # Clean up chunks
        chunk_manager.cancel_upload(upload_id)

        return {
            "session_id": session_id,
            "filename": session.filename,
            "profile": profile,
            "preview": preview,
            "suggestions": suggestions,
            "file_size": session.file_size,
            "processing_mode": "standard",
        }


@app.get("/api/upload/chunked/{upload_id}/status")
async def get_upload_status(upload_id: str):
    """Get upload/processing status."""
    # Check progress first
    progress = _get_progress(upload_id)
    if progress:
        return progress

    # Check chunk session
    session = chunk_manager.get_session(upload_id)
    if session:
        return {
            "status": "uploading",
            "upload_id": upload_id,
            "filename": session.filename,
            "file_size": session.file_size,
            "chunks_received": len(session.chunks_received),
            "total_chunks": session.total_chunks,
            "progress_pct": session.progress_pct,
        }

    return {"status": "not_found"}


@app.get("/api/upload/chunked/{upload_id}/resume-info")
async def get_resume_info(upload_id: str):
    """Get info needed to resume a chunked upload."""
    session = chunk_manager.get_session(upload_id)
    if session is None:
        raise HTTPException(404, "Upload session not found")

    missing = chunk_manager.get_missing_chunks(upload_id)
    return {
        "upload_id": upload_id,
        "filename": session.filename,
        "file_size": session.file_size,
        "total_chunks": session.total_chunks,
        "chunks_received": sorted(session.chunks_received),
        "missing_chunks": missing,
        "chunk_size": get_chunk_size(),
    }


@app.post("/api/upload/chunked/{upload_id}/cancel")
async def cancel_upload(upload_id: str):
    """Cancel and clean up an upload."""
    ok = chunk_manager.cancel_upload(upload_id)
    _clear_progress(upload_id)
    if not ok:
        raise HTTPException(404, "Upload session not found")
    return {"status": "cancelled"}


@app.get("/api/upload/history")
def get_upload_history():
    """Get upload history."""
    return {"history": store.get_upload_history()}


@app.get("/api/upload/active")
def get_active_uploads():
    """Get all active chunked uploads."""
    return {"uploads": chunk_manager.get_active_sessions()}


# ---------------------------------------------------------------------------
# SSE progress streaming
# ---------------------------------------------------------------------------

@app.get("/api/upload/progress/{upload_id}")
async def stream_upload_progress(upload_id: str):
    """Stream upload progress via Server-Sent Events."""
    async def event_generator():
        for _ in range(300):  # 5 minutes max
            progress = _get_progress(upload_id)
            session = chunk_manager.get_session(upload_id)

            if progress:
                data = json.dumps(progress)
                yield f"data: {data}\n\n"
                if progress.get("status") in ("processing_complete", "processing_error", "completed"):
                    return
            elif session:
                data = json.dumps({
                    "status": "uploading",
                    "upload_id": upload_id,
                    "progress_pct": session.progress_pct,
                    "chunks_received": len(session.chunks_received),
                    "total_chunks": session.total_chunks,
                })
                yield f"data: {data}\n\n"
            else:
                yield f"data: {json.dumps({'status': 'not_found'})}\n\n"
                return

            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# API routes — Session
# ---------------------------------------------------------------------------

@app.get("/api/session/{session_id}")
def get_session(session_id: str):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found or expired.")
    df = entry["df"]

    # Check if background processing is still happening
    progress = _get_progress(session_id)
    if progress and progress.get("status") == "processing_background":
        return {
            "session_id": session_id,
            "filename": entry["filename"],
            "processing": True,
            "message": "Still processing...",
        }

    profile = profile_dataframe(df)
    preview = preview_dataframe(df, 20)
    suggestions = suggest_charts(df, profile)

    return {
        "session_id": session_id,
        "filename": entry["filename"],
        "profile": profile,
        "preview": preview,
        "suggestions": suggestions,
        "history": entry["history"],
        "file_size": entry.get("file_size", 0),
    }


@app.get("/api/session/{session_id}/quality-report")
def get_quality_report(session_id: str):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found or expired.")
    df = entry["df"]
    profile = profile_dataframe(df)
    try:
        report = analyze_dataset_quality(df, profile)
    except Exception as exc:
        raise HTTPException(422, f"Quality report generation failed: {exc}")
    return report


@app.post("/api/session/{session_id}/chart")
def generate_chart(session_id: str, body: dict):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    chart_type = body.get("chart_type", "histogram")
    config = body.get("config", {})
    title = body.get("title", chart_type.capitalize())
    try:
        spec = build_chart(entry["df"], config, chart_type, title)
    except Exception as exc:
        raise HTTPException(422, f"Chart generation failed: {exc}")
    return {"spec": spec}


@app.post("/api/session/{session_id}/clean")
def clean_data(session_id: str, body: dict):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    action = body.get("action")
    params = body.get("params", {})
    if not action:
        raise HTTPException(422, "Missing 'action' in request body.")

    if action == "reset":
        store.update_df(session_id, entry["original_df"], "reset")
    else:
        cleaned = apply_clean(entry["df"], action, params)
        store.update_df(session_id, cleaned, action)

    updated = store.get(session_id)
    df = updated["df"]
    profile = profile_dataframe(df)
    preview = preview_dataframe(df, 20)
    suggestions = suggest_charts(df, profile)
    return {
        "session_id": session_id,
        "profile": profile,
        "preview": preview,
        "suggestions": suggestions,
        "history": updated["history"],
    }


@app.get("/api/session/{session_id}/download")
def download_data(session_id: str, format: str = "csv"):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    df = entry["df"]
    base = Path(entry["filename"]).stem or "data"

    if format.lower() == "json":
        buf = io.StringIO()
        records = json.loads(df.to_json(orient="records"))
        buf.write(json.dumps(records, indent=2, default=str))
        media = "application/json"
        ext = "json"
    else:
        buf = io.StringIO()
        df.to_csv(buf, index=False)
        media = "text/csv"
        ext = "csv"

    buf.seek(0)
    headers = {"Content-Disposition": f'attachment; filename="{base}_cleaned.{ext}"'}
    return StreamingResponse(iter([buf.getvalue()]), media_type=media, headers=headers)


# ---------------------------------------------------------------------------
# Correlation analysis
# ---------------------------------------------------------------------------

@app.get("/api/session/{session_id}/correlation")
def get_correlation(session_id: str, method: str = "pearson"):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found or expired.")
    try:
        report = compute_correlation(entry["df"], method)
    except Exception as exc:
        raise HTTPException(422, f"Correlation analysis failed: {exc}")
    return report


@app.post("/api/session/{session_id}/correlation/heatmap")
def get_heatmap(session_id: str, body: dict):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    try:
        spec = build_heatmap(body.get("spec", {}), body.get("title", "Correlation Heatmap"))
    except Exception as exc:
        raise HTTPException(422, f"Heatmap generation failed: {exc}")
    return {"spec": spec}


@app.post("/api/session/{session_id}/correlation/scatter")
def get_scatter(session_id: str, body: dict):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    col_a = body.get("col_a")
    col_b = body.get("col_b")
    if not col_a or not col_b:
        raise HTTPException(422, "col_a and col_b are required.")
    try:
        spec = build_scatter(entry["df"], col_a, col_b)
    except Exception as exc:
        raise HTTPException(422, f"Scatter plot failed: {exc}")
    return {"spec": spec}


@app.post("/api/session/{session_id}/correlation/network")
def get_network(session_id: str, body: dict):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    try:
        spec = build_network_graph(body.get("network", {}))
    except Exception as exc:
        raise HTTPException(422, f"Network graph failed: {exc}")
    return {"spec": spec}


@app.post("/api/session/{session_id}/correlation/export")
def export_correlation(session_id: str, body: dict):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    fmt = body.get("format", "csv")
    pairs = body.get("pairs", [])
    base = Path(entry["filename"]).stem or "correlation"

    if fmt == "json":
        content = export_correlation_json(pairs)
        media = "application/json"
        ext = "json"
    else:
        content = export_correlation_csv(pairs)
        media = "text/csv"
        ext = "csv"

    headers = {"Content-Disposition": f'attachment; filename="{base}_correlation.{ext}"'}
    return StreamingResponse(iter([content]), media_type=media, headers=headers)


# ---------------------------------------------------------------------------
# Distribution analysis
# ---------------------------------------------------------------------------

@app.get("/api/session/{session_id}/distribution")
def get_distribution(session_id: str):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found or expired.")
    try:
        report = compute_distribution(entry["df"])
    except Exception as exc:
        raise HTTPException(422, f"Distribution analysis failed: {exc}")
    return report


@app.post("/api/session/{session_id}/distribution/chart")
def get_distribution_chart(session_id: str, body: dict):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    col = body.get("column")
    chart_type = body.get("chart_type", "histogram")
    if not col:
        raise HTTPException(422, "column is required.")
    try:
        spec = build_distribution_chart(entry["df"], col, chart_type)
    except Exception as exc:
        raise HTTPException(422, f"Chart generation failed: {exc}")
    return {"spec": spec}


@app.post("/api/session/{session_id}/distribution/compare")
def get_distribution_compare(session_id: str, body: dict):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    cols = body.get("columns", [])
    chart_type = body.get("chart_type", "overlay_hist")
    try:
        result = build_comparison_overlay(entry["df"], cols, chart_type)
    except Exception as exc:
        raise HTTPException(422, f"Comparison failed: {exc}")
    return {"result": result}


@app.post("/api/session/{session_id}/distribution/transform")
def get_transform_preview(session_id: str, body: dict):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    col = body.get("column")
    transform = body.get("transform", "log")
    if not col:
        raise HTTPException(422, "column is required.")
    try:
        result = build_transform_preview(entry["df"], col, transform)
    except Exception as exc:
        raise HTTPException(422, f"Transform failed: {exc}")
    return result


@app.post("/api/session/{session_id}/distribution/export")
def export_distribution(session_id: str, body: dict):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    fmt = body.get("format", "csv")
    columns_analysis = body.get("columns", [])
    base = Path(entry["filename"]).stem or "distribution"

    if fmt == "json":
        content = export_distribution_json(columns_analysis)
        media = "application/json"
        ext = "json"
    else:
        content = export_distribution_csv(columns_analysis)
        media = "text/csv"
        ext = "csv"

    headers = {"Content-Disposition": f'attachment; filename="{base}_distribution.{ext}"'}
    return StreamingResponse(iter([content]), media_type=media, headers=headers)


# ---------------------------------------------------------------------------
# AI Studio integration
# ---------------------------------------------------------------------------

@app.get("/api/ai/health")
def ai_health():
    ok = ai_check_connection()
    return {"status": "ok" if ok else "error", "configured": bool(ai_check_connection.__code__.co_consts)}


@app.post("/api/ai/analyze")
def ai_analyze_endpoint(body: dict):
    prompt = body.get("prompt", "")
    if not prompt:
        raise HTTPException(422, "prompt is required.")
    try:
        result = ai_analyze(prompt)
    except Exception as exc:
        raise HTTPException(422, f"AI request failed: {exc}")
    return {"result": result}


@app.post("/api/ai/chat")
def ai_chat_endpoint(body: dict):
    messages = body.get("messages", [])
    if not messages:
        raise HTTPException(422, "messages is required.")
    try:
        result = ai_chat(messages)
    except Exception as exc:
        raise HTTPException(422, f"AI request failed: {exc}")
    return {"result": result}


# ---------------------------------------------------------------------------
# EDA Report
# ---------------------------------------------------------------------------

@app.post("/api/session/{session_id}/eda-report")
def generate_eda(session_id: str, body: dict):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found or expired.")
    report_type = body.get("report_type", "full")
    custom_title = body.get("custom_title", "")
    custom_author = body.get("custom_author", "")
    branding = {}
    if custom_title:
        branding["title"] = custom_title
    if custom_author:
        branding["author"] = custom_author
    try:
        df = entry["df"]
        profile = profile_dataframe(df)
        report = generate_eda_report(df, entry.get("filename", "data"), profile=profile, report_type=report_type, branding=branding or None)
    except Exception as exc:
        raise HTTPException(422, f"EDA report generation failed: {exc}")
    return report


@app.post("/api/session/{session_id}/eda-report/export")
def export_eda(session_id: str, body: dict):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found or expired.")
    fmt = body.get("format", "html")
    report_data = body.get("report_data", None)
    if not report_data:
        raise HTTPException(422, "report_data is required.")
    base = Path(entry["filename"]).stem or "eda_report"
    try:
        if fmt == "html":
            content = build_html_report(report_data)
            media = "text/html"
            ext = "html"
        elif fmt == "json":
            content = json.dumps(report_data, indent=2, default=str)
            media = "application/json"
            ext = "json"
        elif fmt == "markdown":
            content = export_markdown(report_data)
            media = "text/markdown"
            ext = "md"
        elif fmt == "excel":
            content = export_excel_summary(report_data)
            media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ext = "xlsx"
        else:
            raise HTTPException(422, f"Unsupported format: {fmt}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, f"Export failed: {exc}")
    headers = {"Content-Disposition": f'attachment; filename="{base}_eda_report.{ext}"'}
    if fmt == "excel":
        buf = io.BytesIO(content)
        buf.seek(0)
        return StreamingResponse(iter([buf.read()]), media_type=media, headers=headers)
    return StreamingResponse(iter([content]), media_type=media, headers=headers)


# ---------------------------------------------------------------------------
# AI Insights Engine
# ---------------------------------------------------------------------------

@app.post("/api/session/{session_id}/ai-insights")
def generate_insights(session_id: str, body: dict):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found or expired.")
    force_refresh = body.get("force_refresh", False)
    extra_context = body.get("context", "")
    try:
        df = entry["df"]
        profile = profile_dataframe(df)
        insights = generate_ai_insights(df, profile, session_id, extra_context, force_refresh)
    except Exception as exc:
        raise HTTPException(422, f"AI insights generation failed: {exc}")
    return insights


@app.get("/api/session/{session_id}/ai-insights")
def get_insights(session_id: str):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found or expired.")
    cached = get_cached_insights(session_id)
    if cached:
        return cached
    raise HTTPException(404, "No cached insights. Generate insights first via POST.")


@app.delete("/api/session/{session_id}/ai-insights")
def delete_insights_cache(session_id: str):
    clear_cache(session_id)
    return {"status": "cleared"}


@app.post("/api/session/{session_id}/ai-insights/export")
def export_insights(session_id: str, body: dict):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found or expired.")
    fmt = body.get("format", "markdown")
    report_data = body.get("report_data", None)
    if not report_data:
        raise HTTPException(422, "report_data is required.")
    base = Path(entry["filename"]).stem or "ai_insights"
    try:
        if fmt == "markdown":
            content = export_insights_markdown(report_data)
            media = "text/markdown"
            ext = "md"
        elif fmt == "html":
            content = export_insights_html(report_data)
            media = "text/html"
            ext = "html"
        elif fmt == "json":
            content = export_insights_json(report_data)
            media = "application/json"
            ext = "json"
        elif fmt == "csv":
            content = export_insights_csv(report_data)
            media = "text/csv"
            ext = "csv"
        else:
            raise HTTPException(422, f"Unsupported format: {fmt}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, f"Export failed: {exc}")
    headers = {"Content-Disposition": f'attachment; filename="{base}_ai_insights.{ext}"'}
    return StreamingResponse(iter([content]), media_type=media, headers=headers)


# ---------------------------------------------------------------------------
# Advanced Cleaning
# ---------------------------------------------------------------------------

@app.get("/api/session/{session_id}/cleaning/missing")
def get_missing_analysis(session_id: str):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    return analyze_missing(entry["df"])


@app.post("/api/session/{session_id}/cleaning/impute")
def impute_data(session_id: str, body: dict):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    method = body.get("method", "mean")
    columns = body.get("columns")
    try:
        if method == "knn":
            cleaned = impute_knn(entry["df"], columns)
        elif method == "interpolation":
            cleaned = impute_interpolation(entry["df"], columns)
        else:
            cleaned = apply_clean(entry["df"], "fill_nulls", {"strategy": method, "columns": columns})
        store.update_df(session_id, cleaned, f"impute_{method}")
    except Exception as exc:
        raise HTTPException(422, f"Imputation failed: {exc}")
    updated = store.get(session_id)
    df = updated["df"]
    return {"profile": profile_dataframe(df), "preview": preview_dataframe(df, 20), "history": updated["history"]}


@app.post("/api/session/{session_id}/cleaning/convert")
def convert_types(session_id: str, body: dict):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    conversions = body.get("conversions", {})
    try:
        cleaned = convert_datatypes(entry["df"], conversions)
        store.update_df(session_id, cleaned, "convert_types")
    except Exception as exc:
        raise HTTPException(422, f"Conversion failed: {exc}")
    updated = store.get(session_id)
    df = updated["df"]
    return {"profile": profile_dataframe(df), "preview": preview_dataframe(df, 20), "history": updated["history"]}


@app.get("/api/session/{session_id}/cleaning/invalid")
def get_invalid_values(session_id: str):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    return detect_invalid_values(entry["df"])


@app.post("/api/session/{session_id}/cleaning/normalize")
def normalize_text_data(session_id: str, body: dict):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    columns = body.get("columns")
    operations = body.get("operations", ["lowercase", "strip"])
    try:
        cleaned = normalize_text(entry["df"], columns, operations)
        store.update_df(session_id, cleaned, "normalize_text")
    except Exception as exc:
        raise HTTPException(422, f"Normalization failed: {exc}")
    updated = store.get(session_id)
    df = updated["df"]
    return {"profile": profile_dataframe(df), "preview": preview_dataframe(df, 20), "history": updated["history"]}


@app.get("/api/session/{session_id}/cleaning/outliers")
def get_outlier_analysis(session_id: str):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    return detect_outliers(entry["df"])


@app.post("/api/session/{session_id}/cleaning/outliers")
def treat_outlier_data(session_id: str, body: dict):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    columns = body.get("columns")
    method = body.get("method", "clip")
    try:
        cleaned = treat_outliers(entry["df"], columns, method)
        store.update_df(session_id, cleaned, f"treat_outliers_{method}")
    except Exception as exc:
        raise HTTPException(422, f"Outlier treatment failed: {exc}")
    updated = store.get(session_id)
    df = updated["df"]
    return {"profile": profile_dataframe(df), "preview": preview_dataframe(df, 20), "history": updated["history"]}


@app.get("/api/session/{session_id}/cleaning/duplicates")
def get_duplicate_analysis(session_id: str):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    return analyze_duplicates(entry["df"])


@app.post("/api/session/{session_id}/cleaning/auto")
def auto_clean_data(session_id: str):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    try:
        cleaned, actions = auto_clean(entry["df"])
        store.update_df(session_id, cleaned, "auto_clean")
    except Exception as exc:
        raise HTTPException(422, f"Auto-clean failed: {exc}")
    updated = store.get(session_id)
    df = updated["df"]
    return {"profile": profile_dataframe(df), "preview": preview_dataframe(df, 20), "history": updated["history"], "actions": actions}


@app.get("/api/session/{session_id}/cleaning/report")
def get_cleaning_report(session_id: str):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    return generate_cleaning_report(entry["original_df"], entry["df"])


# ---------------------------------------------------------------------------
# Ask Your Data (NLQ)
# ---------------------------------------------------------------------------

@app.post("/api/session/{session_id}/ask")
def ask_question(session_id: str, body: dict):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    question = body.get("question", "").strip()
    if not question:
        raise HTTPException(422, "question is required.")
    try:
        profile = profile_dataframe(entry["df"])
        result = process_question(entry["df"], profile, question)
    except Exception as exc:
        raise HTTPException(422, f"Query failed: {exc}")
    return result


@app.get("/api/session/{session_id}/ask/suggestions")
def get_ask_suggestions(session_id: str):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    profile = profile_dataframe(entry["df"])
    return {"suggestions": suggest_questions(profile)}


# ---------------------------------------------------------------------------
# Feature Engineering
# ---------------------------------------------------------------------------

@app.post("/api/session/{session_id}/feature-engineering/encode")
def encode_data(session_id: str, body: dict):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    method = body.get("method", "onehot")
    columns = body.get("columns", [])
    if not columns:
        raise HTTPException(422, "columns is required.")
    try:
        if method == "onehot":
            cleaned = encode_onehot(entry["df"], columns)
        elif method == "label":
            cleaned = encode_label(entry["df"], columns)
        elif method == "ordinal":
            cleaned = encode_ordinal(entry["df"], columns)
        elif method == "frequency":
            cleaned = encode_frequency(entry["df"], columns)
        elif method == "target":
            target = body.get("target")
            if not target:
                raise HTTPException(422, "target column required for target encoding.")
            cleaned = encode_target(entry["df"], columns, target)
        else:
            raise HTTPException(422, f"Unknown encoding method: {method}")
        store.update_df(session_id, cleaned, f"encode_{method}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, f"Encoding failed: {exc}")
    updated = store.get(session_id)
    df = updated["df"]
    return {"profile": profile_dataframe(df), "preview": preview_dataframe(df, 20), "columns": list(df.columns), "history": updated["history"]}


@app.post("/api/session/{session_id}/feature-engineering/scale")
def scale_data(session_id: str, body: dict):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    method = body.get("method", "standard")
    columns = body.get("columns")
    try:
        if method == "standard":
            cleaned = scale_standard(entry["df"], columns)
        elif method == "minmax":
            cleaned = scale_minmax(entry["df"], columns)
        elif method == "robust":
            cleaned = scale_robust(entry["df"], columns)
        else:
            raise HTTPException(422, f"Unknown scaling method: {method}")
        store.update_df(session_id, cleaned, f"scale_{method}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, f"Scaling failed: {exc}")
    updated = store.get(session_id)
    df = updated["df"]
    return {"profile": profile_dataframe(df), "preview": preview_dataframe(df, 20), "history": updated["history"]}


@app.post("/api/session/{session_id}/feature-engineering/transform")
def transform_data(session_id: str, body: dict):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    method = body.get("method", "log")
    columns = body.get("columns", [])
    if not columns:
        raise HTTPException(422, "columns is required.")
    try:
        if method == "log":
            cleaned = transform_log(entry["df"], columns)
        elif method == "sqrt":
            cleaned = transform_sqrt(entry["df"], columns)
        elif method == "power":
            cleaned = transform_power(entry["df"], columns)
        else:
            raise HTTPException(422, f"Unknown transform method: {method}")
        store.update_df(session_id, cleaned, f"transform_{method}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, f"Transform failed: {exc}")
    updated = store.get(session_id)
    df = updated["df"]
    return {"profile": profile_dataframe(df), "preview": preview_dataframe(df, 20), "history": updated["history"]}


@app.post("/api/session/{session_id}/feature-engineering/create")
def create_features(session_id: str, body: dict):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    operation = body.get("operation")
    columns = body.get("columns", [])
    try:
        if operation == "date_features":
            date_col = body.get("date_column")
            if not date_col:
                raise HTTPException(422, "date_column is required.")
            cleaned = create_date_features(entry["df"], date_col)
        elif operation == "polynomial":
            degree = body.get("degree", 2)
            cleaned = create_polynomial(entry["df"], columns, degree)
        elif operation == "interactions":
            cleaned = create_interactions(entry["df"], columns)
        elif operation == "binning":
            col = body.get("column")
            bins = body.get("bins", 5)
            if not col:
                raise HTTPException(422, "column is required.")
            cleaned = create_binning(entry["df"], col, bins)
        elif operation == "missing_indicator":
            cleaned = create_missing_indicator(entry["df"], columns or None)
        else:
            raise HTTPException(422, f"Unknown operation: {operation}")
        store.update_df(session_id, cleaned, f"create_{operation}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, f"Feature creation failed: {exc}")
    updated = store.get(session_id)
    df = updated["df"]
    return {"profile": profile_dataframe(df), "preview": preview_dataframe(df, 20), "columns": list(df.columns), "history": updated["history"]}


@app.get("/api/session/{session_id}/feature-engineering/recommend")
def get_feature_recommendations(session_id: str):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    profile = profile_dataframe(entry["df"])
    return {"recommendations": recommend_features(entry["df"], profile)}


# ---------------------------------------------------------------------------
# Statistical Tests
# ---------------------------------------------------------------------------

@app.post("/api/session/{session_id}/stats/descriptive")
def get_descriptive_stats(session_id: str, body: dict):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    column = body.get("column")
    if not column or column not in entry["df"].columns:
        raise HTTPException(422, "Valid column is required.")
    return descriptive_stats(entry["df"][column])


@app.post("/api/session/{session_id}/stats/normality")
def get_normality_tests(session_id: str, body: dict):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    column = body.get("column")
    if not column or column not in entry["df"].columns:
        raise HTTPException(422, "Valid column is required.")
    return {"tests": run_all_normality_tests(entry["df"][column])}


@app.post("/api/session/{session_id}/stats/ttest")
def get_ttest(session_id: str, body: dict):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    col_a = body.get("column_a")
    col_b = body.get("column_b")
    paired = body.get("paired", False)
    if not col_a or not col_b:
        raise HTTPException(422, "column_a and column_b are required.")
    try:
        if paired:
            result = ttest_paired(entry["df"][col_a], entry["df"][col_b])
        else:
            result = ttest_ind(entry["df"][col_a], entry["df"][col_b])
    except Exception as exc:
        raise HTTPException(422, f"T-test failed: {exc}")
    return result


@app.post("/api/session/{session_id}/stats/anova")
def get_anova(session_id: str, body: dict):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    column = body.get("column")
    group_by = body.get("group_by")
    if not column or not group_by:
        raise HTTPException(422, "column and group_by are required.")
    try:
        groups = [group[column].dropna() for _, group in entry["df"].groupby(group_by)]
        result = anova_one_way(groups)
    except Exception as exc:
        raise HTTPException(422, f"ANOVA failed: {exc}")
    return result


@app.post("/api/session/{session_id}/stats/chi-square")
def get_chi_square(session_id: str, body: dict):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    col_a = body.get("column_a")
    col_b = body.get("column_b")
    if not col_a or not col_b:
        raise HTTPException(422, "column_a and column_b are required.")
    return chi_square_test(entry["df"], col_a, col_b)


@app.post("/api/session/{session_id}/stats/correlation-test")
def get_correlation_test(session_id: str, body: dict):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    col_a = body.get("column_a")
    col_b = body.get("column_b")
    method = body.get("method", "pearson")
    if not col_a or not col_b:
        raise HTTPException(422, "column_a and column_b are required.")
    if method == "spearman":
        return spearman_test(entry["df"][col_a], entry["df"][col_b])
    return pearson_test(entry["df"][col_a], entry["df"][col_b])


# ---------------------------------------------------------------------------
# SQL Generator
# ---------------------------------------------------------------------------

@app.post("/api/session/{session_id}/sql")
def generate_sql_query(session_id: str, body: dict):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    question = body.get("question", "").strip()
    dialect = body.get("dialect", "MySQL")
    if not question:
        raise HTTPException(422, "question is required.")
    try:
        profile = profile_dataframe(entry["df"])
        result = generate_sql(entry["df"], profile, question, dialect)
    except Exception as exc:
        raise HTTPException(422, f"SQL generation failed: {exc}")
    return result


# ---------------------------------------------------------------------------
# Code Generator
# ---------------------------------------------------------------------------

@app.post("/api/session/{session_id}/code")
def generate_python_code(session_id: str, body: dict):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    question = body.get("question", "").strip()
    if not question:
        raise HTTPException(422, "question is required.")
    try:
        profile = profile_dataframe(entry["df"])
        result = generate_code(entry["df"], profile, question)
    except Exception as exc:
        raise HTTPException(422, f"Code generation failed: {exc}")
    return result


# ---------------------------------------------------------------------------
# AI Chart Advisor
# ---------------------------------------------------------------------------

@app.get("/api/session/{session_id}/chart-recommendations")
def get_chart_recommendations(session_id: str):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    profile = profile_dataframe(entry["df"])
    return {"recommendations": recommend_charts(entry["df"], profile)}


# ---------------------------------------------------------------------------
# Dashboard Builder
# ---------------------------------------------------------------------------

@app.post("/api/session/{session_id}/dashboard/save")
def save_dashboard(session_id: str, body: dict):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    dashboard = body.get("dashboard", {})
    if not dashboard:
        raise HTTPException(422, "dashboard is required.")
    dash_id = dashboard_store.save(session_id, dashboard)
    return {"id": dash_id, "version": dashboard.get("version", 1)}


@app.get("/api/session/{session_id}/dashboard/list")
def list_dashboards(session_id: str):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    return {"dashboards": dashboard_store.list_dashboards(session_id)}


@app.get("/api/session/{session_id}/dashboard/{dash_id}")
def get_dashboard(session_id: str, dash_id: str):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    dashboard = dashboard_store.get(session_id, dash_id)
    if dashboard is None:
        raise HTTPException(404, "Dashboard not found.")
    return {"dashboard": dashboard}


@app.delete("/api/session/{session_id}/dashboard/{dash_id}")
def delete_dashboard(session_id: str, dash_id: str):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    ok = dashboard_store.delete(session_id, dash_id)
    if not ok:
        raise HTTPException(404, "Dashboard not found.")
    return {"status": "deleted"}


@app.post("/api/session/{session_id}/dashboard/{dash_id}/duplicate")
def duplicate_dashboard(session_id: str, dash_id: str):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    new_id = dashboard_store.duplicate(session_id, dash_id)
    if new_id is None:
        raise HTTPException(404, "Dashboard not found.")
    return {"id": new_id}


@app.get("/api/session/{session_id}/dashboard/{dash_id}/versions")
def get_versions(session_id: str, dash_id: str):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    return {"versions": dashboard_store.get_versions(session_id, dash_id)}


@app.post("/api/session/{session_id}/dashboard/{dash_id}/restore/{version}")
def restore_version(session_id: str, dash_id: str, version: int):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    restored = dashboard_store.restore_version(session_id, dash_id, version)
    if restored is None:
        raise HTTPException(404, "Version not found.")
    return {"dashboard": restored}


@app.post("/api/session/{session_id}/dashboard/chart")
def dashboard_chart(session_id: str, body: dict):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    widget = body.get("widget", {})
    try:
        spec = build_dashboard_chart(entry["df"], widget)
    except Exception as exc:
        raise HTTPException(422, f"Chart generation failed: {exc}")
    return {"spec": spec}


@app.post("/api/session/{session_id}/dashboard/ai-generate")
def ai_generate_dashboard(session_id: str):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    df = entry["df"]
    profile = profile_dataframe(df)
    dashboard = generate_ai_dashboard(df, profile)
    return {"dashboard": dashboard}


@app.post("/api/session/{session_id}/dashboard/chart-insight")
def chart_insight(session_id: str, body: dict):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    widget = body.get("widget", {})
    try:
        insight = generate_chart_insight(entry["df"], widget)
    except Exception as exc:
        raise HTTPException(422, f"Insight generation failed: {exc}")
    return {"insight": insight}


@app.get("/api/session/{session_id}/dashboard/templates")
def get_templates():
    return {"templates": list(DASHBOARD_TEMPLATES.keys())}


@app.get("/api/session/{session_id}/dashboard/template/{name}")
def get_template(session_id: str, name: str):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    template = DASHBOARD_TEMPLATES.get(name)
    if template is None:
        raise HTTPException(404, f"Template '{name}' not found.")
    return {"dashboard": template}


@app.post("/api/session/{session_id}/dashboard/filter")
def apply_dashboard_filter(session_id: str, body: dict):
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(404, "Session not found.")
    filters = body.get("filters", [])
    df = entry["df"].copy()
    for f in filters:
        col = f.get("column")
        op = f.get("operator", "eq")
        val = f.get("value")
        if not col or val is None or col not in df.columns:
            continue
        if op == "eq":
            df = df[df[col].astype(str) == str(val)]
        elif op == "neq":
            df = df[df[col].astype(str) != str(val)]
        elif op == "gt":
            df = df[pd.to_numeric(df[col], errors="coerce") > float(val)]
        elif op == "gte":
            df = df[pd.to_numeric(df[col], errors="coerce") >= float(val)]
        elif op == "lt":
            df = df[pd.to_numeric(df[col], errors="coerce") < float(val)]
        elif op == "lte":
            df = df[pd.to_numeric(df[col], errors="coerce") <= float(val)]
        elif op == "contains":
            df = df[df[col].astype(str).str.contains(str(val), case=False, na=False)]
        elif op == "in":
            if isinstance(val, list):
                df = df[df[col].astype(str).isin([str(v) for v in val])]
    profile = profile_dataframe(df)
    preview = preview_dataframe(df, 20)
    suggestions = suggest_charts(df, profile)
    return {"profile": profile, "preview": preview, "suggestions": suggestions, "row_count": len(df)}


# ---------------------------------------------------------------------------
# Project management
# ---------------------------------------------------------------------------

@app.get("/api/projects")
def list_projects(status: str | None = None):
    return project_store.list_projects(status=status)


@app.post("/api/projects")
def create_project(body: dict):
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(400, "Project name is required")
    description = body.get("description", "")
    settings = body.get("settings", {})
    project = project_store.create(name, description, settings)
    return project


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    project = project_store.get(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


@app.put("/api/projects/{project_id}")
def update_project(project_id: str, body: dict):
    project = project_store.update(project_id, body)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str):
    if not project_store.delete(project_id):
        raise HTTPException(404, "Project not found")
    return {"ok": True}


@app.post("/api/projects/{project_id}/datasets")
def add_dataset_to_project(project_id: str, body: dict):
    session_id = body.get("session_id", "").strip()
    filename = body.get("filename", "unknown")
    if not session_id:
        raise HTTPException(400, "session_id is required")
    if not store.exists(session_id):
        raise HTTPException(404, "Dataset session not found")
    project = project_store.add_dataset(project_id, session_id, filename)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


@app.delete("/api/projects/{project_id}/datasets/{session_id}")
def remove_dataset_from_project(project_id: str, session_id: str):
    project = project_store.remove_dataset(project_id, session_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


@app.post("/api/projects/{project_id}/dashboards")
def add_dashboard_to_project(project_id: str, body: dict):
    dashboard_id = body.get("dashboard_id", "").strip()
    title = body.get("title", "Untitled Dashboard")
    if not dashboard_id:
        raise HTTPException(400, "dashboard_id is required")
    project = project_store.add_dashboard(project_id, dashboard_id, title)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


@app.delete("/api/projects/{project_id}/dashboards/{dashboard_id}")
def remove_dashboard_from_project(project_id: str, dashboard_id: str):
    project = project_store.remove_dashboard(project_id, dashboard_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


@app.get("/api/projects/{project_id}/activity")
def get_project_activity(project_id: str, limit: int = 50):
    project = project_store.get(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project_store.get_activity(project_id, limit)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Serve frontend (static files) — mounted last so API routes take priority
# ---------------------------------------------------------------------------

app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
