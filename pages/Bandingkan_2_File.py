import os
import re
import sqlite3
import tempfile
from io import BytesIO

import pandas as pd
import streamlit as st

# ================== KONFIGURASI ==================
st.set_page_config(
    page_title="Perbandingan File Data",
    page_icon="📊",
    layout="wide",
)

EKSTENSI = [
    "xlsx", "xls", "xlsm", "csv", "tsv", "txt", "dbf",
    "sav", "zsav", "sql", "mdb", "accdb", "parquet",
    "dta", "sas7bdat", "xpt", "json",
]

ENCODING_OPSI = ["utf-8", "utf-8-sig", "latin1", "cp1252"]
SEP_MAP = {"auto": None, "koma ( , )": ",", "titik-koma ( ; )": ";",
           "tab ( \\t )": "\t", "pipa ( | )": "|"}
PEMISAH_KUNCI = "|"


# ================== FUNGSI UMUM ==================
def simpan_sementara(bytes_data: bytes, suffix: str) -> str:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(bytes_data)
    tmp.close()
    return tmp.name


def normalize_text(value) -> str:
    """Huruf kecil semua -> hapus spasi berlebih -> hanya huruf & angka."""
    if pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).lower()
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"[^a-z0-9]", "", text)
    return text


def buat_kunci(df: pd.DataFrame, kolom_list: list) -> tuple[pd.Series, pd.DataFrame]:
    """Bentuk kunci gabungan dari beberapa kolom (ternormalisasi)."""
    komponen = [df[k].apply(normalize_text) for k in kolom_list]
    kunci = komponen[0]
    for k in komponen[1:]:
        kunci = kunci + PEMISAH_KUNCI + k
    mask_lengkap = pd.concat([(c != "") for c in komponen], axis=1).all(axis=1)
    return kunci, mask_lengkap


def sort_df_aman(df: pd.DataFrame, kolom_list: list, naik: bool = True) -> pd.DataFrame:
    """
    Sorting multi-kolom yang aman terhadap tipe data campuran
    (angka + teks dalam satu kolom tidak menyebabkan error).
    Sorting dilakukan per kolom secara berurutan (kolom pertama = prioritas utama).
    """
    if not kolom_list:
        return df
    try:
        return df.sort_values(by=kolom_list, ascending=naik,
                              kind="stable", na_position="last")
    except TypeError:
        # fallback: jika ada tipe campuran yang tak bisa dibandingkan
        return df.sort_values(by=kolom_list, ascending=naik, kind="stable",
                              key=lambda s: s.astype(str), na_position="last")


def export_excel(sheets: dict) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name[:31], index=False)
    return buffer.getvalue()


def pilih_baris_judul(mentah: pd.DataFrame, prefix: str, label: str):
    mentah = mentah.copy()
    mentah.index = mentah.index + 1
    st.markdown("**Pratinjau 30 baris pertama** (perhatikan di baris ke-berapa judul kolom berada):")
    st.dataframe(mentah, use_container_width=True, height=250)
    return st.number_input(
        f"📌 {label}",
        min_value=1, max_value=max(30, len(mentah)), value=1,
        key=f"{prefix}_hdr",
        help="Contoh: jika judul kolom ada di baris ke-3 pratinjau, isi 3. "
             "Baris di atasnya akan diabaikan.",
    )


# ================== LOADER PER FORMAT ==================
def muat_excel(file, prefix):
    xls = pd.ExcelFile(file)
    sheets = xls.sheet_names
    if len(sheets) > 1:
        sheet = st.selectbox("Pilih sheet", sheets, key=f"{prefix}_sheet")
    else:
        sheet = sheets[0]
        st.caption(f"File memiliki 1 sheet: **{sheet}**")

    mentah = pd.read_excel(xls, sheet_name=sheet, header=None, nrows=30)
    baris = pilih_baris_judul(mentah, prefix, "Baris yang menjadi judul kolom (mulai dari 1)")
    df = pd.read_excel(xls, sheet_name=sheet, header=int(baris) - 1)

    if st.checkbox("Buang kolom tanpa nama (Unnamed)", value=False, key=f"{prefix}_unnamed"):
        df = df.loc[:, ~df.columns.astype(str).str.startswith("Unnamed")]

    st.info(f"Baris ke-{baris} dipakai sebagai judul kolom → "
            f"**{len(df)} baris**, **{len(df.columns)} kolom**")
    return df


def muat_csv(file, prefix):
    c1, c2 = st.columns(2)
    with c1:
        encoding = st.selectbox("Encoding", ENCODING_OPSI, key=f"{prefix}_enc",
                                help="Jika karakter tampil aneh, coba latin1 / cp1252")
    with c2:
        sep_label = st.selectbox("Pemisah kolom", list(SEP_MAP.keys()), key=f"{prefix}_sep")
    sep = SEP_MAP[sep_label]

    try:
        mentah = pd.read_csv(file, header=None, nrows=30,
                             encoding=encoding, sep=sep, engine="python")
    except Exception:
        file.seek(0)
        mentah = pd.read_csv(file, header=None, nrows=30, encoding=encoding)

    baris = pilih_baris_judul(mentah, prefix, "Baris yang menjadi judul kolom (mulai dari 1)")

    file.seek(0)
    return pd.read_csv(file, header=int(baris) - 1,
                       encoding=encoding, sep=sep, engine="python")


def muat_dbf(file):
    try:
        from dbfread import DBF
    except ImportError:
        st.error("Library `dbfread` belum terpasang → `pip install dbfread`")
        return None
    path = simpan_sementara(file.getvalue(), ".dbf")
    try:
        return pd.DataFrame(list(DBF(path, load=True)))
    finally:
        os.unlink(path)


def muat_spss(file):
    try:
        import pyreadstat
    except ImportError:
        st.error("Library `pyreadstat` belum terpasang → `pip install pyreadstat`")
        return None
    path = simpan_sementara(file.getvalue(), ".sav")
    try:
        df, _ = pyreadstat.read_sav(path)
        return df
    finally:
        os.unlink(path)


@st.cache_data(show_spinner="Membaca file SQL...")
def parse_sql(bytes_data: bytes) -> dict:
    teks = bytes_data.decode("utf-8", errors="replace")
    teks = re.sub(r"^\s*SET\s+[^;]+;", "", teks, flags=re.I | re.M)
    teks = re.sub(r"^\s*(LOCK|UNLOCK)\s+TABLES?[^;]*;", "", teks, flags=re.I | re.M)
    teks = re.sub(r"\)\s*ENGINE=[^;]*;", ");", teks, flags=re.I)
    teks = re.sub(r"\bAUTO_INCREMENT\s*=\s*\d+\s*", "", teks, flags=re.I)

    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    buffer = ""
    for line in teks.splitlines():
        buffer += line + "\n"
        if sqlite3.complete_statement(buffer):
            try:
                cur.execute(buffer)
            except sqlite3.Error:
                pass
            buffer = ""

    hasil = {}
    nama_tabel = [r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    for t in nama_tabel:
        try:
            df = pd.read_sql(f'SELECT * FROM "{t}"', conn)
            if len(df) > 0:
                hasil[t] = df
        except Exception:
            continue
    conn.close()
    return hasil


def muat_sql(file, prefix):
    tabel_df = parse_sql(file.getvalue())
    if not tabel_df:
        st.error("Tidak ada tabel berisi data yang bisa dibaca dari file SQL ini.")
        return None
    st.caption(f"Tabel terdeteksi: {', '.join(tabel_df.keys())}")
    pilih = st.selectbox("Pilih tabel", list(tabel_df.keys()), key=f"{prefix}_tabel")
    return tabel_df[pilih]


@st.cache_data(show_spinner="Membaca file Access...")
def parse_mdb(bytes_data: bytes):
    try:
        from access_parser import AccessParser
    except ImportError:
        return None
    path = simpan_sementara(bytes_data, ".accdb")
    try:
        db = AccessParser(path)
        hasil = {}
        for nama in db.catalog:
            try:
                parsed = db.parse_table(nama)
                cols, rows = parsed.get("columns", []), parsed.get("data", [])
                df = (pd.DataFrame(rows) if rows and isinstance(rows[0], dict)
                      else pd.DataFrame(rows, columns=cols))
                if len(df) > 0:
                    hasil[str(nama)] = df
            except Exception:
                continue
        return hasil
    finally:
        os.unlink(path)


def muat_mdb(file, prefix):
    hasil = parse_mdb(file.getvalue())
    if hasil is None:
        st.error("Library `access-parser` belum terpasang → `pip install access-parser`")
        return None
    if not hasil:
        st.error("Tidak ada tabel yang bisa dibaca dari file Access ini.")
        return None
    st.caption(f"Tabel terdeteksi: {', '.join(hasil.keys())}")
    pilih = st.selectbox("Pilih tabel", list(hasil.keys()), key=f"{prefix}_tabel")
    return hasil[pilih]


# ================== PANEL UPLOAD ==================
def render_panel(judul: str, prefix: str):
    st.subheader(f"📁 {judul}")
    file = st.file_uploader(f"Unggah {judul}", type=EKSTENSI, key=f"{prefix}_up",
                            help="Excel, CSV/TXT, DBF, SPSS (.sav), SQL dump, "
                                 "Access (.mdb/.accdb), Parquet, Stata, SAS, JSON")

    if file is None:
        st.info("Menunggu file…")
        return None

    ext = file.name.rsplit(".", 1)[-1].lower()
    st.caption(f"Format terdeteksi: **.{ext}**")

    try:
        if ext in ("xlsx", "xls", "xlsm"):
            df = muat_excel(file, prefix)
        elif ext in ("csv", "tsv", "txt"):
            df = muat_csv(file, prefix)
        elif ext == "dbf":
            df = muat_dbf(file)
        elif ext in ("sav", "zsav"):
            df = muat_spss(file)
        elif ext == "sql":
            df = muat_sql(file, prefix)
        elif ext in ("mdb", "accdb"):
            df = muat_mdb(file, prefix)
        elif ext == "parquet":
            df = pd.read_parquet(file)
        elif ext == "dta":
            df = pd.read_stata(file)
        elif ext == "sas7bdat":
            df = pd.read_sas(file, format="sas7bdat")
        elif ext == "xpt":
            df = pd.read_sas(file, format="xport")
        elif ext == "json":
            df = pd.read_json(file)
        else:
            st.error(f"Format .{ext} belum didukung.")
            return None
    except Exception as e:
        st.error(f"Gagal membaca file: {e}")
        return None

    if df is None:
        return None

    st.success(f"✅ Berhasil dimuat — **{len(df)} baris × {len(df.columns)} kolom**")
    st.markdown("**Nama-nama kolom:**")
    st.code("  |  ".join(map(str, df.columns)), language=None)
    return df


# ================== HALAMAN UTAMA ==================
st.title("📊 Aplikasi Perbandingan File Data")
st.markdown(
    "Bandingkan dua file data berdasarkan **satu atau beberapa kolom pembanding**, "
    "lalu hasil diurutkan (sorting) sesuai kolom pembanding agar mudah diverifikasi. "
    "Nilai otomatis dinormalisasi: huruf kecil semua → hapus spasi berlebih → "
    "hapus karakter selain huruf & angka."
)
with st.expander("ℹ️ Format yang didukung & library tambahan"):
    st.markdown(
        "| Format | Library |\n|---|---|\n"
        "| .xlsx / .xlsm | openpyxl |\n"
        "| .xls (lama) | xlrd |\n"
        "| .csv / .tsv / .txt | bawaan pandas |\n"
        "| .dbf | dbfread |\n"
        "| .sav / .zsav (SPSS) | pyreadstat |\n"
        "| .sql (dump) | bawaan (sqlite3) |\n"
        "| .mdb / .accdb (Access) | access-parser |\n"
        "| .parquet | pyarrow |\n"
        "| .dta (Stata) / .sas7bdat / .xpt | bawaan pandas |\n"
        "| .json | bawaan pandas |"
    )
st.divider()

if "hasil" not in st.session_state:
    st.session_state.hasil = None

col_a, col_b = st.columns(2)
with col_a:
    df1 = render_panel("File Data 1", "f1")
with col_b:
    df2 = render_panel("File Data 2", "f2")

# ================== PILIH KOLOM & BANDINGKAN ==================
if df1 is not None and df2 is not None:

    st.divider()
    st.subheader("⚙️ Pilih Kolom Pembanding (bisa lebih dari satu)")
    st.caption("💡 Pilih kolom **berurutan dan sepadan** — kolom ke-1 File 1 dipasangkan "
               "dengan kolom ke-1 File 2, dst. Contoh: `Nama, Tgl Lahir` ⇄ `Nama Lengkap, Tanggal Lahir`")

    c1, c2 = st.columns(2)
    with c1:
        kolom1_list = st.multiselect(
            "Kolom dari File 1", list(df1.columns), key="kol1",
            placeholder="Pilih satu atau lebih kolom…")
        if kolom1_list:
            k1, _ = buat_kunci(df1.head(3), kolom1_list)
            st.caption("Contoh kunci ternormalisasi: " + " , ".join(
                f"`{v or '(kosong)'}`" for v in k1))
    with c2:
        kolom2_list = st.multiselect(
            "Kolom dari File 2", list(df2.columns), key="kol2",
            placeholder="Pilih satu atau lebih kolom…")
        if kolom2_list:
            k2, _ = buat_kunci(df2.head(3), kolom2_list)
            st.caption("Contoh kunci ternormalisasi: " + " , ".join(
                f"`{v or '(kosong)'}`" for v in k2))

    # ---------- validasi pasangan kolom ----------
    valid = False
    if not kolom1_list and not kolom2_list:
        st.warning("Pilih minimal satu kolom dari masing-masing file.")
    elif len(kolom1_list) != len(kolom2_list):
        st.error(f"Jumlah kolom tidak sepadan: File 1 = {len(kolom1_list)} kolom, "
                 f"File 2 = {len(kolom2_list)} kolom. Samakan jumlahnya.")
    else:
        valid = True
        pasangan = pd.DataFrame({
            "No": range(1, len(kolom1_list) + 1),
            "File 1": kolom1_list,
            "⇄": ["sepadan dengan"] * len(kolom1_list),
            "File 2": kolom2_list,
        }).set_index("No")
        st.markdown("**Pasangan kolom pembanding:**")
        st.table(pasangan)

    # ================== PENGATURAN SORTING ==================
    st.subheader("🔀 Pengaturan Sorting Hasil")
    sort_aktif = st.checkbox(
        "Urutkan hasil berdasarkan kolom pembanding",
        value=True,
        help="Hasil SAMA dan BERBEDA akan diurutkan berdasarkan kolom pembanding "
             "yang dipilih (kolom pertama = prioritas utama pengurutan).")

    naik = True
    sort_kolom_idx = list(range(len(kolom1_list)))  # default: semua kolom pembanding

    if sort_aktif and valid:
        s1, s2 = st.columns(2)
        with s1:
            arah = st.radio("Arah pengurutan",
                            ["Naik (A→Z, 0→9)", "Turun (Z→A, 9→0)"],
                            horizontal=True, key="arah_sort")
            naik = arah.startswith("Naik")
        with s2:
            label_pilihan = [f"{i+1}. {a} ⇄ {b}"
                             for i, (a, b) in enumerate(zip(kolom1_list, kolom2_list))]
            sort_kolom_idx = st.multiselect(
                "Kolom yang dipakai untuk sorting (urutan = prioritas)",
                options=list(range(len(label_pilihan))),
                default=list(range(len(label_pilihan))),
                format_func=lambda i: label_pilihan[i],
                key="kolom_sort")

    hanya_lengkap = st.checkbox(
        "Hanya cocokkan baris dengan SEMUA kolom kunci terisi",
        value=True,
        help="Jika aktif, baris yang memiliki sel kosong pada salah satu kolom kunci "
             "tidak akan diikutkan dalam perbandingan (lebih akurat).")

    if st.button("🔍 Bandingkan", type="primary", use_container_width=True, disabled=not valid):
        with st.spinner("Memproses perbandingan & sorting..."):
            d1, d2 = df1.copy(), df2.copy()

            kunci_s1, lengkap1 = buat_kunci(d1, kolom1_list)
            kunci_s2, lengkap2 = buat_kunci(d2, kolom2_list)
            d1["_kunci"], d2["_kunci"] = kunci_s1, kunci_s2

            if hanya_lengkap:
                layak1 = lengkap1 & (d1["_kunci"] != "")
                layak2 = lengkap2 & (d2["_kunci"] != "")
            else:
                layak1 = d1["_kunci"] != ""
                layak2 = d2["_kunci"] != ""

            kunci1 = set(d1.loc[layak1, "_kunci"])
            kunci2 = set(d2.loc[layak2, "_kunci"])
            m1, m2 = d1["_kunci"].isin(kunci2), d2["_kunci"].isin(kunci1)

            # ---- kolom sorting untuk masing-masing file (pasangan sepadan) ----
            sort1 = [kolom1_list[i] for i in sort_kolom_idx if i < len(kolom1_list)]
            sort2 = [kolom2_list[i] for i in sort_kolom_idx if i < len(kolom2_list)]

            def proses(df, mask, kolom_sort):
                out = df[mask].drop(columns="_kunci")
                if sort_aktif:
                    out = sort_df_aman(out, kolom_sort, naik)
                return out.reset_index(drop=True)

            st.session_state.hasil = {
                "sama1": proses(d1, m1, sort1),
                "sama2": proses(d2, m2, sort2),
                "beda1": proses(d1, ~m1, sort1),
                "beda2": proses(d2, ~m2, sort2),
                "kolom1": kolom1_list, "kolom2": kolom2_list,
                "sort1": sort1 if sort_aktif else [],
                "sort2": sort2 if sort_aktif else [],
                "naik": naik,
                "vc1": d1.loc[layak1, "_kunci"].value_counts(),
                "vc2": d2.loc[layak2, "_kunci"].value_counts(),
            }

    # ================== HASIL ==================
    if st.session_state.hasil is not None:
        h = st.session_state.hasil
        label1 = " + ".join(map(str, h["kolom1"]))
        label2 = " + ".join(map(str, h["kolom2"]))

        # keterangan sorting
        if h["sort1"]:
            arah_txt = "naik ⬆️ (A→Z, 0→9)" if h["naik"] else "turun ⬇️ (Z→A, 9→0)"
            st.info(f"🔀 Hasil diurutkan berdasarkan: File 1 → `{', '.join(map(str, h['sort1']))}` | "
                    f"File 2 → `{', '.join(map(str, h['sort2']))}` | arah: {arah_txt}")

        st.divider()
        st.subheader("📈 Ringkasan")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("✅ Sama — File 1", len(h["sama1"]))
        m2.metric("✅ Sama — File 2", len(h["sama2"]))
        m3.metric("❌ Beda — File 1", len(h["beda1"]))
        m4.metric("❌ Beda — File 2", len(h["beda2"]))

        with st.expander("🔎 Detil kunci perbandingan (nilai ternormalisasi & jumlah kemunculan)"):
            semua_kunci = sorted(set(h["vc1"].index) | set(h["vc2"].index))
            detil = pd.DataFrame({"kunci": semua_kunci})
            detil["jumlah di File 1"] = detil["kunci"].map(h["vc1"]).fillna(0).astype(int)
            detil["jumlah di File 2"] = detil["kunci"].map(h["vc2"]).fillna(0).astype(int)
            detil["status"] = detil.apply(
                lambda r: "✅ cocok" if r["jumlah di File 1"] and r["jumlah di File 2"]
                else ("hanya File 1" if r["jumlah di File 1"] else "hanya File 2"), axis=1)
            st.dataframe(detil, use_container_width=True, height=300)

        st.subheader("✅ Dataframe dengan Nilai SAMA")
        t1, t2 = st.tabs(["📋 File 1", "📋 File 2"])
        with t1:
            st.caption(f"Kunci `{label1}` (setelah normalisasi) ditemukan di File 2")
            st.dataframe(h["sama1"], use_container_width=True)
        with t2:
            st.caption(f"Kunci `{label2}` (setelah normalisasi) ditemukan di File 1")
            st.dataframe(h["sama2"], use_container_width=True)

        st.subheader("❌ Dataframe dengan Nilai BERBEDA")
        t3, t4 = st.tabs(["📋 File 1", "📋 File 2"])
        with t3:
            st.caption(f"Kunci `{label1}` TIDAK ditemukan di File 2")
            st.dataframe(h["beda1"], use_container_width=True)
        with t4:
            st.caption(f"Kunci `{label2}` TIDAK ditemukan di File 1")
            st.dataframe(h["beda2"], use_container_width=True)

        st.divider()
        dl1, dl2 = st.columns(2)
        with dl1:
            st.download_button("⬇️ Unduh data SAMA (.xlsx)",
                data=export_excel({"SAMA File1": h["sama1"], "SAMA File2": h["sama2"]}),
                file_name="data_sama.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True)
        with dl2:
            st.download_button("⬇️ Unduh data BERBEDA (.xlsx)",
                data=export_excel({"BEDA File1": h["beda1"], "BEDA File2": h["beda2"]}),
                file_name="data_beda.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True)

else:
    st.info("⬆️ Unggah **kedua** file untuk melanjutkan. "
            "Kedua file boleh berbeda format (misal: File 1 = Excel, File 2 = CSV).")