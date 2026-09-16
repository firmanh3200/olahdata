import streamlit as st
import pandas as pd
import geopandas as gpd
from pathlib import Path
import uuid
import time

# Konfigurasi halaman
st.set_page_config(
    page_title="Bandingkan GeoJSON",
    page_icon="🗺️",
    layout="wide"
)

# Direktori penyimpanan file
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# Fungsi untuk menampilkan tabel data
def show_data_table(df, title, max_rows=10):
    st.subheader(f"{title} ({len(df)} baris)")
    st.dataframe(df.head(max_rows), use_container_width=True)

# Fungsi untuk menampilkan hasil perbandingan
def show_comparison_result(df_diff, key_column, compare_columns, before_name, after_name):
    with st.container(border=True):
        st.header("Hasil Perbandingan GeoJSON")
        
        # Ringkasan statistik
        only_before = df_diff[df_diff['status'] == f'hanya_{before_name}']
        only_after = df_diff[df_diff['status'] == f'hanya_{after_name}']
        both = df_diff[df_diff['status'] == 'keduanya']
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            with st.container(border=True):
                st.metric("Total Data", len(df_diff))
        with col2:
            with st.container(border=True):
                st.metric(f"Hanya ada di {before_name}", len(only_before))
        with col3:
            with st.container(border=True):
                st.metric(f"Hanya ada di {after_name}", len(only_after))
    
    # Detail hasil perbandingan
    with st.container(border=True):
        st.subheader("Detail Hasil Perbandingan")
        col1, col2 = st.columns(2)
        
        with col1:
            with st.container(border=True):
                st.subheader(f"Data ada di {before_name} tapi tidak ada di {after_name}")
                st.dataframe(only_before[[key_column]], use_container_width=True)
        
        with col2:
            with st.container(border=True):
                st.subheader(f"Data ada di {after_name} tapi tidak ada di {before_name}")
                st.dataframe(only_after[[key_column]], use_container_width=True)
    
    # Perbandingan nilai kolom
    if len(compare_columns) > 0 and len(both) > 0:
        with st.container(border=True):
            st.subheader("Perbandingan Nilai Kolom")
            
            # Baca data lengkap untuk perbandingan nilai
            before_path = UPLOAD_DIR / f"{before_name.lower()}_geojson.parquet"
            after_path = UPLOAD_DIR / f"{after_name.lower()}_geojson.parquet"
            
            df_before = gpd.read_parquet(before_path)
            df_after = gpd.read_parquet(after_path)
            
            # Filter data yang ada di kedua file
            before_common = df_before[df_before[key_column].isin(both[key_column])]
            after_common = df_after[df_after[key_column].isin(both[key_column])]
            
            # Untuk setiap kolom yang ingin dibandingkan
            for col in compare_columns:
                if col in before_common.columns and col in after_common.columns:
                    st.write(f"#### Perbandingan Kolom: {col}")
                    
                    # Merge data untuk perbandingan
                    compare_df = pd.merge(
                        before_common[[key_column, col]], 
                        after_common[[key_column, col]], 
                        on=key_column, 
                        suffixes=(f'_{before_name}', f'_{after_name}')
                    )
                    
                    # Tambahkan kolom status perbandingan
                    compare_df[f'{col}_match'] = compare_df[f'{col}_{before_name}'] == compare_df[f'{col}_{after_name}']
                    
                    # Filter data yang tidak cocok
                    not_match = compare_df[compare_df[f'{col}_match'] == False]
                    
                    if len(not_match) > 0:
                        st.error(f"❌ Ditemukan {len(not_match)} data dengan nilai {col} yang berbeda")
                        
                        # Tampilkan tabel perbandingan
                        display_cols = [key_column, f'{col}_{before_name}', f'{col}_{after_name}']
                        display_df = not_match[display_cols].copy()
                        display_df.columns = [key_column, f"{col} ({before_name})", f"{col} ({after_name})"]
                        st.dataframe(display_df, use_container_width=True)
                        
                        # Tambahkan opsi untuk download
                        csv = display_df.to_csv(index=False).encode('utf-8')
                        st.download_button(
                            label=f"Download Data {col} Tidak Cocok",
                            data=csv,
                            file_name=f'{col}_tidak_cocok.csv',
                            mime='text/csv',
                            key=f'download_{col}'
                        )
                    else:
                        st.success(f"✅ Semua nilai {col} cocok")

# Main app
def main():
    st.title("Bandingkan Dua File GeoJSON")
    st.markdown("Bandingkan file GeoJSON awal dengan file GeoJSON akhir")
    
    # Navigasi kembali
    if st.sidebar.button("← Kembali ke Halaman Utama"):
        st.switch_page("main.py")
    
    # Upload file GeoJSON awal
    with st.container(border=True):
        st.header("Unggah File GeoJSON Awal")
        before_file = st.file_uploader(
            "Pilih file GeoJSON awal", 
            type=['geojson'],
            key="before_uploader"
        )
        
        if before_file is not None:
            try:
                # Simpan file sementara
                file_path = UPLOAD_DIR / f"before_{uuid.uuid4()}.geojson"
                with open(file_path, "wb") as buffer:
                    buffer.write(before_file.getvalue())
                
                # Baca GeoJSON
                gdf_before = gpd.read_file(file_path)
                
                # Tampilkan informasi kolom yang tersedia
                st.write("Kolom yang tersedia dalam file GeoJSON awal:")
                st.write(gdf_before.columns.tolist())
                
                # Simpan sebagai Parquet
                parquet_path = UPLOAD_DIR / "before_geojson.parquet"
                gdf_before.to_parquet(parquet_path)
                
                # Hapus file sementara
                file_path.unlink()
                
                # Tampilkan preview data
                show_data_table(gdf_before, "Data GeoJSON Awal")
                
                st.success("✅ File GeoJSON awal berhasil diunggah dan diproses!")
                
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
    
    st.subheader("", divider='orange')
    
    # Upload file GeoJSON akhir
    with st.container(border=True):
        st.header("Unggah File GeoJSON Akhir")
        after_file = st.file_uploader(
            "Pilih file GeoJSON akhir", 
            type=['geojson'],
            key="after_uploader"
        )
        
        if after_file is not None:
            try:
                # Simpan file sementara
                file_path = UPLOAD_DIR / f"after_{uuid.uuid4()}.geojson"
                with open(file_path, "wb") as buffer:
                    buffer.write(after_file.getvalue())
                
                # Baca GeoJSON
                gdf_after = gpd.read_file(file_path)
                
                # Tampilkan informasi kolom yang tersedia
                st.write("Kolom yang tersedia dalam file GeoJSON akhir:")
                st.write(gdf_after.columns.tolist())
                
                # Simpan sebagai Parquet
                parquet_path = UPLOAD_DIR / "after_geojson.parquet"
                gdf_after.to_parquet(parquet_path)
                
                # Hapus file sementara
                file_path.unlink()
                
                # Tampilkan preview data
                show_data_table(gdf_after, "Data GeoJSON Akhir")
                
                st.success("✅ File GeoJSON akhir berhasil diunggah dan diproses!")
                
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
    
    # Konfigurasi perbandingan
    before_path = UPLOAD_DIR / "before_geojson.parquet"
    after_path = UPLOAD_DIR / "after_geojson.parquet"
    
    st.subheader("", divider='orange')
    
    if before_path.exists() and after_path.exists():
        st.header("Konfigurasi Perbandingan")
        
        # Baca data untuk mendapatkan daftar kolom
        df_before = gpd.read_parquet(before_path)
        df_after = gpd.read_parquet(after_path)
        
        # Pilih kolom kunci
        key_column = st.selectbox(
            "Pilih Kolom Kunci (penghubung):",
            options=list(set(df_before.columns) & set(df_after.columns)),
            index=0
        )
        
        # Pilih kolom yang ingin dibandingkan
        available_columns = list(set(df_before.columns) & set(df_after.columns))
        available_columns.remove(key_column)  # Hapus kolom kunci dari pilihan
        
        compare_columns = st.multiselect(
            "Pilih Kolom yang Ingin Dibandingkan:",
            options=available_columns,
            default=available_columns[:3] if len(available_columns) >= 3 else available_columns
        )
        
        # Tombol untuk membandingkan data
        if st.button("BANDINGKAN DATA", type="primary"):
            with st.spinner("Memproses perbandingan data..."):
                try:
                    # Baca data Parquet
                    df_before = gpd.read_parquet(before_path)
                    df_after = gpd.read_parquet(after_path)
                    
                    # Bandingkan data berdasarkan kolom kunci
                    set_before = set(df_before[key_column])
                    set_after = set(df_after[key_column])
                    
                    # Buat dataframe perbandingan
                    only_before = list(set_before - set_after)
                    only_after = list(set_after - set_before)
                    both = list(set_before & set_after)
                    
                    diff_data = []
                    diff_data.extend([(id, f'hanya_before') for id in only_before])
                    diff_data.extend([(id, f'hanya_after') for id in only_after])
                    diff_data.extend([(id, 'keduanya') for id in both])
                    
                    df_diff = pd.DataFrame(diff_data, columns=[key_column, 'status'])
                    
                    # Tampilkan hasil perbandingan
                    show_comparison_result(df_diff, key_column, compare_columns, "before", "after")
                    
                except Exception as e:
                    st.error(f"❌ Error dalam perbandingan: {str(e)}")

if __name__ == "__main__":
    main()