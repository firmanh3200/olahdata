"""
======================================================
 APLIKASI KONVERSI FILE UNIVERSAL (Streamlit)
======================================================
1. Unggah file dengan ekstensi bebas
2. Pilih format tujuan
3. Unduh hasil konversi

Jalankan:  streamlit run app.py
"""

import io
import os
import csv
import datetime
import tempfile

import streamlit as st
import pandas as pd

# ----------------- KONFIGURASI & DAFTAR FORMAT -----------------
st.set_page_config(page_title="Konverter File Universal", page_icon="🔄")

FORMAT_TABEL = {"csv", "tsv", "xlsx", "xlsm", "xls", "dbf", "json", "parquet", "pdf"}
FORMAT_TEKS  = {"txt", "py", "md", "log", "sql", "xml", "html", "css", "js",
                "yaml", "yml", "ini", "java", "c", "cpp", "h", "sh", "bat", "r"}
TABEL_OUT    = {"csv", "tsv", "xlsx", "xlsm", "xls", "dbf", "json",
                "parquet", "html", "md", "txt"}

FORMAT_TUJUAN = [
    ("CSV  (.csv)",          "csv"),
    ("Excel 2007+ (.xlsx)",  "xlsx"),
    ("Excel 97-2003 (.xls)", "xls"),
    ("dBase III (.dbf)",     "dbf"),
    ("PDF (.pdf)",           "pdf"),
    ("JSON (.json)",         "json"),
    ("Teks (.txt)",          "txt"),
    ("HTML (.html)",         "html"),
    ("Markdown (.md)",       "md"),
    ("Parquet (.parquet)",   "parquet"),
]

MIME = {
    "csv": "text/csv",
    "tsv": "text/tab-separated-values",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "dbf": "application/x-dbase",
    "pdf": "application/pdf",
    "json": "application/json",
    "txt": "text/plain",
    "html": "text/html",
    "md": "text/markdown",
    "parquet": "application/octet-stream",
}

# ----------------- FUNGSI UTILITAS -----------------
def decode_bytes(data: bytes) -> str:
    """Decode bytes dengan beberapa percobaan encoding."""
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def deteksi_pemisah(teks: str) -> str:
    """Deteksi otomatis pemisah (koma, titik-koma, tab, pipe)."""
    try:
        dialek = csv.Sniffer().sniff(teks[:8192], delimiters=",;\t|")
        return dialek.delimiter
    except csv.Error:
        return ","

# ----------------- MEMBACA FILE -> DATAFRAME -----------------
@st.cache_data(show_spinner=False)
def baca_jadi_dataframe(data: bytes, ext: str) -> pd.DataFrame:
    ext = ext.lower()

    if ext in ("csv", "tsv"):
        teks = decode_bytes(data)
        pemisah = "\t" if ext == "tsv" else deteksi_pemisah(teks)
        return pd.read_csv(io.StringIO(teks), sep=pemisah,
                           engine="python", on_bad_lines="skip")

    if ext in ("xlsx", "xlsm"):
        return pd.read_excel(io.BytesIO(data), engine="openpyxl")   # sheet pertama

    if ext == "xls":
        return pd.read_excel(io.BytesIO(data), engine="xlrd")       # sheet pertama

    if ext == "dbf":
        from dbfread import DBF
        with tempfile.NamedTemporaryFile(suffix=".dbf", delete=False) as tmp:
            tmp.write(data)
            path = tmp.name
        try:
            return pd.DataFrame(iter(DBF(path, encoding="cp1252")))
        finally:
            os.unlink(path)

    if ext == "json":
        try:
            return pd.read_json(io.StringIO(decode_bytes(data)))
        except Exception as e:
            raise ValueError(f"JSON tidak dapat dibaca sebagai tabel: {e}")

    if ext == "parquet":
        return pd.read_parquet(io.BytesIO(data))

    if ext == "pdf":
        import pdfplumber
        frame_list = []
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for halaman in pdf.pages:
                for tabel in (halaman.extract_tables() or []):
                    if not tabel:
                        continue
            # --- perbaiki indentasi blok ini ---
                    header, *baris = tabel
                    frame_list.append(pd.DataFrame(baris, columns=[str(h) for h in header]))
        if frame_list:
            return pd.concat(frame_list, ignore_index=True)
        raise ValueError("Tidak ada tabel di PDF. Coba konversi ke TXT untuk mengambil teksnya.")

    if ext in FORMAT_TEKS:  # txt, py, md, dll.
        teks = decode_bytes(data)
        try:
            df = pd.read_csv(io.StringIO(teks), sep=None, engine="python",
                             on_bad_lines="skip")
            if df.shape[1] >= 2:
                return df
        except Exception:
            pass
        return pd.DataFrame({"isi_teks": teks.splitlines()})

    raise ValueError(f"Format .{ext} belum didukung untuk dibaca.")

# ----------------- MENULIS DATAFRAME -> FORMAT TUJUAN -----------------
def _nama_field_dbf(nama, terpakai):
    nama = "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in str(nama).upper())
    if not nama or nama[0].isdigit():
        nama = "F" + nama
    nama, kandidat, i = nama[:10], nama[:10], 1
    while kandidat in terpakai:
        kandidat = f"{nama[:8]}_{i}"
        i += 1
    terpakai.add(kandidat)
    return kandidat


def df_ke_dbf(df: pd.DataFrame) -> bytes:
    """Penulis dBase III sederhana (tanpa dependensi tambahan)."""
    terpakai = set()
    fields = []
    for kol in df.columns:
        s = df[kol]
        nama = _nama_field_dbf(kol, terpakai)
        if pd.api.types.is_bool_dtype(s):
            fields.append((nama, "L", 1, 0, kol))
        elif pd.api.types.is_numeric_dtype(s):
            fields.append((nama, "N", 19, 4, kol))
        elif pd.api.types.is_datetime64_any_dtype(s):
            fields.append((nama, "D", 8, 0, kol))
        else:
            panjang = int(s.astype(str).str.len().max()) if len(s) else 1
            fields.append((nama, "C", max(1, min(panjang or 1, 250)), 0, kol))

    header_len  = 32 + 32 * len(fields) + 1
    record_len  = 1 + sum(f[2] for f in fields)
    hari_ini    = datetime.date.today()

    out = bytearray([0x03, hari_ini.year % 100, hari_ini.month, hari_ini.day])
    out += len(df).to_bytes(4, "little")
    out += header_len.to_bytes(2, "little")
    out += record_len.to_bytes(2, "little")
    out += b"\x00" * 20

    for nama, tipe, size, dec, _ in fields:
        d = bytearray(32)
        nb = nama.encode("ascii")[:11]
        d[0:len(nb)] = nb
        d[11], d[16], d[17] = ord(tipe), size, dec
        out += d
    out.append(0x0D)

    for _, baris in df.iterrows():
        out.append(0x20)  # penanda "belum terhapus"
        for nama, tipe, size, dec, kol in fields:
            nilai = baris[kol]
            if pd.isna(nilai):
                out += b"?" if tipe == "L" else b" " * size
            elif tipe == "L":
                out += b"T" if bool(nilai) else b"F"
            elif tipe == "D":
                out += pd.Timestamp(nilai).strftime("%Y%m%d").encode("ascii")
            elif tipe == "N":
                teks = f"{float(nilai):.{dec}f}"[:size]
                out += teks.rjust(size).encode("ascii", "replace")
            else:  # C
                out += str(nilai).encode("cp1252", "replace")[:size].ljust(size, b" ")
    out.append(0x1A)
    return bytes(out)


def df_ke_pdf(df: pd.DataFrame) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet

    MAKS_BARIS, MAKS_KARAKTER = 1000, 60
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            leftMargin=10*mm, rightMargin=10*mm,
                            topMargin=10*mm, bottomMargin=10*mm)
    gaya = getSampleStyleSheet()
    cerita = [Paragraph("Hasil Konversi", gaya["Title"]), Spacer(1, 6*mm)]

    data = [[str(k)[:MAKS_KARAKTER] for k in df.columns]]
    for _, baris in df.head(MAKS_BARIS).iterrows():
        data.append([str(v)[:MAKS_KARAKTER] for v in baris.tolist()])

    tabel = Table(data, repeatRows=1)
    tabel.setStyle(TableStyle([
        ("BACKGROUND",      (0, 0), (-1, 0), colors.HexColor("#0F4C81")),
        ("TEXTCOLOR",       (0, 0), (-1, 0), colors.white),
        ("FONTNAME",        (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",        (0, 0), (-1, -1), 7),
        ("GRID",            (0, 0), (-1, -1), 0.4, colors.grey),
        ("ROWBACKGROUNDS",  (0, 1), (-1, -1), [colors.white, colors.HexColor("#EFF3F8")]),
        ("VALIGN",          (0, 0), (-1, -1), "TOP"),
    ]))
    cerita.append(tabel)
    if len(df) > MAKS_BARIS:
        cerita.append(Spacer(1, 4*mm))
        cerita.append(Paragraph(
            f"Catatan: hanya {MAKS_BARIS} baris pertama dari total {len(df)} baris.",
            gaya["Italic"]))
    doc.build(cerita)
    return buf.getvalue()


def teks_ke_pdf(teks: str) -> bytes:
    from xml.sax.saxutils import escape
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15*mm, rightMargin=15*mm,
                            topMargin=15*mm, bottomMargin=15*mm)
    gaya = getSampleStyleSheet()
    isi = escape(teks[:100_000]).replace("\n", "<br/>")
    doc.build([Paragraph("Hasil Konversi", gaya["Title"]),
               Spacer(1, 5*mm),
               Paragraph(isi, gaya["Code"])])
    return buf.getvalue()


def df_ke_bytes(df: pd.DataFrame, ext: str) -> bytes:
    buf = io.BytesIO()
    if ext == "csv":
        return df.to_csv(index=False).encode("utf-8")
    if ext == "tsv":
        return df.to_csv(index=False, sep="\t").encode("utf-8")
    if ext in ("xlsx", "xlsm"):
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            df.to_excel(w, index=False, sheet_name="Data")
        return buf.getvalue()
    if ext == "xls":
        try:
            with pd.ExcelWriter(buf, engine="xlwt") as w:
                df.to_excel(w, index=False, sheet_name="Data")
            return buf.getvalue()
        except Exception:
            raise ValueError("Menulis .xls butuh paket xlwt. Saran: gunakan XLSX.")
    if ext == "json":
        return df.to_json(orient="records", indent=2, force_ascii=False).encode("utf-8")
    if ext == "html":
        html = df.to_html(index=False)
        return (f'<!DOCTYPE html><html><head><meta charset="utf-8">'
                f'<title>Data</title></head><body>{html}</body></html>').encode("utf-8")
    if ext == "md":
        try:
            return df.to_markdown(index=False).encode("utf-8")
        except Exception:
            return ("```\n" + df.to_string(index=False) + "\n```").encode("utf-8")
    if ext == "txt":
        return df.to_csv(index=False, sep="\t").encode("utf-8")
    if ext == "parquet":
        try:
            df.to_parquet(buf, index=False)
            return buf.getvalue()
        except Exception:
            raise ValueError("Menulis .parquet butuh paket pyarrow.")
    if ext == "dbf":
        return df_ke_dbf(df)
    if ext == "pdf":
        return df_ke_pdf(df)
    raise ValueError(f"Format keluaran .{ext} belum didukung.")

# ----------------- FUNGSI KONVERSI UTAMA -----------------
def konversi(data: bytes, src: str, dst: str):
    """Mengembalikan (bytes_hasil, daftar_catatan)."""
    catatan = []
    src, dst = src.lower(), dst.lower()

    if src == dst:
        return data, ["Format sumber = format tujuan, file disalin apa adanya."]

    # 1) Baca sumber
    df, teks = None, None
    if src in FORMAT_TABEL:
        df = baca_jadi_dataframe(data, src)
    else:
        teks = decode_bytes(data)

    # 2) Tujuan PDF
    if dst == "pdf":
        return (df_ke_pdf(df) if df is not None else teks_ke_pdf(teks)), catatan

    # 3) Teks -> txt: salin apa adanya
    if dst == "txt" and df is None:
        return teks.encode("utf-8"), ["Teks disalin apa adanya ke file .txt."]

    # 4) Tujuan format tabel
    if dst in TABEL_OUT:
        if df is None:  # sumber teks
            try:
                df = pd.read_csv(io.StringIO(teks), sep=None, engine="python",
                                 on_bad_lines="skip")
                catatan.append("File teks diparsing sebagai tabel (pemisah terdeteksi otomatis).")
            except Exception:
                df = pd.DataFrame({"isi_teks": teks.splitlines()})
                catatan.append("Isi teks tidak berbentuk tabel, disimpan sebagai satu kolom 'isi_teks'.")
        return df_ke_bytes(df, dst), catatan

    # 5) Tujuan teks bebas lainnya (py, js, css, dll.)
    if teks is not None:
        return teks.encode("utf-8"), [f"Isi file teks disalin apa adanya (ke .{dst})."]

    raise ValueError(f"Konversi .{src} → .{dst} belum didukung.")

# ================== ANTARMUKA (UI) ==================
st.title("🔄 Konverter File Universal")
st.markdown("Unggah file apa pun → pilih format tujuan → unduh hasilnya.")

with st.sidebar:
    st.header("ℹ️ Informasi")
    st.markdown(
        "**Input yang bisa diparsing:**\n"
        "- Tabel: csv, tsv, xlsx, xlsm, xls, dbf, json, parquet\n"
        "- Dokumen: pdf (ekstraksi tabel/teks)\n"
        "- Teks: txt, py, md, sql, xml, dll.\n\n"
        "**Keluaran:** csv, xlsx, xls, dbf, pdf, json, txt, html, md, parquet"
    )
    st.subheader("📦 Instal dependensi")
    st.code("pip install streamlit pandas openpyxl xlrd xlwt "
            "dbfread pdfplumber reportlab pyarrow tabulate", language="bash")

# ---- Langkah 1: Unggah ----
uploaded = st.file_uploader("1️⃣ Unggah file Anda (ekstensi bebas)", type=None)

if uploaded is None:
    st.info("⬆️ Belum ada file. Silakan unggah file terlebih dahulu.")
    st.stop()

data = uploaded.getvalue()
base, ekst = os.path.splitext(uploaded.name)
ekst = ekst.lower().lstrip(".")
file_key = f"{uploaded.name}|{uploaded.size}"

if st.session_state.get("_file_key") != file_key:   # reset hasil bila file berganti
    st.session_state["_file_key"] = file_key
    st.session_state["hasil"] = None

st.success(f"✅ **{uploaded.name}** terunggah ({len(data)/1024:.1f} KB)")

# ---- Pratinjau ----
with st.expander("👀 Pratinjau isi file"):
    if b"\x00" in data[:1024]:
        st.caption("File biner — pratinjau teks tidak ditampilkan.")
    else:
        try:
            df_prev = baca_jadi_dataframe(data, ekst)
            st.caption(f"Tabel: {df_prev.shape[0]:,} baris × {df_prev.shape[1]} kolom "
                       f"(menampilkan maks. 10 baris)")
            st.dataframe(df_prev.head(10), use_container_width=True)
        except Exception:
            st.caption("Pratinjau teks (maks. 2.000 karakter):")
            st.text(decode_bytes(data[:5000])[:2000])

# ---- Langkah 2: Pilih format tujuan ----
label2ext = dict(FORMAT_TUJUAN)
label = st.selectbox("2️⃣ Pilih format file tujuan", list(label2ext.keys()))
dst = label2ext[label]

if st.session_state.get("_dst") != dst:             # reset hasil bila format berganti
    st.session_state["_dst"] = dst
    st.session_state["hasil"] = None

# ---- Proses konversi ----
if st.button("🚀 Konversi Sekarang", type="primary"):
    with st.spinner("⏳ Sedang mengonversi..."):
        try:
            hasil_bytes, catatan = konversi(data, ekst, dst)
            st.session_state["hasil"] = {
                "data": hasil_bytes,
                "mime": MIME.get(dst, "application/octet-stream"),
                "nama": f"{base}.{dst}",
                "catatan": catatan,
            }
        except Exception as e:
            st.session_state["hasil"] = {"error": str(e)}

# ---- Langkah 3: Unduh ----
hasil = st.session_state.get("hasil")
if hasil:
    if "error" in hasil:
        st.error(f"❌ Konversi gagal: {hasil['error']}")
    else:
        st.balloons()
        st.success("✅ Konversi berhasil! Silakan unduh file Anda.")
        for c in hasil["catatan"]:
            st.caption("ℹ️ " + c)
        st.download_button(
            "3️⃣ Unduh file hasil",
            data=hasil["data"],
            file_name=hasil["nama"],
            mime=hasil["mime"],
        )