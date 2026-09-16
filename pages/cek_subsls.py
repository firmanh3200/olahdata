import streamlit as st
import pandas as pd
import geopandas as gpd
from pathlib import Path
import uuid
import time

# Konfigurasi halaman
st.set_page_config(
    page_title="Cek SUBSLS",
    page_icon="📍",
    layout="wide"
)

# Direktori penyimpanan file
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# Fungsi untuk menampilkan alert duplikasi
def show_duplicate_alert(duplicate_count, source):
    if duplicate_count == 0:
        st.success(f"✅ Tidak ada duplikasi data di {source}")
    else:
        st.warning(f"⚠️ Ditemukan {duplicate_count} data duplikat di {source}")

# Fungsi untuk menampilkan tabel data
def show_data_table(df, title, max_rows=10, highlight_duplicates=False, columns=None):
    st.subheader(f"{title} ({len(df)} baris)")
    
    # Pilih kolom yang akan ditampilkan
    if columns:
        display_df = df[columns].copy()
    else:
        display_df = df.copy()
    
    # Deteksi duplikat jika diminta
    if highlight_duplicates and 'idsubsls' in display_df.columns:
        duplicates = display_df[display_df.duplicated(subset=['idsubsls'], keep=False)]
        duplicate_ids = duplicates['idsubsls'].tolist()
        
        # Highlight baris duplikat
        def highlight_dup(row):
            if 'idsubsls' in row and str(row['idsubsls']) in duplicate_ids:
                return ['background-color: yellow'] * len(row)
            return [''] * len(row)
        
        styled_df = display_df.head(max_rows).style.apply(highlight_dup, axis=1)
        st.dataframe(styled_df, use_container_width=True)
    else:
        st.dataframe(display_df.head(max_rows), use_container_width=True)

# Fungsi untuk menampilkan tabel duplikat
def show_duplicate_table(duplicates, source):
    if len(duplicates) > 0:
        st.subheader(f"Detail Duplikat di {source}")
        st.dataframe(duplicates, use_container_width=True)

# Fungsi untuk menampilkan hasil perbandingan
def show_comparison_result(df_diff, msls_duplicates, petasls_duplicates, nmsls_diff):
    with st.container(border=True):
        st.header("Hasil Pengecekan dan Perbandingan SUBSLS")
        
        # Ringkasan statistik
        only_msls = df_diff[df_diff['status'] == 'hanya_msls']
        only_petasls = df_diff[df_diff['status'] == 'hanya_petasls']
        both = df_diff[df_diff['status'] == 'keduanya']
        
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            with st.container(border=True):
                st.metric("Total Data", len(df_diff))
        with col2:
            with st.container(border=True):
                st.metric("Hanya ada di MSLS", len(only_msls))
        with col3:
            with st.container(border=True):
                st.metric("Hanya ada di PETASLS", len(only_petasls))
        with col4:
            with st.container(border=True):
                st.metric("Data Cocok", len(both))
        with col5:
            with st.container(border=True):
                st.metric("Total Duplikat", len(msls_duplicates) + len(petasls_duplicates))
    
    # Detail duplikasi
    with st.container(border=True):
        st.subheader("Detail Duplikasi IDSUBSLS")
        col1, col2 = st.columns(2)
        
        with col1:
            with st.container(border=True):
                show_duplicate_table(msls_duplicates, "MSLS")
        
        with col2:
            with st.container(border=True):
                show_duplicate_table(petasls_duplicates, "PETASLS")
    
    # Detail hasil perbandingan
    with st.container(border=True):
        st.subheader("Detail Hasil Perbandingan")
        col1, col2 = st.columns(2)
        
        with col1:
            with st.container(border=True):
                st.subheader("Data ada di MSLS tapi tidak ada di PETASLS")
                st.dataframe(only_msls[['idsubsls']], use_container_width=True)
        
        with col2:
            with st.container(border=True):
                st.subheader("Data ada di PETASLS tapi tidak ada di MSLS")
                st.dataframe(only_petasls[['idsubsls']], use_container_width=True)
    
    # Perbandingan nama SUBSLS
    with st.container(border=True):
        st.subheader("Perbandingan Nama SUBSLS (nmsls)")
        
        if len(nmsls_diff) > 0:
            # Filter data yang tidak cocok
            not_match = nmsls_diff[nmsls_diff['nmsls_match'] == False]
            
            if len(not_match) > 0:
                st.error(f"❌ Ditemukan {len(not_match)} data dengan nama SUBSLS yang berbeda untuk ID yang sama")
                
                # Tampilkan tabel perbandingan
                comparison_df = not_match[['idsubsls', 'nmsls_msls', 'nmsls_petasls']].copy()
                comparison_df.columns = ['ID SUBSLS', 'Nama SUBSLS (MSLS)', 'Nama SUBSLS (PETASLS)']
                st.dataframe(comparison_df, use_container_width=True)
                
                # Tambahkan opsi untuk download
                csv = comparison_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="Download Data Tidak Cocok",
                    data=csv,
                    file_name='nmsubs_tidak_cocok.csv',
                    mime='text/csv'
                )
            else:
                st.success("✅ Semua nama SUBSLS cocok untuk ID yang sama")
        else:
            st.info("Tidak ada data yang dapat dibandingkan (tidak ada ID yang sama di kedua file)")

# Main app
def main():
    st.title("Aplikasi Cek SUBSLS")
    st.markdown("Unggah file Excel dan GeoJSON untuk membandingkan data SUBSLS")
    
    # Navigasi kembali
    if st.sidebar.button("← Kembali ke Halaman Utama"):
        st.switch_page("main.py")
    
    # Upload file Excel (MSLS)
    with st.container(border=True):
        st.header("Unggah File Excel (Master SUBSLS)")
        msls_file = st.file_uploader(
            "Pilih file Excel", 
            type=['xlsx', 'xls'],
            key="msls_uploader"
        )
        
        if msls_file is not None:
            try:
                # Simpan file sementara
                file_path = UPLOAD_DIR / f"msls_{uuid.uuid4()}.xlsx"
                with open(file_path, "wb") as buffer:
                    buffer.write(msls_file.getvalue())
                
                # Baca Excel
                df_msls = pd.read_excel(file_path)
                
                # Tampilkan informasi kolom yang tersedia
                st.write("Kolom yang tersedia dalam file MSLS:")
                st.write(df_msls.columns.tolist())
                
                # Proses pembuatan kolom idsubsls jika belum ada
                if 'idsubsls' not in df_msls.columns:
                    with st.expander("Proses Pembuatan kolom IDSUBSLS", expanded=True):
                        st.write("Membuat kolom 'idsubsls' dari penggabungan kolom: kdprov, kdkab, kdkec, kddesa, kdsls, dan kdsubsls")
                        st.write("Format: kdprov(2) + kdkab(2) + kdkec(3) + kddesa(3) + kdsls(4) + kdsubsls(2)")
                        
                        # Cek apakah kolom yang diperlukan ada
                        required_cols = ['kdprov', 'kdkab', 'kdkec', 'kddesa', 'kdsls', 'kdsubsls']
                        missing_cols = [col for col in required_cols if col not in df_msls.columns]
                        
                        if missing_cols:
                            st.error(f"❌ Kolom yang diperlukan tidak ditemukan: {', '.join(missing_cols)}")
                            st.stop()
                        
                        # Tampilkan contoh data sebelum penggabungan
                        st.write("Contoh data sebelum penggabungan:")
                        st.dataframe(df_msls[required_cols].head(5))
                        
                        # Buat kolom idsubsls dengan format string
                        df_msls['idsubsls'] = (
                            df_msls['kdprov'].astype(str).str.zfill(2) + 
                            df_msls['kdkab'].astype(str).str.zfill(2) + 
                            df_msls['kdkec'].astype(str).str.zfill(3) + 
                            df_msls['kddesa'].astype(str).str.zfill(3) + 
                            df_msls['kdsls'].astype(str).str.zfill(4) + 
                            df_msls['kdsubsls'].astype(str).str.zfill(2)  # Diperbaiki: 2 digit bukan 4 digit
                        )
                        
                        # Tampilkan contoh data setelah penggabungan
                        st.write("Contoh data setelah pembuatan idsubsls:")
                        st.dataframe(df_msls[required_cols + ['idsubsls']].head(5))
                else:
                    st.info("Kolom 'idsubsls' sudah ada dalam file")
                
                # Urutkan berdasarkan idsubsls
                df_msls = df_msls.sort_values('idsubsls')
                
                # Simpan sebagai Parquet
                parquet_path = UPLOAD_DIR / "msls_subs.parquet"
                df_msls.to_parquet(parquet_path)
                
                # Hapus file sementara
                file_path.unlink()
                
                # Cek duplikasi
                duplicates = df_msls[df_msls.duplicated(subset=['idsubsls'], keep=False)]
                duplicate_count = len(duplicates)
                duplicate_summary = duplicates.groupby('idsubsls').size().reset_index(name='count')
                
                # Tampilkan hasil
                show_duplicate_alert(duplicate_count, "MSLS")
                show_data_table(df_msls, "Data MSLS", highlight_duplicates=True, columns=['idsubsls', 'nmsls'])
                show_duplicate_table(duplicate_summary, "MSLS")
                
                st.success("✅ File MSLS berhasil diunggah dan diproses!")
                
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
    
    st.subheader("", divider='orange')
    
    # Upload file GeoJSON (PETASLS)
    with st.container(border=True):
        st.header("Unggah File GeoJSON (PETASUBSLS)")
        petasls_file = st.file_uploader(
            "Pilih file GeoJSON", 
            type=['geojson'],
            key="petasls_uploader"
        )
        
        if petasls_file is not None:
            try:
                # Simpan file sementara
                file_path = UPLOAD_DIR / f"petasls_{uuid.uuid4()}.geojson"
                with open(file_path, "wb") as buffer:
                    buffer.write(petasls_file.getvalue())
                
                # Baca GeoJSON
                gdf_petasls = gpd.read_file(file_path)
                
                # Tampilkan informasi kolom yang tersedia
                st.write("Kolom yang tersedia dalam file PETASLS:")
                st.write(gdf_petasls.columns.tolist())
                
                # Proses pembuatan kolom idsubsls jika belum ada
                if 'idsubsls' not in gdf_petasls.columns:
                    with st.expander("Proses Pembuatan kolom IDSUBSLS", expanded=True):
                        st.write("Membuat kolom 'idsubsls' dari penggabungan kolom: kdprov, kdkab, kdkec, kddesa, kdsls, dan kdsubsls")
                        st.write("Format: kdprov(2) + kdkab(2) + kdkec(3) + kddesa(3) + kdsls(4) + kdsubsls(2)")
                        
                        # Cek apakah kolom yang diperlukan ada
                        required_cols = ['kdprov', 'kdkab', 'kdkec', 'kddesa', 'kdsls', 'kdsubsls']
                        missing_cols = [col for col in required_cols if col not in gdf_petasls.columns]
                        
                        if missing_cols:
                            st.error(f"❌ Kolom yang diperlukan tidak ditemukan: {', '.join(missing_cols)}")
                            st.stop()
                        
                        # Tampilkan contoh data sebelum penggabungan
                        st.write("Contoh data sebelum penggabungan:")
                        st.dataframe(gdf_petasls[required_cols].head(5))
                        
                        # Buat kolom idsubsls dengan format string
                        gdf_petasls['idsubsls'] = (
                            gdf_petasls['kdprov'].astype(str).str.zfill(2) + 
                            gdf_petasls['kdkab'].astype(str).str.zfill(2) + 
                            gdf_petasls['kdkec'].astype(str).str.zfill(3) + 
                            gdf_petasls['kddesa'].astype(str).str.zfill(3) + 
                            gdf_petasls['kdsls'].astype(str).str.zfill(4) + 
                            gdf_petasls['kdsubsls'].astype(str).str.zfill(2)  # Diperbaiki: 2 digit bukan 4 digit
                        )
                        
                        # Tampilkan contoh data setelah penggabungan
                        st.write("Contoh data setelah pembuatan idsubsls:")
                        st.dataframe(gdf_petasls[required_cols + ['idsubsls']].head(5))
                else:
                    st.info("Kolom 'idsubsls' sudah ada dalam file")
                
                # Urutkan berdasarkan idsubsls
                gdf_petasls = gdf_petasls.sort_values('idsubsls')
                
                # Simpan sebagai Parquet
                parquet_path = UPLOAD_DIR / "petasls_subs.parquet"
                gdf_petasls.to_parquet(parquet_path)
                
                # Hapus file sementara
                file_path.unlink()
                
                # Cek duplikasi
                duplicates = gdf_petasls[gdf_petasls.duplicated(subset=['idsubsls'], keep=False)]
                duplicate_count = len(duplicates)
                duplicate_summary = duplicates.groupby('idsubsls').size().reset_index(name='count')
                
                # Tampilkan hasil
                show_duplicate_alert(duplicate_count, "PETASLS")
                show_data_table(gdf_petasls, "Data PETASLS", highlight_duplicates=True, columns=['idsubsls', 'nmsls'])
                show_duplicate_table(duplicate_summary, "PETASLS")
                
                st.success("✅ File PETASLS berhasil diunggah dan diproses!")
                
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
    
    # Tombol untuk membandingkan data
    msls_path = UPLOAD_DIR / "msls_subs.parquet"
    petasls_path = UPLOAD_DIR / "petasls_subs.parquet"
    
    st.subheader("", divider='orange')
    
    if msls_path.exists() and petasls_path.exists():
        st.header("Bandingkan Data Pada Kedua File")
        if st.button("BANDINGKAN DATA", type="primary"):
            with st.spinner("Memproses perbandingan data..."):
                try:
                    # Baca data Parquet
                    df_msls = pd.read_parquet(msls_path)
                    df_petasls = pd.read_parquet(petasls_path)
                    
                    # Cek duplikasi
                    msls_duplicates = df_msls[df_msls.duplicated(subset=['idsubsls'], keep=False)]
                    msls_duplicate_summary = msls_duplicates.groupby('idsubsls').size().reset_index(name='count')
                    
                    petasls_duplicates = df_petasls[df_petasls.duplicated(subset=['idsubsls'], keep=False)]
                    petasls_duplicate_summary = petasls_duplicates.groupby('idsubsls').size().reset_index(name='count')
                    
                    # Bandingkan data
                    set_msls = set(df_msls['idsubsls'])
                    set_petasls = set(df_petasls['idsubsls'])
                    
                    # Buat dataframe perbandingan
                    only_msls = list(set_msls - set_petasls)
                    only_petasls = list(set_petasls - set_msls)
                    both = list(set_msls & set_petasls)
                    
                    diff_data = []
                    diff_data.extend([(id, 'hanya_msls') for id in only_msls])
                    diff_data.extend([(id, 'hanya_petasls') for id in only_petasls])
                    diff_data.extend([(id, 'keduanya') for id in both])
                    
                    df_diff = pd.DataFrame(diff_data, columns=['idsubsls', 'status'])
                    
                    # Bandingkan nama SUBSLS (nmsls) untuk ID yang sama
                    nmsls_diff = pd.DataFrame()
                    
                    if both:
                        # Ambil data yang memiliki ID sama
                        msls_common = df_msls[df_msls['idsubsls'].isin(both)][['idsubsls', 'nmsls']]
                        petasls_common = df_petasls[df_petasls['idsubsls'].isin(both)][['idsubsls', 'nmsls']]
                        
                        # Rename kolom untuk membedakan
                        msls_common.columns = ['idsubsls', 'nmsls_msls']
                        petasls_common.columns = ['idsubsls', 'nmsls_petasls']
                        
                        # Merge berdasarkan idsubsls
                        nmsls_diff = pd.merge(msls_common, petasls_common, on='idsubsls', how='inner')
                        
                        # Bandingkan nama SUBSLS
                        nmsls_diff['nmsls_match'] = nmsls_diff['nmsls_msls'] == nmsls_diff['nmsls_petasls']
                        
                        # Handle case insensitive comparison
                        nmsls_diff['nmsls_match_case'] = nmsls_diff['nmsls_msls'].str.lower() == nmsls_diff['nmsls_petasls'].str.lower()
                    
                    # Tampilkan hasil perbandingan
                    show_comparison_result(df_diff, msls_duplicate_summary, petasls_duplicate_summary, nmsls_diff)
                    
                except Exception as e:
                    st.error(f"❌ Error dalam perbandingan: {str(e)}")

if __name__ == "__main__":
    main()