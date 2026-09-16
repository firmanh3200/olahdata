import streamlit as st
import pandas as pd
import geopandas as gpd
from pathlib import Path
import time
from shapely.geometry import Polygon

# Konfigurasi halaman
st.set_page_config(
    page_title="Cek Overlap",
    page_icon="🔄",
    layout="wide"
)

# Direktori penyimpanan file
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# Fungsi untuk mengecek overlap
def check_overlaps(gdf):
    overlaps = []
    
    # Buat salinan geometri untuk perbandingan
    geometries = gdf.geometry.tolist()
    ids = gdf.idsls.tolist()
    
    # Cek setiap pasangan polygon
    for i in range(len(geometries)):
        for j in range(i+1, len(geometries)):
            if geometries[i].intersects(geometries[j]):
                # Hitung area overlap
                overlap_area = geometries[i].intersection(geometries[j]).area
                
                # Hitung persentase overlap terhadap area masing-masing polygon
                area_i = geometries[i].area
                area_j = geometries[j].area
                
                if area_i > 0 and area_j > 0:
                    percent_i = (overlap_area / area_i) * 100
                    percent_j = (overlap_area / area_j) * 100
                    
                    overlaps.append({
                        'idsls_1': ids[i],
                        'idsls_2': ids[j],
                        'overlap_area': overlap_area,
                        'percent_overlap_1': percent_i,
                        'percent_overlap_2': percent_j
                    })
    
    return pd.DataFrame(overlaps)

# Main app
def main():
    st.title("Cek Overlap Polygon")
    st.markdown("Halaman untuk memeriksa tumpang tindih (overlap) antar polygon")
    
    # Navigasi kembali
    if st.sidebar.button("← Kembali ke Halaman Utama"):
        st.switch_page("main.py")
    
    # Cek apakah file GeoJSON sudah ada
    petasls_path = UPLOAD_DIR / "petasls.parquet"
    
    if not petasls_path.exists():
        st.error("❌ File GeoJSON belum diunggah. Silakan unggah file terlebih dahulu di halaman utama.")
        if st.button("Ke Halaman Utama"):
            st.switch_page("main.py")
        return
    
    # Baca data GeoJSON
    try:
        gdf_petasls = gpd.read_parquet(petasls_path)
        st.success(f"✅ Berhasil memuat {len(gdf_petasls)} polygon dari file GeoJSON")
    except Exception as e:
        st.error(f"❌ Error membaca file: {str(e)}")
        return
    
    # Tambahkan parameter untuk pengecekan
    st.subheader("Parameter Pengecekan")
    col1, col2 = st.columns(2)
    
    with col1:
        min_overlap_percent = st.slider(
            "Persentase Overlap Minimum (%)",
            min_value=0.0,
            max_value=100.0,
            value=1.0,
            step=0.1
        )
    
    with col2:
        max_results = st.number_input(
            "Maksimum Hasil yang Ditampilkan",
            min_value=10,
            max_value=1000,
            value=100,
            step=10
        )
    
    # Tombol untuk memulai pengecekan
    if st.button("Mulai Pengecekan Overlap", type="primary"):
        with st.spinner("Memeriksa overlap polygon..."):
            try:
                # Lakukan pengecekan overlap
                overlaps = check_overlaps(gdf_petasls)
                
                # Filter berdasarkan persentase minimum
                if not overlaps.empty:
                    overlaps = overlaps[
                        (overlaps['percent_overlap_1'] >= min_overlap_percent) | 
                        (overlaps['percent_overlap_2'] >= min_overlap_percent)
                    ]
                
                # Tampilkan hasil
                st.subheader("Hasil Pengecekan Overlap")
                
                if len(overlaps) > 0:
                    st.error(f"❌ Ditemukan {len(overlaps)} pasangan polygon yang tumpang tindih")
                    
                    # Urutkan berdasarkan area overlap terbesar
                    overlaps = overlaps.sort_values('overlap_area', ascending=False)
                    
                    # Batasi jumlah hasil
                    display_overlaps = overlaps.head(max_results)
                    
                    # Tampilkan tabel
                    st.dataframe(display_overlaps, use_container_width=True)
                    
                    # Tambahkan opsi untuk download
                    csv = display_overlaps.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="Download Data Overlap",
                        data=csv,
                        file_name='overlap_polygon.csv',
                        mime='text/csv'
                    )
                    
                    # Tampilkan statistik
                    st.subheader("Statistik Overlap")
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.metric("Total Overlap", len(overlaps))
                    with col2:
                        avg_overlap = overlaps['overlap_area'].mean()
                        st.metric("Rata-rata Area", f"{avg_overlap:.2f}")
                    with col3:
                        max_overlap = overlaps['percent_overlap_1'].max()
                        st.metric("Persentase Maks", f"{max_overlap:.2f}%")
                    with col4:
                        total_area = overlaps['overlap_area'].sum()
                        st.metric("Total Area Overlap", f"{total_area:.2f}")
                    
                    # Visualisasi distribusi
                    st.subheader("Distribusi Persentase Overlap")
                    chart_data = overlaps[['percent_overlap_1', 'percent_overlap_2']].values.flatten()
                    chart_data = chart_data[chart_data > 0]  # Hapus nilai 0
                    
                    st.bar_chart(chart_data)
                    
                else:
                    st.success("✅ Tidak ditemukan polygon yang tumpang tindih")
                
            except Exception as e:
                st.error(f"❌ Error dalam pengecekan: {str(e)}")

if __name__ == "__main__":
    main()