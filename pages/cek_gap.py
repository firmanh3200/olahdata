import streamlit as st
import pandas as pd
import geopandas as gpd
from pathlib import Path
import time
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union
import numpy as np

# Konfigurasi halaman
st.set_page_config(
    page_title="Cek Gap",
    page_icon="🔍",
    layout="wide"
)

# Direktori penyimpanan file
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# Fungsi untuk mengecek gap
def check_gaps(gdf, tolerance=0.0001):
    gaps = []
    
    # Dapatkan semua geometri
    geometries = gdf.geometry.tolist()
    ids = gdf.idsls.tolist()
    
    # Pendekatan 1: Periksa setiap polygon apakah memiliki tetangga
    for i, geom in enumerate(geometries):
        has_neighbor = False
        for j, other_geom in enumerate(geometries):
            if i != j and geom.touches(other_geom):
                has_neighbor = True
                break
        
        if not has_neighbor:
            gaps.append({
                'idsls': ids[i],
                'type': 'Isolated Polygon',
                'distance': 'N/A',
                'area': geom.area
            })
    
    # Pendekatan 2: Periksa jarak antar polygon yang tidak bersebelahan
    for i in range(len(geometries)):
        for j in range(i+1, len(geometries)):
            if not geometries[i].touches(geometries[j]):
                # Hitung jarak terdekat antara polygon
                distance = geometries[i].distance(geometries[j])
                
                if distance > tolerance:
                    gaps.append({
                        'idsls_1': ids[i],
                        'idsls_2': ids[j],
                        'type': 'Gap Between Polygons',
                        'distance': distance,
                        'area': 'N/A'
                    })
    
    return pd.DataFrame(gaps)

# Main app
def main():
    st.title("Cek Gap Polygon")
    st.markdown("Halaman untuk memeriksa celah (gap) antar polygon")
    
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
        tolerance = st.number_input(
            "Tolerance (jarak minimum dianggap gap)",
            min_value=0.0,
            max_value=1.0,
            value=0.0001,
            step=0.00001,
            format="%.6f"
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
    if st.button("Mulai Pengecekan Gap", type="primary"):
        with st.spinner("Memeriksa gap polygon..."):
            try:
                # Lakukan pengecekan gap
                gaps = check_gaps(gdf_petasls, tolerance)
                
                # Tampilkan hasil
                st.subheader("Hasil Pengecekan Gap")
                
                if len(gaps) > 0:
                    st.error(f"❌ Ditemukan {len(gaps)} celah antar polygon")
                    
                    # Urutkan berdasarkan jarak terbesar
                    if 'distance' in gaps.columns:
                        # Filter hanya yang memiliki nilai distance numerik
                        numeric_gaps = gaps[gaps['distance'] != 'N/A'].copy()
                        numeric_gaps['distance'] = pd.to_numeric(numeric_gaps['distance'])
                        numeric_gaps = numeric_gaps.sort_values('distance', ascending=False)
                        
                        # Gabungkan kembali dengan isolated polygon
                        isolated_gaps = gaps[gaps['distance'] == 'N/A']
                        display_gaps = pd.concat([numeric_gaps.head(max_results//2), isolated_gaps.head(max_results//2)])
                    else:
                        display_gaps = gaps.head(max_results)
                    
                    # Tampilkan tabel
                    st.dataframe(display_gaps, use_container_width=True)
                    
                    # Tambahkan opsi untuk download
                    csv = display_gaps.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="Download Data Gap",
                        data=csv,
                        file_name='gap_polygon.csv',
                        mime='text/csv'
                    )
                    
                    # Tampilkan statistik
                    st.subheader("Statistik Gap")
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.metric("Total Gap", len(gaps))
                    with col2:
                        isolated_count = len([g for g in gaps if 'Isolated' in str(g['type'])])
                        st.metric("Polygon Terisolasi", isolated_count)
                    with col3:
                        distance_gaps = [g for g in gaps if str(g['distance']) != 'N/A']
                        avg_distance = np.mean([g['distance'] for g in distance_gaps]) if distance_gaps else 0
                        st.metric("Rata-rata Jarak", f"{avg_distance:.6f}")
                    with col4:
                        max_distance = np.max([g['distance'] for g in distance_gaps]) if distance_gaps else 0
                        st.metric("Jarak Maksimum", f"{max_distance:.6f}")
                    
                    # Visualisasi distribusi jarak gap
                    if distance_gaps:
                        st.subheader("Distribusi Jarak Gap")
                        distances = [g['distance'] for g in distance_gaps]
                        st.bar_chart(distances)
                    
                else:
                    st.success("✅ Tidak ditemukan celah antar polygon")
                
            except Exception as e:
                st.error(f"❌ Error dalam pengecekan: {str(e)}")

if __name__ == "__main__":
    main()