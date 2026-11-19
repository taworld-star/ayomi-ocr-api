from contextlib import asynccontextmanager
import hmac
import os
import threading
import time

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

import ocr_engine
from ocr_engine import ENGINE_INFO, DocumentError, read_document

VERSION = "1.0.0"
MAX_BYTES = 15 * 1024 * 1024
API_TOKEN = os.environ.get("API_TOKEN", "")
if len(API_TOKEN) < 32:
    raise RuntimeError("Set API_TOKEN (minimal 32 karakter acak) sebelum menjalankan layanan.")

_slots = threading.BoundedSemaphore(int(os.environ.get("OCR_CONCURRENCY", "1")))
QUEUE_SECONDS = 120


@asynccontextmanager
async def lifespan(_app):
    await run_in_threadpool(ocr_engine.engine)
    yield


app = FastAPI(title="Ayomi OCR Dokumen", version=VERSION, lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)


def fail(status, code, message):
    raise HTTPException(status_code=status, detail={"code": code, "error": message})


def authorize(header):
    if not hmac.compare_digest(header or "", f"Bearer {API_TOKEN}"):
        fail(401, "unauthorized", "Token API tidak valid.")


def run_ocr(data, force_ocr):
    if not _slots.acquire(timeout=QUEUE_SECONDS):
        raise DocumentError(503, "busy", "Layanan OCR sedang sibuk. Coba lagi beberapa saat.")
    try:
        return read_document(data, force_ocr=force_ocr)
    finally:
        _slots.release()


@app.get("/health")
def health():
    return {"status": "ok", "version": VERSION, "engine": ENGINE_INFO}


@app.post("/ocr")
async def ocr(
    file: UploadFile = File(...),
    force_ocr: bool = Form(False),
    authorization: str | None = Header(default=None),
):
    authorize(authorization)
    data = await file.read(MAX_BYTES + 1)
    if not data:
        fail(400, "empty_file", "Berkas kosong.")
    if len(data) > MAX_BYTES:
        fail(413, "file_too_large", "Berkas maksimal 15 MB.")
    started = time.perf_counter()
    try:
        result = await run_in_threadpool(run_ocr, data, force_ocr)
    except DocumentError as error:
        fail(error.status, error.code, error.message)
    return {
        **result,
        "page_count": len(result["pages"]),
        "engine": ENGINE_INFO,
        "version": VERSION,
        "duration_ms": round((time.perf_counter() - started) * 1000),
    }

