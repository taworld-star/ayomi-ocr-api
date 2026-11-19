import io
import os
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from fastapi.testclient import TestClient

import app as service

FIXTURES = Path(__file__).parent / "fixtures"
TEXT_PDF = (FIXTURES / "A-pelangi-biru-izin-operasional.pdf").read_bytes()
SCAN_JPG = (FIXTURES / "C-pondok-ceria-lentera-izin-operasional-scan.jpg").read_bytes()
AUTH = {"Authorization": f"Bearer {os.environ['API_TOKEN']}"}


@pytest.fixture(scope="module")
def client():
    with TestClient(service.app) as test_client:
        yield test_client


def post(client, data, name="dokumen.pdf", headers=AUTH, **form):
    return client.post("/ocr", headers=headers, files={"file": (name, data)}, data=form)


def blank_pdf(pages):
    pdf = pdfium.PdfDocument.new()
    for _ in range(pages):
        pdf.new_page(595, 842)
    buffer = io.BytesIO()
    pdf.save(buffer)
    return buffer.getvalue()


def test_health_reports_engine_without_token(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["engine"]["recognizer"] == "PP-OCRv5 mobile (latin)"


def test_token_is_required(client):
    assert post(client, TEXT_PDF, headers={}).status_code == 401
    wrong = post(client, TEXT_PDF, headers={"Authorization": "Bearer salah"})
    assert wrong.status_code == 401
    assert wrong.json()["detail"]["code"] == "unauthorized"


def test_rejects_empty_unknown_and_oversized_files(client, monkeypatch):
    assert post(client, b"").json()["detail"]["code"] == "empty_file"
    unknown = post(client, b"bukan dokumen", name="catatan.txt")
    assert unknown.status_code == 415 and unknown.json()["detail"]["code"] == "unsupported_format"
    broken = post(client, b"%PDF-1.7 rusak")
    assert broken.status_code == 400 and broken.json()["detail"]["code"] == "invalid_pdf"
    monkeypatch.setattr(service, "MAX_BYTES", 100)
    assert post(client, TEXT_PDF).status_code == 413


def test_pdf_page_limit(client):
    response = post(client, blank_pdf(21))
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "too_many_pages"


def test_text_pdf_is_read_from_its_text_layer(client):
    body = post(client, TEXT_PDF).json()
    page = body["pages"][0]
    assert body["kind"] == "pdf" and body["page_count"] == 1
    assert page["source"] == "text_layer"
    assert "SPES/IO/KS/2025/0012" in page["text"]
    assert "Taman Asuh Pelangi Biru" in page["text"]


def test_scanned_photo_is_read_with_ocr(client):
    body = post(client, SCAN_JPG, name="scan.jpg").json()
    page = body["pages"][0]
    assert body["kind"] == "jpeg" and page["source"] == "ocr"
    assert "SPES/IO/KS/2022/0031" in page["text"]
    assert "Pondok Ceria Lentera" in page["text"]
    assert "30 Juni 2025" in page["text"]
    assert all(0 <= line["confidence"] <= 1 and len(line["box"]) == 4 for line in page["lines"])


def test_blank_page_without_text_goes_to_ocr(client):
    body = post(client, blank_pdf(1)).json()
    assert body["pages"][0]["source"] == "ocr"
    assert body["pages"][0]["text"] == ""
