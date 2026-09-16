import streamlit as st
import pandas as pd
import geopandas as gpd
from pathlib import Path
import uuid
import time

# Konfigurasi halaman
st.set_page_config(
    page_title="CEK IDSLS",
    page_icon="📊",
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
def show_data_table(df, title, max_rows=10, highlight_duplicates=False):
    st.subheader(f"{title} ({len(df)} baris)")
    
    # Deteksi duplikat jika diminta
    if highlight_duplicates and 'idsls' in df.columns:
        duplicates = df[df.duplicated(subset=['idsls'], keep=False)]
        duplicate_ids = duplicates['idsls'].tolist()
        
        # Highlight baris duplikat
        def highlight_dup(row):
            if 'idsls' in row and str(row['idsls']) in duplicate_ids:
                return ['background-color: yellow'] * len(row)
            return [''] * len(row)
        
        styled_df = df.head(max_rows).style.apply(highlight_dup, axis=1)
        st.dataframe(styled_df, use_container_width=True)
    else:
        st.dataframe(df.head(max_rows), use_container_width=True)

# Fungsi untuk menampilkan tabel duplikat
def show_duplicate_table(duplicates, source):
    if len(duplicates) > 0:
        st.subheader(f"Detail Duplikat di {source}")
        st.dataframe(duplicates, use_container_width=True)

# Fungsi untuk menampilkan hasil perbandingan
def show_comparison_result(df_diff, msls_duplicates, petasls_duplicates, nmsls_diff):
    with st.container(border=True):
        st.header("Hasil Pengecekan dan Perbandingan")
        
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
        st.subheader("Detail Duplikasi IDSLS")
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
                st.dataframe(only_msls[['idsls']], use_container_width=True)
        
        with col2:
            with st.container(border=True):
                st.subheader("Data ada di PETASLS tapi tidak ada di MSLS")
                st.dataframe(only_petasls[['idsls']], use_container_width=True)
    
    # Perbandingan nama SLS
    with st.container(border=True):
        st.subheader("Perbandingan Nama SLS (nmsls)")
        
        if len(nmsls_diff) > 0:
            # Filter data yang tidak cocok
            not_match = nmsls_diff[nmsls_diff['nmsls_match'] == False]
            
            if len(not_match) > 0:
                st.error(f"❌ Ditemukan {len(not_match)} data dengan nama SLS yang berbeda untuk ID yang sama")
                
                # Tampilkan tabel perbandingan
                comparison_df = not_match[['idsls', 'nmsls_msls', 'nmsls_petasls']].copy()
                comparison_df.columns = ['ID SLS', 'Nama SLS (MSLS)', 'Nama SLS (PETASLS)']
                st.dataframe(comparison_df, use_container_width=True)
                
                # Tambahkan opsi untuk download
                csv = comparison_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="Download Data Tidak Cocok",
                    data=csv,
                    file_name='nmsls_tidak_cocok.csv',
                    mime='text/csv'
                )
            else:
                st.success("✅ Semua nama SLS cocok untuk ID yang sama")
        else:
            st.info("Tidak ada data yang dapat dibandingkan (tidak ada ID yang sama di kedua file)")

# Main app
def main():
    with st.container(border=True):
        with st.container(border=True):
            st.title("Aplikasi Cek IDSLS")
            st.markdown("Unggah file Excel dan GeoJSON untuk membandingkan data")
    
    # Navigasi ke halaman lain
    st.sidebar.title("Navigasi")
    page = st.sidebar.radio("Pilih Halaman:", ["Cek Data", "Cek Overlap", "Cek Gap"])
    
    if page == "Cek Overlap":
        st.switch_page("pages/cek_overlap.py")
    elif page == "Cek Gap":
        st.switch_page("pages/cek_gap.py")
    
    # Upload file Excel (MSLS)
    with st.container(border=True):
        st.header("Unggah File Excel (Master SLS)")
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
                
                # Proses pembuatan kolom idsls
                with st.expander("Proses Pembuatan kolom IDSLS", expanded=False):
                    st.write("Membuat kolom 'idsls' dari penggabungan kolom: kdprov, kdkab, kdkec, kddesa, dan kdsls")
                    
                    # Cek apakah kolom yang diperlukan ada
                    required_cols = ['kdprov', 'kdkab', 'kdkec', 'kddesa', 'kdsls']
                    missing_cols = [col for col in required_cols if col not in df_msls.columns]
                    
                    if missing_cols:
                        st.error(f"❌ Kolom yang diperlukan tidak ditemukan: {', '.join(missing_cols)}")
                        st.stop()
                    
                    # Buat kolom idsls dengan format string
                    df_msls['idsls'] = (
                        df_msls['kdprov'].astype(str).str.zfill(2) + 
                        df_msls['kdkab'].astype(str).str.zfill(2) + 
                        df_msls['kdkec'].astype(str).str.zfill(3) + 
                        df_msls['kddesa'].astype(str).str.zfill(3) + 
                        df_msls['kdsls'].astype(str).str.zfill(4)
                    )
                
                # Urutkan berdasarkan idsls
                df_msls = df_msls.sort_values('idsls')
                
                # Simpan sebagai Parquet
                parquet_path = UPLOAD_DIR / "msls.parquet"
                df_msls.to_parquet(parquet_path)
                
                # Hapus file sementara
                file_path.unlink()
                
                # Cek duplikasi
                duplicates = df_msls[df_msls.duplicated(subset=['idsls'], keep=False)]
                duplicate_count = len(duplicates)
                duplicate_summary = duplicates.groupby('idsls').size().reset_index(name='count')
                
                # Tampilkan hasil
                show_duplicate_alert(duplicate_count, "MSLS")
                show_data_table(df_msls, "Data MSLS", highlight_duplicates=True)
                show_duplicate_table(duplicate_summary, "MSLS")
                
                st.success("✅ File MSLS berhasil diunggah dan diproses!")
                st.warning("Duplikasi pada MSLS bisa terjadi karena File MSLS mengandung kolom IDSUBSLS")
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
    
    st.subheader("", divider='orange')
    
    # Upload file GeoJSON (PETASLS)
    with st.container(border=True):
        st.header("Unggah File GeoJSON (PETASLS)")
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
                
                # Untuk GeoJSON, asumsikan kolom idsls sudah ada
                if 'idsls' not in gdf_petasls.columns:
                    st.error("❌ Kolom 'idsls' tidak ditemukan di file GeoJSON")
                    st.stop()
                
                # Urutkan berdasarkan idsls
                gdf_petasls = gdf_petasls.sort_values('idsls')
                
                # Simpan sebagai Parquet
                parquet_path = UPLOAD_DIR / "petasls.parquet"
                gdf_petasls.to_parquet(parquet_path)
                
                # Hapus file sementara
                file_path.unlink()
                
                # Cek duplikasi
                duplicates = gdf_petasls[gdf_petasls.duplicated(subset=['idsls'], keep=False)]
                duplicate_count = len(duplicates)
                duplicate_summary = duplicates.groupby('idsls').size().reset_index(name='count')
                
                # Tampilkan hasil
                show_duplicate_alert(duplicate_count, "PETASLS")
                show_data_table(gdf_petasls, "Data PETASLS", highlight_duplicates=True)
                show_duplicate_table(duplicate_summary, "PETASLS")
                
                st.success("✅ File PETASLS berhasil diunggah dan diproses!")
                
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
    
    # Tombol untuk membandingkan data
    msls_path = UPLOAD_DIR / "msls.parquet"
    petasls_path = UPLOAD_DIR / "petasls.parquet"
    
    st.subheader("", divider='orange')
    
    if msls_path.exists() and petasls_path.exists():
        st.header("Bandingkan Data Pada Kedua File")
        if st.button("C E K I D O T", type="primary"):
            with st.spinner("Memproses perbandingan data..."):
                try:
                    # Baca data Parquet
                    df_msls = pd.read_parquet(msls_path)
                    df_petasls = pd.read_parquet(petasls_path)
                    
                    # Cek duplikasi
                    msls_duplicates = df_msls[df_msls.duplicated(subset=['idsls'], keep=False)]
                    msls_duplicate_summary = msls_duplicates.groupby('idsls').size().reset_index(name='count')
                    
                    petasls_duplicates = df_petasls[df_petasls.duplicated(subset=['idsls'], keep=False)]
                    petasls_duplicate_summary = petasls_duplicates.groupby('idsls').size().reset_index(name='count')
                    
                    # Bandingkan data
                    set_msls = set(df_msls['idsls'])
                    set_petasls = set(df_petasls['idsls'])
                    
                    # Buat dataframe perbandingan
                    only_msls = list(set_msls - set_petasls)
                    only_petasls = list(set_petasls - set_msls)
                    both = list(set_msls & set_petasls)
                    
                    diff_data = []
                    diff_data.extend([(id, 'hanya_msls') for id in only_msls])
                    diff_data.extend([(id, 'hanya_petasls') for id in only_petasls])
                    diff_data.extend([(id, 'keduanya') for id in both])
                    
                    df_diff = pd.DataFrame(diff_data, columns=['idsls', 'status'])
                    
                    # Bandingkan nama SLS (nmsls) untuk ID yang sama
                    nmsls_diff = pd.DataFrame()
                    
                    if both:
                        # Ambil data yang memiliki ID sama
                        msls_common = df_msls[df_msls['idsls'].isin(both)][['idsls', 'nmsls']]
                        petasls_common = df_petasls[df_petasls['idsls'].isin(both)][['idsls', 'nmsls']]
                        
                        # Rename kolom untuk membedakan
                        msls_common.columns = ['idsls', 'nmsls_msls']
                        petasls_common.columns = ['idsls', 'nmsls_petasls']
                        
                        # Merge berdasarkan idsls
                        nmsls_diff = pd.merge(msls_common, petasls_common, on='idsls', how='inner')
                        
                        # Bandingkan nama SLS
                        nmsls_diff['nmsls_match'] = nmsls_diff['nmsls_msls'] == nmsls_diff['nmsls_petasls']
                    
                    # Tampilkan hasil perbandingan
                    show_comparison_result(df_diff, msls_duplicate_summary, petasls_duplicate_summary, nmsls_diff)
                    
                except Exception as e:
                    st.error(f"❌ Error dalam perbandingan: {str(e)}")

if __name__ == "__main__":
    main()