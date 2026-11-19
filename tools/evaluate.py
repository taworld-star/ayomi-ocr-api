import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_DIR = ROOT.parent / "ayomi-project-cut-meutia" / "docs" / "spesimen-dokumen"
FIELDS = ["document_number", "institution_name", "issuer", "issued_on", "expires_on", "address"]
MONTHS = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus",
          "September", "Oktober", "November", "Desember"]


def long_date(iso):
    year, month, day = iso.split("-")
    return f"{int(day)} {MONTHS[int(month) - 1]} {year}"


def exact(text):
    text = re.sub(r"\bji\.", "jl.", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def loose(text):
    return re.sub(r"[^0-9a-z]", "", exact(text))


def expected_value(field, value):
    return long_date(value) if field in {"issued_on", "expires_on"} else value


def read_local(path, force_ocr):
    from ocr_engine import read_document
    return read_document(path.read_bytes(), force_ocr=force_ocr)


def read_remote(path, force_ocr, url, token):
    import httpx
    response = httpx.post(f"{url.rstrip('/')}/ocr", headers={"Authorization": f"Bearer {token}"},
                          files={"file": (path.name, path.read_bytes())},
                          data={"force_ocr": str(force_ocr).lower()}, timeout=600)
    response.raise_for_status()
    return response.json()


def main():
    parser = argparse.ArgumentParser(description="Ukur akurasi OCR pada dokumen spesimen.")
    parser.add_argument("--specimen-dir", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--text-layer", action="store_true", help="pakai lapisan teks PDF bila ada (tanpa OCR)")
    parser.add_argument("--url", help="uji layanan yang sudah di-deploy (token dari OCR_API_TOKEN)")
    parser.add_argument("--json", type=Path, help="simpan hasil lengkap ke berkas JSON")
    args = parser.parse_args()

    key = json.loads((args.specimen_dir / "kunci-jawaban.json").read_text(encoding="utf-8"))
    force_ocr = not args.text_layer
    token = os.environ.get("OCR_API_TOKEN", "")
    if args.url and not token:
        sys.exit("Isi OCR_API_TOKEN untuk menguji layanan yang di-deploy.")

    rows, totals = [], {"exact": 0, "loose": 0, "fields": 0, "seconds": 0.0}
    per_field = {field: {"exact": 0, "loose": 0, "total": 0} for field in FIELDS}
    for daycare in key["daycares"]:
        for document in daycare["documents"]:
            path = args.specimen_dir / document["file"]
            started = time.perf_counter()
            result = read_remote(path, force_ocr, args.url, token) if args.url else read_local(path, force_ocr)
            seconds = time.perf_counter() - started
            text = "\n".join(page["text"] for page in result["pages"])
            checks = {}
            for field in FIELDS:
                if document.get(field) is None:
                    continue
                want = expected_value(field, document[field])
                checks[field] = {"expected": want, "exact": exact(want) in exact(text), "loose": loose(want) in loose(text)}
                per_field[field]["total"] += 1
                per_field[field]["exact"] += checks[field]["exact"]
                per_field[field]["loose"] += checks[field]["loose"]
            hit_exact = sum(check["exact"] for check in checks.values())
            hit_loose = sum(check["loose"] for check in checks.values())
            totals["exact"] += hit_exact
            totals["loose"] += hit_loose
            totals["fields"] += len(checks)
            totals["seconds"] += seconds
            sources = sorted({page["source"] for page in result["pages"]})
            rows.append({"file": document["file"], "pages": len(result["pages"]), "source": sources,
                         "seconds": round(seconds, 1), "checks": checks})
            missed = [f"{field}={check['expected']!r}" for field, check in checks.items() if not check["loose"]]
            print(f"{document['file']:<52} {hit_exact}/{len(checks)} tepat, {hit_loose}/{len(checks)} longgar, "
                  f"{len(result['pages'])} hal, {seconds:5.1f}s {'/'.join(sources)}"
                  + (f"\n    terlewat: {', '.join(missed)}" if missed else ""))

    print("\nPer kolom:")
    for field, count in per_field.items():
        if count["total"]:
            print(f"  {field:<17} tepat {count['exact']}/{count['total']}, longgar {count['loose']}/{count['total']}")
    fields = totals["fields"] or 1
    print(f"\nTotal: tepat {totals['exact']}/{totals['fields']} ({totals['exact'] / fields:.0%}), "
          f"longgar {totals['loose']}/{totals['fields']} ({totals['loose'] / fields:.0%}), "
          f"waktu {totals['seconds']:.0f}s untuk {len(rows)} berkas")
    if args.json:
        args.json.write_text(json.dumps({"mode": "ocr" if force_ocr else "text_layer", "totals": totals,
                                         "per_field": per_field, "documents": rows}, ensure_ascii=False, indent=2),
                             encoding="utf-8")


if __name__ == "__main__":
    main()
