import streamlit as st
import pandas as pd
import os
import re
from pathlib import Path

st.set_page_config(page_title="Gabung & Proses Excel", layout="wide")
st.title("📊 Aplikasi Gabung & Proses File Excel")

# ---- Inisialisasi session state ----
if "df_gabungan" not in st.session_state:
    st.session_state.df_gabungan = None
if "df_duplikasi" not in st.session_state:
    st.session_state.df_duplikasi = None
if "df_dengan_flag" not in st.session_state:
    st.session_state.df_dengan_flag = None

# ============================================================
# 1. INPUT LOKASI FOLDER
# ============================================================
st.subheader("1️⃣ Lokasi Folder File Excel")
folder_path = st.text_input(
    "Masukkan path folder yang berisi file Excel (.xlsx / .xls):",
    value="",
    placeholder="Contoh: C:/Users/nama/Documents/data-excel"
)

# ============================================================
# 2. TOMBOL GABUNG
# ============================================================
st.subheader("2️⃣ Gabungkan File Excel")
col_btn1, col_info1 = st.columns([1, 3])

def gabung_file_excel(path):
    if not path or not os.path.isdir(path):
        st.error("Folder tidak ditemukan. Periksa kembali path-nya.")
        return None
    files = [f for f in os.listdir(path)
             if f.lower().endswith((".xlsx", ".xls")) and not f.startswith("~$")]
    if not files:
        st.error("Tidak ada file Excel di folder tersebut.")
        return None
    dfs = []
    progress = st.progress(0.0, text="Menggabungkan file...")
    for i, f in enumerate(files):
        try:
            df = pd.read_excel(os.path.join(path, f))
            df["__sumber_file__"] = f
            dfs.append(df)
        except Exception as e:
            st.warning(f"Gagal membaca {f}: {e}")
        progress.progress((i + 1) / len(files), text=f"Membaca {f}")
    progress.empty()
    if not dfs:
        st.error("Tidak ada file yang berhasil dibaca.")
        return None
    return pd.concat(dfs, ignore_index=True)

if col_btn1.button("🔗 Gabung File Excel", type="primary"):
    df = gabung_file_excel(folder_path)
    if df is not None:
        st.session_state.df_gabungan = df
        st.session_state.df_duplikasi = None
        st.session_state.df_dengan_flag = None
        st.success(f"Berhasil! {df.shape[0]} baris × {df.shape[1]} kolom.")
        st.rerun()

# ============================================================
# 4. TAMPILKAN DATAFRAME GABUNGAN
# ============================================================
df = st.session_state.df_gabungan
if df is not None:
    st.subheader("4️⃣ Dataframe Gabungan")
    st.dataframe(df.head(500), use_container_width=True)
    st.caption(f"Menampilkan 500 baris pertama dari total {len(df):,} baris.")

    # ========================================================
    # 3. SIMPAN KE CSV / PARQUET
    # ========================================================
    st.subheader("3️⃣ Simpan Hasil Gabungan")
    c1, c2, c3 = st.columns(3)
    nama_default = c1.text_input("Nama file (tanpa ekstensi):", value="gabungan")
    if c2.button("💾 Simpan ke CSV"):
        out_path = os.path.join(folder_path or ".", f"{nama_default}.csv")
        df.to_csv(out_path, index=False)
        st.success(f"Tersimpan: {out_path}")
    if c3.button("💾 Simpan ke Parquet"):
        out_path = os.path.join(folder_path or ".", f"{nama_default}.parquet")
        df.to_parquet(out_path, index=False)
        st.success(f"Tersimpan: {out_path}")

    # ========================================================
    # 5 & 6. NORMALISASI KOLOM
    # ========================================================
    st.subheader("5️⃣6️⃣ Normalisasi Kolom")
    kolom_tersedia = df.columns.tolist()
    kolom_norm = st.multiselect(
        "Pilih kolom yang akan dinormalisasi:",
        options=kolom_tersedia
    )
    if st.button("🧹 Normalisasi"):
        if kolom_norm:
            for k in kolom_norm:
                # konversi ke string
                s = df[k].astype(str)
                # huruf kecil
                s = s.str.lower()
                # hapus karakter selain huruf dan angka
                s = s.apply(lambda x: re.sub(r"[^a-z0-9\s]", "", x))
                # hapus spasi berlebih
                s = s.str.replace(r"\s+", " ", regex=True).str.strip()
                df[k] = s
            st.session_state.df_gabungan = df
            st.success(f"Normalisasi selesai pada kolom: {', '.join(kolom_norm)}")
            st.rerun()
        else:
            st.warning("Pilih minimal 1 kolom.")

    # ========================================================
    # 7 & 8. SORTING
    # ========================================================
    st.subheader("7️⃣8️⃣ Urutkan Data")
    kolom_sort = st.multiselect(
        "Pilih kolom untuk sorting (urutan = prioritas):",
        options=kolom_tersedia
    )
    asc_options = []
    if kolom_sort:
        for k in kolom_sort:
            asc = st.checkbox(f"Urutkan '{k}' ascending (centang=asc, uncheck=desc)", value=True)
            asc_options.append(asc)
    if st.button("↕️ Urutkan Data"):
        if kolom_sort:
            df_sorted = df.sort_values(by=kolom_sort, ascending=asc_options).reset_index(drop=True)
            st.session_state.df_gabungan = df_sorted
            st.success("Data berhasil diurutkan.")
            st.rerun()
        else:
            st.warning("Pilih minimal 1 kolom.")

    # ========================================================
    # 9, 10, 11. CARI DUPLIKASI
    # ========================================================
    st.subheader("9️⃣🔟1️⃣ Cari Duplikasi Data")
    kolom_dup = st.multiselect(
        "Pilih kolom untuk menentukan duplikasi:",
        options=kolom_tersedia,
        key="kolom_dup"
    )
    if st.button("🔍 Cari Duplikasi"):
        if kolom_dup:
            # tandai semua duplikat (keep=False -> semua baris yg merupakan duplik ditandai)
            mask_dup = df.duplicated(subset=kolom_dup, keep=False)
            df_flag = df.copy()
            df_flag["__is_duplikat__"] = mask_dup
            df_dup_only = df_flag[mask_dup].copy()
            st.session_state.df_duplikasi = df_dup_only
            st.session_state.df_dengan_flag = df_flag
            st.success(f"Ditemukan {df_dup_only.shape[0]:,} baris duplikat "
                        f"dari {len(df):,} baris total.")
            st.rerun()
        else:
            st.warning("Pilih minimal 1 kolom.")

    # ========================================================
    # 11. TAMPILKAN 2 DATAFRAME HASIL DUPLIKASI
    # ========================================================
    if st.session_state.df_duplikasi is not None and st.session_state.df_dengan_flag is not None:
        st.markdown("### 1️⃣1️⃣ Hasil Duplikasi")

        st.markdown("**Dataframe 1 — Data Duplikasi Saja**")
        st.dataframe(st.session_state.df_duplikasi.head(500), use_container_width=True)
        st.caption(f"Total baris duplikat: {len(st.session_state.df_duplikasi):,}")

        st.markdown("**Dataframe 2 — Semua Data + Kolom Penanda Duplikasi**")
        st.dataframe(st.session_state.df_dengan_flag.head(500), use_container_width=True)
        st.caption(f"Total baris: {len(st.session_state.df_dengan_flag):,}")

        # ====================================================
        # 12 & 13. FILTER PADA DATAFRAME 2
        # ====================================================
        st.subheader("1️⃣2️⃣1️⃣3️⃣ Filter Dataframe 2")
        kolom_filter = st.multiselect(
            "Pilih kolom untuk filter:",
            options=st.session_state.df_dengan_flag.columns.tolist(),
            key="kolom_filter"
        )

        filter_conditions = {}
        if kolom_filter:
            for k in kolom_filter:
                unique_vals = st.session_state.df_dengan_flag[k].dropna().unique().tolist()
                if len(unique_vals) <= 50:
                    sel = st.multiselect(f"Nilai '{k}':", options=unique_vals, key=f"f_{k}")
                    if sel:
                        filter_conditions[k] = sel
                else:
                    # numeric range
                    try:
                        col_series = pd.to_numeric(st.session_state.df_dengan_flag[k], errors="coerce")
                        lo, hi = st.slider(f"Range '{k}':",
                                           float(col_series.min()),
                                           float(col_series.max()),
                                           (float(col_series.min()), float(col_series.max())),
                                           key=f"slider_{k}")
                        filter_conditions[k] = ("range", lo, hi, k)
                    except Exception:
                        txt = st.text_input(f"Kata kunci '{k}' (berisi):", value="", key=f"txt_{k}")
                        if txt.strip():
                            filter_conditions[k] = ("contains", txt.strip())

        if st.button("🎯 Terapkan Filter"):
            df_f = st.session_state.df_dengan_flag.copy()
            for k, v in filter_conditions.items():
                if isinstance(v, list):
                    df_f = df_f[df_f[k].isin(v)]
                elif isinstance(v, tuple) and v[0] == "range":
                    _, lo, hi, colname = v
                    df_f = df_f[(pd.to_numeric(df_f[colname], errors="coerce") >= lo) &
                                (pd.to_numeric(df_f[colname], errors="coerce") <= hi)]
                elif isinstance(v, tuple) and v[0] == "contains":
                    df_f = df_f[df_f[k].astype(str).str.contains(v[1], case=False, na=False)]
            st.session_state.df_filtered = df_f
            st.success(f"Hasil filter: {len(df_f):,} baris.")
            st.rerun()

        if "df_filtered" in st.session_state and st.session_state.df_filtered is not None:
            st.markdown("### 1️⃣3️⃣ Dataframe Hasil Filter")
            st.dataframe(st.session_state.df_filtered.head(1000), use_container_width=True)
            st.caption(f"Total baris hasil filter: {len(st.session_state.df_filtered):,}")
else:
    st.info("Belum ada dataframe. Isi path folder lalu tekan tombol **Gabung File Excel**.")