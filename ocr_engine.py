import io
import threading

import numpy as np
import pypdfium2 as pdfium
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_PAGES = 20
MAX_IMAGE_SIDE = 2400
RENDER_DPI = 150
MIN_TEXT_CHARS = 20
Image.MAX_IMAGE_PIXELS = 60_000_000

ENGINE_INFO = {
    "name": "rapidocr",
    "detector": "PP-OCRv5 mobile",
    "recognizer": "PP-OCRv5 mobile (latin)",
    "runtime": "onnxruntime-cpu",
}

_engine = None
_engine_lock = threading.Lock()


class DocumentError(Exception):

    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def engine():
    global _engine
    with _engine_lock:
        if _engine is None:
            from rapidocr import EngineType, LangRec, ModelType, OCRVersion, RapidOCR

            _engine = RapidOCR(params={
                "Global.log_level": "warning",
                "Det.engine_type": EngineType.ONNXRUNTIME,
                "Det.ocr_version": OCRVersion.PPOCRV5,
                "Det.model_type": ModelType.MOBILE,
                "Rec.engine_type": EngineType.ONNXRUNTIME,
                "Rec.ocr_version": OCRVersion.PPOCRV5,
                "Rec.model_type": ModelType.MOBILE,
                "Rec.lang_type": LangRec.LATIN,
            })
        return _engine


def detect_kind(data):
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    raise DocumentError(415, "unsupported_format", "Format harus PDF, JPG, atau PNG.")


def ocr_image(image):
    image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    result = engine()(np.asarray(image))
    lines = []
    for box, text, score in zip(result.boxes if result.boxes is not None else [],
                                result.txts or [], result.scores or []):
        text = str(text).strip()
        if text:
            lines.append({
                "text": text,
                "confidence": round(float(score), 4),
                "box": [[round(float(x)), round(float(y))] for x, y in box],
            })
    return "\n".join(line["text"] for line in lines), lines


def read_image(data):
    try:
        with Image.open(io.BytesIO(data)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError):
        raise DocumentError(400, "invalid_image", "Gambar tidak dapat dibaca.")
    text, lines = ocr_image(image)
    return [{"page": 1, "source": "ocr", "text": text, "lines": lines}]


def read_pdf(data, force_ocr):
    try:
        pdf = pdfium.PdfDocument(data)
    except pdfium.PdfiumError:
        raise DocumentError(400, "invalid_pdf", "PDF tidak dapat dibuka (rusak atau terkunci kata sandi).")
    try:
        if len(pdf) == 0:
            raise DocumentError(400, "invalid_pdf", "PDF tidak memiliki halaman.")
        if len(pdf) > MAX_PAGES:
            raise DocumentError(413, "too_many_pages", f"PDF maksimal {MAX_PAGES} halaman.")
        pages = []
        for index in range(len(pdf)):
            page = pdf[index]
            text = ""
            if not force_ocr:
                textpage = page.get_textpage()
                text = textpage.get_text_range().replace("\r\n", "\n").replace("\r", "\n").strip()
                textpage.close()
            if len(text) >= MIN_TEXT_CHARS:
                pages.append({"page": index + 1, "source": "text_layer", "text": text, "lines": []})
            else:
                image = page.render(scale=RENDER_DPI / 72).to_pil().convert("RGB")
                text, lines = ocr_image(image)
                pages.append({"page": index + 1, "source": "ocr", "text": text, "lines": lines})
            page.close()
        return pages
    finally:
        pdf.close()


def read_document(data, force_ocr=False):
    kind = detect_kind(data)
    pages = read_pdf(data, force_ocr) if kind == "pdf" else read_image(data)
    return {"kind": kind, "pages": pages}
