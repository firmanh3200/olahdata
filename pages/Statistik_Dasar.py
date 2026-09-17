import streamlit as st
import pandas as pd
import numpy as np
import json
import os
import io
import tempfile

# Opsional: untuk file DBF
try:
    from dbfread import DBF
    DBF_OK = True
except ImportError:
    DBF_OK = False

# ==========================================
# KONFIGURASI HALAMAN
# ==========================================
st.set_page_config(
    page_title="Pengolah Statistik Dasar",
    page_icon="📊",
    layout="wide"
)

# ==========================================
# FUNGSI MEMBACA DATA BERBAGAI FORMAT
# ==========================================
def load_data(file_bytes, filename):
    ext = os.path.splitext(filename)[1].lower()

    if ext == ".csv":
        for enc in ["utf-8", "utf-8-sig", "latin-1"]:
            try:
                return pd.read_csv(io.BytesIO(file_bytes),
                                   encoding=enc, sep=None, engine="python")
            except Exception:
                continue
        raise ValueError("Gagal membaca file CSV.")

    elif ext in [".xls", ".xlsx"]:
        return pd.read_excel(io.BytesIO(file_bytes))

    elif ext == ".tsv":
        return pd.read_csv(io.BytesIO(file_bytes), sep="\t")

    elif ext == ".json":
        data = json.loads(file_bytes.decode("utf-8"))
        return pd.json_normalize(data)

    elif ext == ".dbf":
        if not DBF_OK:
            raise ValueError("Library dbfread belum terinstall. Jalankan: pip install dbfread")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".dbf") as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        try:
            table = DBF(tmp_path, encoding="latin-1")
            return pd.DataFrame(iter(table))
        finally:
            os.remove(tmp_path)

    elif ext == ".parquet":
        return pd.read_parquet(io.BytesIO(file_bytes))

    elif ext in [".txt", ".dat"]:
        for enc in ["utf-8", "latin-1"]:
            try:
                return pd.read_csv(io.BytesIO(file_bytes),
                                   encoding=enc, sep=None, engine="python")
            except Exception:
                continue
        raise ValueError("Gagal membaca file teks.")

    else:
        raise ValueError(f"Format file {ext} belum didukung.")


def hitung_statistik(df):
    """Menghitung statistik dasar semua kolom numerik."""
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    if not numeric_cols:
        return None

    stats = pd.DataFrame({
        "Jumlah Data": df[numeric_cols].count(),
        "Mean (Rata-rata)": df[numeric_cols].mean(),
        "Median": df[numeric_cols].median(),
        "Modus": df[numeric_cols].mode().iloc[0],
        "Std Deviasi": df[numeric_cols].std(),
        "Variansi": df[numeric_cols].var(),
        "Minimum": df[numeric_cols].min(),
        "Maksimum": df[numeric_cols].max(),
        "Q1 (25%)": df[numeric_cols].quantile(0.25),
        "Q3 (75%)": df[numeric_cols].quantile(0.75),
        "Range": df[numeric_cols].max() - df[numeric_cols].min(),
        "Skewness": df[numeric_cols].skew(),
        "Kurtosis": df[numeric_cols].kurtosis(),
    })
    return stats.round(4)

# ==========================================
# TAMPILAN UTAMA
# ==========================================
st.title("📊 Aplikasi Pengolah Statistik Dasar")
st.markdown("Unggah file data Anda dan hitung statistik dasar secara instan.")

# --- 1. UNGGAH FILE ---
st.sidebar.header("📤 1. Unggah File")
uploaded_file = st.sidebar.file_uploader(
    "Pilih file data",
    type=["csv", "xls", "xlsx", "dbf", "json", "txt", "tsv", "parquet"]
)

if uploaded_file is None:
    st.info("👈 Silakan unggah file di sidebar. Format yang didukung: "
            "**CSV, XLS, XLSX, DBF, JSON, TXT, TSV, Parquet**")
    st.stop()

# --- BACA DATA ---
try:
    df = load_data(uploaded_file.getvalue(), uploaded_file.name)
except Exception as e:
    st.error(f"❌ Gagal membaca file: {e}")
    st.stop()

st.sidebar.success(f"✅ **{uploaded_file.name}** berhasil dimuat")
st.sidebar.write(f"Baris: **{df.shape[0]}** | Kolom: **{df.shape[1]}**")

# --- PRATINJAU DATA ---
with st.expander("👀 Pratinjau Data (10 baris pertama)", expanded=True):
    st.dataframe(df.head(10), use_container_width=True)

# --- 2. TOMBOL STATISTIK ---
st.markdown("---")
if st.button("📈 2. Hitung Statistik Dasar", type="primary", use_container_width=True):
    st.session_state["tampilkan_statistik"] = True

# --- 3. TAMPILKAN STATISTIK ---
if st.session_state.get("tampilkan_statistik", False):

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    object_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()

    st.header("📋 3. Hasil Statistik Dasar")

    if not numeric_cols:
        st.warning("⚠️ Tidak ditemukan kolom numerik dalam data!")
    else:
        # Ringkasan semua kolom numerik
        stats = hitung_statistik(df)
        st.subheader("Ringkasan Semua Kolom Numerik")
        st.dataframe(stats, use_container_width=True)

        # Tombol unduh hasil
        csv_stats = stats.to_csv().encode("utf-8")
        st.download_button(
            label="💾 Unduh Statistik (CSV)",
            data=csv_stats,
            file_name="statistik_dasar.csv",
            mime="text/csv"
        )

        # Detail per kolom
        st.subheader("Detail per Kolom")
        pilih_kolom = st.selectbox("Pilih kolom:", numeric_cols)
        kolom = df[pilih_kolom].dropna()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Mean", f"{kolom.mean():.2f}")
        c1.metric("Median", f"{kolom.median():.2f}")
        c2.metric("Std Deviasi", f"{kolom.std():.2f}")
        c2.metric("Variansi", f"{kolom.var():.2f}")
        c3.metric("Minimum", f"{kolom.min():.2f}")
        c3.metric("Maksimum", f"{kolom.max():.2f}")
        c4.metric("Jumlah Data", f"{kolom.count()}")
        c4.metric("Data Kosong", f"{df[pilih_kolom].isna().sum()}")

        # Histogram
        st.subheader(f"Distribusi Data: {pilih_kolom}")
        hist, bins = np.histogram(kolom, bins=20)
        chart_df = pd.DataFrame({
            "Frekuensi": hist,
            "Interval": [f"{bins[i]:.1f} - {bins[i+1]:.1f}" for i in range(len(hist))]
        })
        st.bar_chart(chart_df.set_index("Interval"))

    # Statistik kolom kategorik
    if object_cols:
        st.subheader("Statistik Kolom Kategorik")
        katik_stats = df[object_cols].describe().T.rename(columns={
            "count": "Jumlah Data", "unique": "Jumlah Unik",
            "top": "Nilai Terbanyak", "freq": "Frekuensi"
        })
        st.dataframe(katik_stats, use_container_width=True)