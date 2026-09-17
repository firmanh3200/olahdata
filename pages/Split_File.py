import streamlit as st
import pandas as pd
import geopandas as gpd
import os
import zipfile
import tempfile
import shutil
import numpy as np
import re

# Konfigurasi tampilan halaman
st.set_page_config(page_title="File Splitter App", layout="wide")

st.title("📂 Aplikasi Split File")
st.write("""
Aplikasi ini digunakan untuk membagi satu file besar menjadi beberapa file bagian yang lebih kecil.
Format yang didukung: Excel, CSV, JSON, GeoJSON, Parquet.
""")

# Fungsi untuk membersihkan nama file dari karakter ilegal
def clean_filename(name):
    """Mengganti karakter ilegal dengan underscore"""
    return re.sub(r'[\\/*?:"<>|]', "_", str(name))

# 1. Memasukkan File
uploaded_file = st.file_uploader(
    "1. Upload File Anda", 
    type=['xlsx', 'xls', 'csv', 'json', 'geojson', 'parquet']
)

if uploaded_file is not None:
    try:
        # Mendapatkan nama dan ekstensi file
        file_name = uploaded_file.name
        file_ext = os.path.splitext(file_name)[1].lower()
        
        # Logika membaca file berdasarkan ekstensi
        df = None
        is_geo = False

        with st.spinner("Membaca file..."):
            if file_ext == '.geojson':
                df = gpd.read_file(uploaded_file)
                is_geo = True
            elif file_ext == '.csv':
                df = pd.read_csv(uploaded_file)
            elif file_ext in ['.xlsx', '.xls']:
                df = pd.read_excel(uploaded_file)
            elif file_ext == '.json':
                df = pd.read_json(uploaded_file)
            elif file_ext == '.parquet':
                df = pd.read_parquet(uploaded_file)
            else:
                st.error("Format file tidak didukung.")
                st.stop()

        # 2. Menampilkan Informasi File
        st.subheader("2. Informasi File")
        col1, col2, col3 = st.columns(3)
        col1.metric("Nama File", file_name)
        col2.metric("Jumlah Baris", df.shape[0])
        col3.metric("Jumlah Kolom", df.shape[1])

        # Preview Data
        with st.expander("Lihat 5 Data Teratas"):
            st.dataframe(df.head())

        # =======================
        # 3. Pengaturan Split (MODIFIKASI)
        # =======================
        st.subheader("3. Pengaturan Split")
        
        split_method = st.radio(
            "Pilih metode split:", 
            ("Berdasarkan Jumlah Bagian", "Berdasarkan Nilai Kolom")
        )

        # List untuk menampung pecahan dataframe dan nama file
        chunks = []
        file_suffixes = []

        if split_method == "Berdasarkan Jumlah Bagian":
            # Logika lama: split berdasarkan jumlah
            max_split = df.shape[0]
            num_parts = st.number_input(
                "Tentukan jumlah file yang akan dibentuk:", 
                min_value=1, 
                max_value=max_split, 
                value=2, 
                step=1
            )
            # Proses split
            chunks = np.array_split(df, num_parts)
            file_suffixes = [f"_part{i+1}" for i in range(len(chunks))]

        else:
            # Logika baru: split berdasarkan nilai kolom
            selected_col = st.selectbox("Pilih kolom untuk acuan split:", df.columns)
            
            if st.button("Tampilkan Nilai Unik"):
                unique_vals = df[selected_col].unique()
                st.info(f"Ditemukan {len(unique_vals)} nilai unik di kolom '{selected_col}'.")
                st.write(unique_vals[:20]) # Tampilkan 20 pertama saja biar tidak penuh

            if st.button("✂️ Split Berdasarkan Kolom", type="primary"):
                # Proses grouping
                grouped = df.groupby(selected_col)
                
                # Progress bar untuk proses grouping (karena bisa lama jika data besar)
                progress_grouping = st.progress(0)
                total_groups = len(grouped)
                
                for i, (name, group_df) in enumerate(grouped):
                    chunks.append(group_df)
                    # Bersihkan nama nilai kolom agar bisa dijadikan nama file
                    safe_name = clean_filename(name)
                    file_suffixes.append(f"_{safe_name}")
                    progress_grouping.progress((i + 1) / total_groups)
                
                st.success(f"Data siap di-split menjadi {len(chunks)} file.")
            
            # Jika proses belum dijalankan, inisialisasi kosong agar tombol split utama tidak error
            if 'chunks' not in locals() or len(chunks) == 0:
                chunks = []
                file_suffixes = []

        # =======================
        # 4. Menentukan folder simpan & Opsi Download
        # =======================
        st.subheader("4. Lokasi Penyimpanan")
        st.info("""
            **Catatan:** Aplikasi Streamlit berjalan di browser. 
            Jika dijalankan lokal (komputer sendiri), Anda bisa menyimpan langsung ke folder. 
            Jika tidak, gunakan opsi Download ZIP.
        """)
        
        save_option = st.radio("Metode Penyimpanan:", ("Download sebagai ZIP", "Simpan ke Folder Lokal (Server)"))
        
        local_path = ""
        if save_option == "Simpan ke Folder Lokal (Server)":
            default_path = os.path.join(os.getcwd(), "output_split")
            local_path = st.text_input("Masukkan path folder tujuan:", value=default_path)

        # =======================
        # 5. Tombol Split File Utama (Disesuaikan)
        # =======================
        # Tombol ini hanya muncul jika chunks sudah ada (baik via number input atau split kolom)
        
        # Kondisi tombol: 
        # Jika metode jumlah, tampilkan tombol biasa.
        # Jika metode kolom, tombol sudah ditekan di atas, jadi langsung tampilkan opsi simpan.
        
        show_save_options = False
        
        if split_method == "Berdasarkan Jumlah Bagian":
            if st.button("✂️ Split File", type="primary"):
                show_save_options = True
        else:
            # Jika metode kolom, cek apakah chunks sudah terisi
            if len(chunks) > 0:
                show_save_options = True

        if show_save_options and len(chunks) > 0:
            if df.shape[0] == 0:
                st.warning("File kosong, tidak bisa di-split.")
            else:
                base_name = os.path.splitext(file_name)[0]
                files_created_count = 0
                
                progress_bar = st.progress(0)
                status_text = st.empty()

                # Penanganan penyimpanan
                if save_option == "Download sebagai ZIP":
                    with tempfile.TemporaryDirectory() as temp_dir:
                        zip_filename = f"{base_name}_split.zip"
                        zip_path = os.path.join(temp_dir, zip_filename)
                        
                        with zipfile.ZipFile(zip_path, 'w') as zipf:
                            # Iterasi menggunakan zip(chunks, file_suffixes)
                            for i, (chunk, suffix) in enumerate(zip(chunks, file_suffixes)):
                                # Gunakan suffix yang sudah dibuat (misal: _adam atau _part1)
                                part_filename = f"{base_name}{suffix}{file_ext}"
                                temp_file_path = os.path.join(temp_dir, part_filename)
                                
                                # Simpan sementara
                                if file_ext == '.geojson':
                                    chunk.to_file(temp_file_path, driver='GeoJSON')
                                elif file_ext == '.csv':
                                    chunk.to_csv(temp_file_path, index=False)
                                elif file_ext in ['.xlsx', '.xls']:
                                    chunk.to_excel(temp_file_path, index=False)
                                elif file_ext == '.json':
                                    chunk.to_json(temp_file_path, orient='records')
                                elif file_ext == '.parquet':
                                    chunk.to_parquet(temp_file_path, index=False)
                                
                                # Tambahkan ke zip
                                zipf.write(temp_file_path, part_filename)
                                files_created_count += 1
                                progress_bar.progress((i + 1) / len(chunks))
                                status_text.text(f"Membuat file {i+1} dari {len(chunks)}...")

                        status_text.text("Proses selesai!")
                        with open(zip_path, "rb") as f:
                            st.success(f"Berhasil! {files_created_count} file telah dibentuk.")
                            st.download_button(
                                label="📥 Download File ZIP",
                                data=f,
                                file_name=zip_filename,
                                mime="application/zip"
                            )

                else: # Simpan ke Folder Lokal
                    if not os.path.exists(local_path):
                        os.makedirs(local_path)
                    
                    saved_files_list = []
                    for i, (chunk, suffix) in enumerate(zip(chunks, file_suffixes)):
                        part_filename = f"{base_name}{suffix}{file_ext}"
                        save_path = os.path.join(local_path, part_filename)
                        
                        if file_ext == '.geojson':
                            chunk.to_file(save_path, driver='GeoJSON')
                        elif file_ext == '.csv':
                            chunk.to_csv(save_path, index=False)
                        elif file_ext in ['.xlsx', '.xls']:
                            chunk.to_excel(save_path, index=False)
                        elif file_ext == '.json':
                            chunk.to_json(save_path, orient='records')
                        elif file_ext == '.parquet':
                            chunk.to_parquet(save_path, index=False)
                            
                        files_created_count += 1
                        saved_files_list.append(part_filename)
                        progress_bar.progress((i + 1) / len(chunks))
                        status_text.text(f"Membuat file {i+1} dari {len(chunks)}...")

                    st.success(f"Berhasil! {files_created_count} file telah dibentuk di folder: `{local_path}`")
                    st.write("Daftar file:")
                    st.write(saved_files_list)

    except Exception as e:
        st.error(f"Terjadi kesalahan saat memproses file: {e}")
        st.error("Pastikan file tidak rusak dan library pendukung (seperti openpyxl/geopandas) sudah terinstal.")

else:
    st.warning("Silakan upload file untuk memulai.")