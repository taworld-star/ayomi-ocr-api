# Ayomi OCR Dokumen

Layanan pembaca dokumen legal daycare untuk fitur **Safety Score & Legal Verification** Ayomi. Aplikasi web Ayomi mengirim dokumen yang sudah diunggah Pengelola (PDF, JPG, atau PNG), lalu layanan ini mengembalikan teks setiap halaman.

Layanan ini **hanya membaca**. Tiga hal lain tetap di aplikasi web:
- mengambil isian (nomor, penerbit, tanggal, alamat) dari teks ini dengan model bahasa;
- mencocokkan kutipan dengan teks OCR;
- keputusan Admin dan perhitungan skor.

Polanya sama dengan layanan Foto Fokus Anak (`ayomi-cv-api`): model berjalan di server Dokploy, sedangkan data dan izin akses tetap di aplikasi.

```text
Pengelola unggah dokumen ──▶ Aplikasi Ayomi (Vercel + Supabase)
                                  │  POST /ocr  (Bearer token)
                                  ▼
                            Ayomi OCR (Dokploy)  ──▶ teks per halaman
                                  │
Aplikasi: model bahasa mengambil isian + cek kutipan ──▶ usulan untuk Admin
Admin memverifikasi dokumen ──▶ Admin menilai Safety Score ──▶ skor publik
```

## Repository terkait

| Repository | Isi |
| --- | --- |
| [Project-Ayomi_Cut_Meutia](https://github.com/taworld-star/Project-Ayomi_Cut_Meutia) | Aplikasi web Ayomi (Next.js + Supabase): halaman, REST API, database, dan dokumentasi. Memanggil layanan ini dari server |
| [ayomi-cv-api](https://github.com/taworld-star/ayomi-cv-api) | Layanan **Foto Fokus Anak** (YOLO11n-seg) |
| [ayomi-ocr-api](https://github.com/taworld-star/ayomi-ocr-api) (repo ini) | Layanan **OCR dokumen legal** (RapidOCR PP-OCRv5) |
| [ayomi-triage-api](https://github.com/taworld-star/ayomi-triage-api) | Layanan **triage urgensi insiden** (mesin aturan rubrik; IndoBERT eksperimen) |

- Website: https://project-ayomi-cut-meutia.vercel.app
- Dokumentasi API aplikasi (Swagger UI): `docs/05-api/swagger.html` di repository aplikasi
- Dokumentasi semua fitur AI: `docs/06-fitur-ai/` di repository aplikasi

## Ringkasan fitur AI

| Poin | Isi |
| --- | --- |
| **Fitur** | **Safety Score & Legal Verification**: Admin menekan **Baca dengan AI** pada dokumen legal daycare |
| **Use case** | Computer Vision (OCR), dilanjutkan model bahasa di aplikasi web untuk mengambil isian |
| **Mengapa AI dibutuhkan** | Orang tua tidak punya tolok ukur legalitas daycare yang terstandarisasi (PRD 2.1). Admin harus memeriksa banyak dokumen (izin operasional, registrasi usaha, SOP, sertifikat staf, pemeriksaan fasilitas). OCR mempercepat pemeriksaan dan menandai ketidakcocokan; keputusan tetap di tangan Admin |
| **Model** | RapidOCR dengan model pra-latih **PaddleOCR PP-OCRv5** (detektor mobile + pengenal huruf **Latin**), Apache-2.0, di ONNX Runtime CPU. Isian diambil oleh model bahasa terbuka `qwen/qwen3.8-27b` (lewat Groq) di aplikasi web |
| **Alasan memilih** | Open source dan ringan (±13 MB) sehingga berjalan di CPU tanpa GPU; pengenal Latin menjaga huruf dan spasi bahasa Indonesia; PDF berlapis teks dibaca langsung tanpa OCR |
| **Data** | Dokumen legal yang diunggah Pengelola (PDF/JPG/PNG). Untuk pengujian: 16 dokumen spesimen **fiktif** buatan tim (3 daycare × 5 jenis, ditambah 1 hasil scan) dengan kunci jawaban; tidak memakai dokumen daycare asli |
| **Input → output** | Berkas dokumen → teks per halaman dengan sumber (`text_layer` atau `ocr`), lalu di aplikasi: isian usulan dengan kutipan per halaman, isian yang hilang, dan peringatan |
| **Evaluasi** | **80/81 isian (99%)** terbaca tepat di server production; pada alur penuh, **tidak ada nilai salah yang lolos** karena isian tanpa kutipan di teks OCR dikosongkan (bagian [Mengukur akurasi](#mengukur-akurasi)) |
| **Batasan dan risiko** | Scan buram atau miring menurunkan kualitas. Dokumen spesimen bersih, jadi angkanya bukan akurasi pada dokumen asli. OCR tidak bisa memastikan keaslian dokumen; karena itu Admin yang memutuskan setuju, minta revisi, atau tolak |

Dokumentasi lengkap semua fitur AI Ayomi ada di `docs/06-fitur-ai/` pada repository aplikasi.

## Model

- **Mesin:** [RapidOCR](https://github.com/RapidAI/RapidOCR) 3.10, berjalan dengan model pra-latih **PaddleOCR PP-OCRv5** (Apache-2.0) di ONNX Runtime, hanya memakai CPU.
  - Detektor teks: PP-OCRv5 mobile.
  - Pengenal huruf: PP-OCRv5 mobile **Latin**, yang menjaga spasi dan huruf bahasa Indonesia.
  - Ukuran model sekitar 13 MB. Model diunduh sekali saat image Docker dibuat, sehingga container bisa berjalan tanpa internet.
- **PDF berlapis teks** (dibuat dari komputer): teksnya dibaca langsung tanpa OCR. Selesai dalam sekitar 0,1 detik dan hasilnya persis.
- **Scan, foto, dan halaman PDF tanpa teks:** di-render pada 150 DPI, lalu dibaca dengan OCR. Satu halaman A4 butuh sekitar 15 detik pada CPU 2 inti.
- **Privasi:** berkas hanya ada di memori selama satu permintaan. Tidak ada yang disimpan atau dicatat di log.

## API

Semua permintaan kecuali `/health` wajib membawa header `Authorization: Bearer <API_TOKEN>`.

### `GET /health`

```json
{ "status": "ok", "version": "1.0.0", "engine": { "name": "rapidocr", "detector": "PP-OCRv5 mobile", "recognizer": "PP-OCRv5 mobile (latin)", "runtime": "onnxruntime-cpu" } }
```

### `POST /ocr` (multipart/form-data)

| Kolom | Isi |
| --- | --- |
| `file` | PDF, JPG, atau PNG, maksimal 15 MB dan 20 halaman |
| `force_ocr` | `true` untuk tetap memakai OCR walaupun PDF punya lapisan teks (untuk evaluasi). Bawaan `false` |

Contoh jawaban:

```json
{
  "kind": "jpeg",
  "page_count": 1,
  "pages": [{
    "page": 1,
    "source": "ocr",
    "text": "IZIN OPERASIONAL\nNomor: SPES/IO/KS/2022/0031\n…",
    "lines": [{ "text": "Nomor: SPES/IO/KS/2022/0031", "confidence": 0.98, "box": [[480,345],[775,341],[775,368],[480,372]] }]
  }],
  "engine": { "…": "…" },
  "version": "1.0.0",
  "duration_ms": 15230
}
```

`source` bernilai `text_layer` (dibaca dari PDF) atau `ocr`. `lines` hanya terisi untuk halaman yang dibaca dengan OCR, dan `box` adalah koordinat piksel pada gambar yang dibaca.

Jika gagal, layanan mengembalikan `{"detail": {"code": "…", "error": "pesan bahasa Indonesia"}}`:

| Status | Kode |
| --- | --- |
| 400 | `empty_file`, `invalid_pdf`, `invalid_image` |
| 401 | `unauthorized` |
| 413 | `file_too_large`, `too_many_pages` |
| 415 | `unsupported_format` |
| 503 | `busy` (antrean OCR penuh lebih dari 2 menit) |

## Variabel lingkungan

| Nama | Wajib | Isi |
| --- | --- | --- |
| `API_TOKEN` | Ya | String acak minimal 32 karakter. Nilai yang sama dipasang di Vercel sebagai `OCR_API_TOKEN`. Jangan memakai ulang token YOLO |
| `OCR_CONCURRENCY` | Tidak | Jumlah dokumen yang dibaca bersamaan. Bawaan `1` |

Membuat token, misalnya: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.

## Menjalankan di laptop

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
set API_TOKEN=token-lokal-minimal-32-karakter-xxxxxxxx   # PowerShell: $env:API_TOKEN="..."
.venv/Scripts/python -m uvicorn app:app --port 7860
```

Tes (sekitar 1 menit, karena satu tes membaca scan dengan OCR):

```bash
.venv/Scripts/python -m pytest -q
```

## Mengukur akurasi

`tools/evaluate.py` membaca semua dokumen spesimen fiktif (`../ayomi-project-cut-meutia/docs/06-fitur-ai/spesimen-dokumen`). Untuk setiap dokumen, skrip mengecek apakah nomor, nama lembaga, penerbit, tanggal, dan alamat dari `kunci-jawaban.json` muncul di teks hasil OCR.

```bash
.venv/Scripts/python tools/evaluate.py                       # paksa OCR (uji terberat)
.venv/Scripts/python tools/evaluate.py --text-layer          # PDF dibaca dari lapisan teks
set OCR_API_TOKEN=...  &&  .venv/Scripts/python tools/evaluate.py --url https://ocr.domain-anda
```

Skrip ini mengukur kemampuan **membaca**, bukan pengambilan isian. Dokumen spesimen bersih dan fiktif, jadi angkanya bukan akurasi pada dokumen asli daycare.

Hasil 19 November 2026 (OCR dipaksa untuk semua halaman, laptop 2 inti):

| Isian | Terbaca |
| --- | --- |
| Nama lembaga | 16/16 |
| Penerbit | 16/16 |
| Tanggal terbit | 13/13 |
| Berlaku sampai | 10/10 |
| Nomor dokumen | 10/10 |
| Alamat | 13/16 |
| **Total** | **78/81 (96%)** |

Di server Dokploy (dari `--url`, 19 November 2026), hasilnya **80/81 (99%)** dalam 98 detik untuk 25 halaman, sekitar 4 detik per halaman. Uji ulang 21 November 2026 memberi hasil yang sama, **80/81**, dengan waktu 3,4–14,1 detik per dokumen (89 detik untuk 16 berkas). Hanya satu alamat yang terlewat. Selisih kecil antara hasil laptop dan server wajar, karena hitungan model di CPU yang berbeda bisa sedikit berbeda.

Di laptop, ketiga alamat yang terlewat punya kesalahan yang sama: singkatan "Jl." terbaca "J.", sedangkan sisa alamatnya benar. Total waktunya 417 detik untuk 16 berkas (25 halaman), rata-rata sekitar 17 detik per halaman.

Pembuat dokumen spesimen ada di `tools/specimen/generate.py`, dan hasilnya ditulis ke folder dokumen spesimen di project web.

## Deploy di Dokploy

Langkahnya sama dengan `ayomi-cv-api`, tetapi sebagai **aplikasi terpisah**:

1. Unggah folder ini ke repo GitHub privat baru, misalnya `ayomi-ocr-api`.
2. Di Dokploy, buat **Application** baru di project yang sama dengan layanan YOLO:
   - **Provider:** GitHub (GitHub App yang sudah ada), pilih repo `ayomi-ocr-api` dan branch `main`.
   - **Build type:** Dockerfile.
3. Di tab **Environment**, isi `API_TOKEN=<token baru>`.
4. Di tab **Domains**, tambahkan domain, misalnya `ayomi-ocr.neoartd.my.id`, dengan **container port 7860** dan HTTPS aktif. Buat juga record DNS A untuk subdomain itu ke IP server, sama seperti domain YOLO.
5. Klik **Deploy**. Build pertama memakan beberapa menit karena mengunduh paket dan model.
6. Cek `https://ayomi-ocr.neoartd.my.id/health`, yang harus berisi `"status": "ok"`. Halaman `/` memang menampilkan `{"detail":"Not Found"}`, sama seperti layanan YOLO.
7. Di Vercel (project Ayomi), tambahkan `OCR_API_URL=https://ayomi-ocr.neoartd.my.id` dan `OCR_API_TOKEN=<token yang sama>`. Jangan pakai awalan `NEXT_PUBLIC_`.

Kebutuhan server: model dimuat sekitar 65 MB, dan puncak memori sekitar 520 MB saat membaca PDF 5 halaman (diukur 19 November 2026). Sediakan minimal 1 GB RAM untuk container ini. Kalau server yang sama juga menjalankan YOLO, biarkan `OCR_CONCURRENCY=1`.
