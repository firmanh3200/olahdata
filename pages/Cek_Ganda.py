import streamlit as st
import pandas as pd
import os
import re
from pathlib import Path

# Coba import library untuk DBF
try:
    from dbfread import DBF
    DBF_AVAILABLE = True
except ImportError:
    DBF_AVAILABLE = False

st.set_page_config(page_title="Aplikasi Pemrosesan Data", layout="wide")
st.title("🗂️ Aplikasi Pemrosesan Data")

# Inisialisasi session state
if 'df_work' not in st.session_state:
    st.session_state.df_work = None
if 'current_file' not in st.session_state:
    st.session_state.current_file = None
if 'current_sheet' not in st.session_state:
    st.session_state.current_sheet = None
if 'dup_processed' not in st.session_state:
    st.session_state.dup_processed = False

# ---------------------------------------------------------------
# 1. INPUT LOKASI FOLDER
# ---------------------------------------------------------------
st.header("1. Lokasi Folder")
folder_path = st.text_input("Masukkan path folder yang berisi banyak file:")

valid_extensions = ['.csv', '.xlsx', '.xls', '.parquet', '.dbf']
files = []

if folder_path:
    if os.path.isdir(folder_path):
        files = [f for f in os.listdir(folder_path)
                 if os.path.splitext(f)[1].lower() in valid_extensions]
        if files:
            st.success(f"Ditemukan {len(files)} file yang didukung di folder tersebut.")
        else:
            st.warning("Tidak ada file (csv/excel/parquet/dbf) di folder tersebut.")
    else:
        st.error("Folder tidak ditemukan! Periksa kembali path yang dimasukkan.")

# ---------------------------------------------------------------
# 2. PILIH FILE
# ---------------------------------------------------------------
if files:
    st.header("2. Pilih File")
    selected_file = st.selectbox("Pilih file untuk ditampilkan:", files)

    # Reset state jika file berganti
    if selected_file != st.session_state.current_file:
        st.session_state.current_file = selected_file
        st.session_state.df_work = None
        st.session_state.dup_processed = False
        st.session_state.current_sheet = None # Reset sheet juga

    file_path = os.path.join(folder_path, selected_file)
    ext = os.path.splitext(selected_file)[1].lower()

    # Fungsi cache untuk membaca file
    @st.cache_data(show_spinner=False)
    def load_file(path, extension, sheet_name=None):
        if extension == '.csv':
            return pd.read_csv(path)
        elif extension in ['.xlsx', '.xls']:
            return pd.read_excel(path, sheet_name=sheet_name)
        elif extension == '.parquet':
            return pd.read_parquet(path)
        elif extension == '.dbf':
            if DBF_AVAILABLE:
                dbf = DBF(path)
                return pd.DataFrame(iter(dbf))
            else:
                st.error("Library `dbfread` belum terpasang. Jalankan: `pip install dbfread`")
                return None
        return None

    # Fungsi cache untuk mengambil daftar nama sheet di file excel
    @st.cache_data(show_spinner=False)
    def get_excel_sheets(path):
        xls = pd.ExcelFile(path)
        return xls.sheet_names

    df = None

    # Logika khusus jika file adalah Excel
    if ext in ['.xlsx', '.xls']:
        sheets = get_excel_sheets(file_path)
        
        # 2.5. PILIH SHEET
        selected_sheet = st.selectbox("Pilih sheet pada file Excel:", sheets)
        
        # Reset state jika sheet berganti
        if selected_sheet != st.session_state.current_sheet:
            st.session_state.current_sheet = selected_sheet
            st.session_state.df_work = None
            st.session_state.dup_processed = False
            
        df = load_file(file_path, ext, sheet_name=selected_sheet)
    else:
        # Untuk file non-excel
        df = load_file(file_path, ext)

    if df is not None:
        # Inisialisasi df_work jika masih kosong
        if st.session_state.df_work is None:
            st.session_state.df_work = df.copy()

                # -------------------------------------------------------
        # 3. PILIH KOLOM & TAMPILKAN FILE
        # -------------------------------------------------------
        st.header("3. Pilih Kolom & Tampilan File")
        st.write(f"**Nama file:** `{selected_file}`  |  **Ukuran:** {df.shape[0]} baris × {df.shape[1]} kolom")

        st.caption("Kolom yang tidak dipilih akan dibuang dari data kerja (berlaku juga untuk "
                   "normalisasi, sorting, dan duplikasi di bawah). Menerapkan ulang akan mereset "
                   "normalisasi/sorting sebelumnya.")

        keep_cols = st.multiselect(
            "Pilih kolom yang akan dipertahankan (kosongkan untuk semua kolom):",
            options=list(df.columns),   # selalu dari file asli agar daftar tidak menyusut
            key="keep_cols"
        )

        if st.button("🔧 Terapkan Pemilihan Kolom", key="apply_cols"):
            if keep_cols:
                st.session_state.df_work = df[list(keep_cols)].copy()
                st.session_state.dup_processed = False
                st.success(f"✅ Data kerja sekarang hanya berisi {len(keep_cols)} kolom.")
            else:
                st.session_state.df_work = df.copy()
                st.session_state.dup_processed = False
                st.info("Semua kolom dikembalikan.")

        st.dataframe(st.session_state.df_work, use_container_width=True)

        # -------------------------------------------------------
        # 4. PILIH KOLOM UNTUK DINORMALISASI
        # -------------------------------------------------------
        st.header("4. Normalisasi Kolom")
        st.caption("Normalisasi: huruf kecil semua, hapus karakter selain huruf & angka, hapus spasi berlebih.")
        normalize_cols = st.multiselect(
            "Pilih kolom yang akan dinormalisasi:",
            options=st.session_state.df_work.columns
        )

        # -------------------------------------------------------
        # 5. TOMBOL NORMALISASI
        # -------------------------------------------------------
        if st.button("5. 🔧 Normalisasi", type="primary"):
            if normalize_cols:
                def normalize_text(val):
                    if pd.isna(val):
                        return val
                    s = str(val).lower()
                    s = re.sub(r'[^a-z0-9\s]', '', s)   # hapus karakter non-alfanumerik
                    s = re.sub(r'\s+', ' ', s).strip()  # hapus spasi berlebih
                    return s

                for col in normalize_cols:
                    st.session_state.df_work[col] = st.session_state.df_work[col].apply(normalize_text)

                # Reset hasil duplikasi karena data sudah berubah
                st.session_state.dup_processed = False

                st.success(f"✅ Kolom berhasil dinormalisasi: {', '.join(normalize_cols)}")
                st.dataframe(st.session_state.df_work, use_container_width=True)
            else:
                st.warning("Pilih minimal satu kolom untuk dinormalisasi.")

        # -------------------------------------------------------
        # 6. PILIH KOLOM UNTUK SORTING
        # -------------------------------------------------------
        st.header("6. Sorting Data")
        sort_cols = st.multiselect(
            "Pilih kolom untuk sorting (urutan berpengaruh):",
            options=st.session_state.df_work.columns,
            key="sort_cols"
        )

        sort_orders = {}
        if sort_cols:
            st.write("**Atur urutan (Ascending/Descending) per kolom:**")
            cols_layout = st.columns(min(len(sort_cols), 3))
            for i, col in enumerate(sort_cols):
                with cols_layout[i % len(cols_layout)]:
                    sort_orders[col] = st.radio(
                        f"`{col}`",
                        options=["Ascending", "Descending"],
                        horizontal=True,
                        key=f"sort_{col}"
                    )

        # -------------------------------------------------------
        # 7. TOMBOL URUTKAN DATA
        # -------------------------------------------------------
        if st.button("7. 🔃 Urutkan Data", type="primary"):
            if sort_cols:
                ascending = [sort_orders[col] == "Ascending" for col in sort_cols]
                st.session_state.df_work = st.session_state.df_work.sort_values(
                    by=sort_cols, ascending=ascending
                ).reset_index(drop=True)
                st.session_state.dup_processed = False
                st.success("✅ Data berhasil diurutkan berdasarkan kolom terpilih.")
                st.dataframe(st.session_state.df_work, use_container_width=True)
            else:
                st.warning("Pilih minimal satu kolom untuk sorting.")

        # -------------------------------------------------------
        # 8. PILIH KOLOM UNTUK MENCARI DUPLIKASI
        # -------------------------------------------------------
        st.header("8. Cari Duplikasi Data")
        dup_cols = st.multiselect(
            "Pilih kolom untuk mendeteksi duplikasi:",
            options=st.session_state.df_work.columns,
            key="dup_cols"
        )

        # -------------------------------------------------------
        # 9. TOMBOL CARI DUPLIKASI
        # -------------------------------------------------------
        if st.button("9. 🔍 Cari Duplikasi", type="primary"):
            if dup_cols:
                df_current = st.session_state.df_work.copy()

                # Mark semua baris yang duplikat
                is_dup = df_current.duplicated(subset=dup_cols, keep=False)

                # 1) Dataframe hanya berisi data duplikasi
                df_duplicates = df_current[is_dup].copy()

                # 2) Semua data + kolom info duplikasi
                df_all_with_info = df_current.copy()
                df_all_with_info['_is_duplicate'] = is_dup
                df_all_with_info['_dup_group'] = df_current.groupby(dup_cols).ngroup()

                # 3) Dataframe terhindar dari duplikasi (keep first)
                df_dedup = df_current.drop_duplicates(subset=dup_cols, keep='first').copy()

                st.session_state.df_duplicates = df_duplicates
                st.session_state.df_all_with_info = df_all_with_info
                st.session_state.df_dedup = df_dedup
                st.session_state.dup_processed = True

                st.success(
                    f"✅ Duplikasi diproses! "
                    f"{int(is_dup.sum())} baris duplikat ditemukan, "
                    f"{len(df_dedup)} baris unik tersisa."
                )
            else:
                st.warning("Pilih minimal satu kolom untuk mendeteksi duplikasi.")

        # -------------------------------------------------------
        # 10. TAMPILKAN 3 DATAFRAME HASIL DUPLIKASI
        # -------------------------------------------------------
        if st.session_state.dup_processed:
            st.header("10. Hasil Pencarian Duplikasi")

            st.subheader("1️⃣ Dataframe Berisi Data Duplikasi")
            st.write(f"Ukuran: {st.session_state.df_duplicates.shape[0]} baris × "
                     f"{st.session_state.df_duplicates.shape[1]} kolom")
            st.dataframe(st.session_state.df_duplicates, use_container_width=True)

            st.subheader("2️⃣ Semua Data + Kolom Informasi Duplikasi")
            st.write(f"Ukuran: {st.session_state.df_all_with_info.shape[0]} baris × "
                     f"{st.session_state.df_all_with_info.shape[1]} kolom")
            st.dataframe(st.session_state.df_all_with_info, use_container_width=True)

            st.subheader("3️⃣ Dataframe Terhindar dari Duplikasi (Sisa Baris Pertama)")
            st.write(f"Ukuran: {st.session_state.df_dedup.shape[0]} baris × "
                     f"{st.session_state.df_dedup.shape[1]} kolom")
            st.dataframe(st.session_state.df_dedup, use_container_width=True)

            # ---------------------------------------------------
            # 12. PILIH KOLOM UNTUK FILTER PADA DATAFRAME 2)
            # ---------------------------------------------------
            st.header("12. Filter pada Dataframe 2)")
            df2 = st.session_state.df_all_with_info

            filter_cols = st.multiselect(
                "Pilih kolom untuk dijadikan filter:",
                options=df2.columns,
                key="filter_cols"
            )

            filter_conditions = {}
            if filter_cols:
                for col in filter_cols:
                    unique_vals = df2[col].dropna().unique()
                    if len(unique_vals) > 200:
                        st.warning(f"Kolom `{col}` memiliki {len(unique_vals)} nilai unik. "
                                   "Menggunakan input teks sebagai alternatif.")
                        txt = st.text_input(f"Ketik nilai untuk `{col}` (pisahkan dengan koma):",
                                            key=f"txt_{col}")
                        if txt.strip():
                            vals = [v.strip() for v in txt.split(',') if v.strip()]
                            filter_conditions[col] = vals
                    else:
                        try:
                            options_list = sorted(unique_vals.tolist(), key=lambda x: str(x))
                        except Exception:
                            options_list = list(unique_vals)
                        selected_vals = st.multiselect(
                            f"Nilai untuk `{col}`:",
                            options=options_list,
                            key=f"sel_{col}"
                        )
                        if selected_vals:
                            filter_conditions[col] = selected_vals

            # ---------------------------------------------------
            # 13. TAMPILKAN DATAFRAME HASIL FILTER
            # ---------------------------------------------------
            if filter_conditions:
                mask = pd.Series([True] * len(df2))
                for col, vals in filter_conditions.items():
                    mask &= df2[col].isin(vals)

                df_filtered = df2[mask].copy()

                st.header("13. Dataframe Hasil Filter")
                st.write(f"Ukuran: {df_filtered.shape[0]} baris × {df_filtered.shape[1]} kolom")
                st.dataframe(df_filtered, use_container_width=True)

                csv = df_filtered.to_csv(index=False).encode('utf-8')
                st.download_button(
                    "⬇️ Unduh hasil filter (CSV)",
                    data=csv,
                    file_name="hasil_filter.csv",
                    mime="text/csv"
                )
            else:
                st.info("Pilih minimal satu kolom dan nilai filter untuk menampilkan hasil.")