import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
import tempfile
import os
import sqlite3
import re
import warnings
warnings.filterwarnings('ignore')

# ============ KONFIGURASI HALAMAN ============
st.set_page_config(
    page_title="📊 Universal Data Processing Studio",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed" # Sidebar dirapatkan karena fokus di halaman utama
)

# ============ CUSTOM CSS ============
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(90deg, #4CAF50, #2196F3);
        padding: 20px;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin-bottom: 20px;
    }
    .stButton > button {
        width: 100%;
    }
    .streamlit-expanderHeader {
        font-size: 18px;
        font-weight: bold;
        background-color: #f0f2f6;
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)

# ============ INISIALISASI SESSION STATE ============
if 'df' not in st.session_state:
    st.session_state.df = None
if 'df_filtered' not in st.session_state:
    st.session_state.df_filtered = None

# ============ HELPER FUNCTIONS ============
def convert_df_to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Hasil')
    return output.getvalue()

def get_numeric_columns(df):
    return df.select_dtypes(include=[np.number]).columns.tolist()

def get_categorical_columns(df):
    return df.select_dtypes(include=['object', 'category']).columns.tolist()

# ============ FUNGSI LOADER MULTI-FORMAT ============
def load_data(uploaded_file):
    file_ext = os.path.splitext(uploaded_file.name)[1].lower()
    
    try:
        if file_ext in ['.xlsx', '.xls']:
            xls = pd.ExcelFile(uploaded_file)
            sheet_name = st.selectbox("Pilih Sheet:", xls.sheet_names) if len(xls.sheet_names) > 1 else xls.sheet_names[0]
            return pd.read_excel(uploaded_file, sheet_name=sheet_name)
        elif file_ext == '.csv':
            return pd.read_csv(uploaded_file)
        elif file_ext == '.parquet':
            return pd.read_parquet(uploaded_file)
        elif file_ext == '.json':
            return pd.read_json(uploaded_file)
        elif file_ext == '.dbf':
            from dbfread import DBF
            return pd.DataFrame(iter(DBF(uploaded_file)))
        elif file_ext == '.sav':
            import pyreadstat
            df, meta = pyreadstat.read_sav(uploaded_file)
            return df
        elif file_ext in ['.db', '.sqlite', '.sqlite3']:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp:
                tmp.write(uploaded_file.getvalue())
                tmp_path = tmp.name
            con = sqlite3.connect(tmp_path)
            tables = pd.read_sql_query("SELECT name FROM sqlite_master WHERE type='table'", con)['name'].tolist()
            con.close()
            if tables:
                table_name = st.selectbox("Pilih Tabel Database:", tables) if len(tables) > 1 else tables[0]
                con = sqlite3.connect(tmp_path)
                df = pd.read_sql_query(f"SELECT * FROM {table_name}", con)
                con.close()
                os.unlink(tmp_path)
                return df
        elif file_ext == '.sql':
            con = sqlite3.connect(':memory:')
            con.executescript(uploaded_file.getvalue().decode('utf-8'))
            tables = pd.read_sql_query("SELECT name FROM sqlite_master WHERE type='table'", con)['name'].tolist()
            if tables:
                table_name = st.selectbox("Pilih Tabel Hasil Query:", tables) if len(tables) > 1 else tables[0]
                return pd.read_sql_query(f"SELECT * FROM {table_name}", con)
        elif file_ext in ['.mdb', '.accdb']:
            try:
                import pandas_access as mdb
                with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
                    tmp.write(uploaded_file.getvalue())
                    tmp_path = tmp.name
                tables = mdb.list_tables(tmp_path)
                if tables:
                    table_name = st.selectbox("Pilih Tabel MS Access:", tables) if len(tables) > 1 else tables[0]
                    df = mdb.read_table(tmp_path, table_name)
                    os.unlink(tmp_path)
                    return df
            except ImportError:
                st.error("Library `pandas_access` belum terinstal.")
                return None
        else:
            st.error(f"Format {file_ext} tidak didukung.")
            return None
    except Exception as e:
        st.error(f"❌ Gagal membaca file: {e}")
        return None

# ============ HEADER APLIKASI ============
st.markdown("""
<div class="main-header">
    <h1>📊 Universal Data Processing Studio</h1>
    <p>Dukungan: Excel, CSV, DBF, SPSS, Parquet, JSON, SQL, dll + Kalkulasi & Manipulasi Kolom</p>
</div>
""", unsafe_allow_html=True)

# ============ AREA UPLOAD FILE (DI HALAMAN UTAMA) ============
with st.expander("📁 1. Upload Data", expanded=True):
    uploaded_file = st.file_uploader(
        "Pilih file data",
        type=['xlsx', 'xls', 'csv', 'parquet', 'json', 'dbf', 'sav', 'db', 'sqlite', 'sqlite3', 'sql', 'mdb', 'accdb']
    )
    
    if uploaded_file is not None:
        st.session_state.df = load_data(uploaded_file)
        if st.session_state.df is not None:
            st.session_state.df_filtered = st.session_state.df.copy()
            st.success(f"✅ File {uploaded_file.name} berhasil dimuat!")
    else:
        st.info("Silakan unggah file untuk memulai.")


# ============ KONTEN UTAMA EXPANDER ============
if st.session_state.df is not None:
    df = st.session_state.df.copy()
    
    # Metrik Utama
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("Total Baris", df.shape[0])
    with col2: st.metric("Total Kolom", df.shape[1])
    with col3: st.metric("Data Kosong", df.isnull().sum().sum())
    with col4: st.metric("Duplikat", df.duplicated().sum())
    
    st.markdown("---")

    # =============================================
    # EXPANDER: TAMPILKAN DATA
    # =============================================
    with st.expander("📋 2. Tampilkan Data"):
        n_rows = st.slider("Jumlah baris yang ditampilkan:", 5, min(100, df.shape[0]), 10, key="disp_rows")
        st.dataframe(df.head(n_rows), use_container_width=True)
        
        with st.expander("ℹ️ Informasi Tipe Data"):
            dtype_df = pd.DataFrame({
                'Kolom': df.columns,
                'Tipe Data': df.dtypes.astype(str).values,
                'Non-Null': df.count().values,
                'Null': df.isnull().sum().values,
                'Unique': df.nunique().values
            })
            st.dataframe(dtype_df, use_container_width=True)

    # =============================================
    # EXPANDER: BUAT KOLOM BARU
    # =============================================
    with st.expander("🧮 3. Buat Kolom Baru (Operasi Matematika & String)"):
        tab_math, tab_str = st.tabs(["🔢 Operasi Matematika", "✂️ Manipulasi Teks/Karakter"])
        
        # --- TAB 1: OPERASI MATEMATIKA ---
        with tab_math:
            st.subheader("Operasi Matematika Antar Kolom")
            numeric_cols = get_numeric_columns(df)
            
            if len(numeric_cols) >= 2:
                col1, col2, col3, col4 = st.columns(4)
                with col1: col_a = st.selectbox("Pilih Kolom A:", numeric_cols, key="math_col_a")
                with col2: operator = st.selectbox("Pilih Operasi:", ['+', '-', '*', '/'], key="math_op")
                with col3: col_b = st.selectbox("Pilih Kolom B:", numeric_cols, key="math_col_b")
                with col4: new_col_name = st.text_input("Nama Kolom Baru:", f"Hasil_{col_a}_{operator}_{col_b}", key="math_new_name")
                
                if st.button("Hitung & Buat Kolom", key="btn_math"):
                    try:
                        if operator == '+': df[new_col_name] = df[col_a] + df[col_b]
                        elif operator == '-': df[new_col_name] = df[col_a] - df[col_b]
                        elif operator == '*': df[new_col_name] = df[col_a] * df[col_b]
                        elif operator == '/': df[new_col_name] = df[col_a] / df[col_b].replace(0, np.nan)
                        
                        st.session_state.df = df.copy()
                        st.success(f"✅ Kolom '{new_col_name}' berhasil dibuat!")
                        st.dataframe(df[[col_a, col_b, new_col_name]].head(10), use_container_width=True)
                    except Exception as e:
                        st.error(f"Error: {e}")
            else:
                st.warning("Butuh minimal 2 kolom numerik untuk operasi matematika.")
                
            st.markdown("---")
            st.subheader("Operasi Matematika dengan Konstanta")
            if numeric_cols:
                c1, c2, c3 = st.columns(3)
                with c1: base_col = st.selectbox("Pilih Kolom:", numeric_cols, key="const_base_col")
                with c2: const_op = st.selectbox("Operasi:", ['+', '-', '*', '/'], key="const_op")
                with c3: const_val = st.number_input("Nilai Konstanta:", value=1.0, key="const_val")
                
                const_name = st.text_input("Nama Kolom Baru:", f"{base_col}_{const_op}_{const_val}", key="const_name")
                if st.button("Hitung dengan Konstanta", key="btn_const"):
                    try:
                        if const_op == '+': df[const_name] = df[base_col] + const_val
                        elif const_op == '-': df[const_name] = df[base_col] - const_val
                        elif const_op == '*': df[const_name] = df[base_col] * const_val
                        elif const_op == '/': df[const_name] = df[base_col] / const_val
                        
                        st.session_state.df = df.copy()
                        st.success(f"✅ Kolom '{const_name}' berhasil dibuat!")
                        st.dataframe(df[[base_col, const_name]].head(10), use_container_width=True)
                    except Exception as e:
                        st.error(f"Error: {e}")
        
        # --- TAB 2: MANIPULASI STRING ---
        with tab_str:
            st.subheader("Manipulasi String & Ekstraksi Karakter")
            all_cols = df.columns.tolist()
            c1, c2 = st.columns(2)
            with c1: str_col = st.selectbox("Pilih Kolom:", all_cols, key="str_col")
            with c2: str_op = st.selectbox("Pilih Operasi:", 
                ["Ambil N Karakter Pertama", "Ambil N Karakter Terakhir", "Ambil Karakter dari Index X ke Y",
                 "Ekstrak Angka dari Teks", "Ekstrak Huruf dari Teks", "Hapus Spasi (Trim)", 
                 "Ubah ke Huruf Kapital", "Ubah ke Huruf Kecil"], key="str_op")
            
            if str_op in ["Ambil N Karakter Pertama", "Ambil N Karakter Terakhir"]:
                n_chars = st.number_input("Jumlah Karakter (N):", min_value=1, value=4, step=1, key="n_chars")
            elif str_op == "Ambil Karakter dari Index X ke Y":
                c_idx1, c_idx2 = st.columns(2)
                with c_idx1: start_idx = st.number_input("Index Awal (mulai dari 0):", min_value=0, value=0, step=1, key="start_idx")
                with c_idx2: end_idx = st.number_input("Index Akhir:", min_value=1, value=4, step=1, key="end_idx")
            
            new_str_col_name = st.text_input("Nama Kolom Baru:", f"Hasil_{str_col}", key="str_new_name")
            if st.button("Buat Kolom Manipulasi", key="btn_str"):
                try:
                    target_series = df[str_col].astype(str)
                    if str_op == "Ambil N Karakter Pertama": df[new_str_col_name] = target_series.str[:n_chars]
                    elif str_op == "Ambil N Karakter Terakhir": df[new_str_col_name] = target_series.str[-n_chars:]
                    elif str_op == "Ambil Karakter dari Index X ke Y": df[new_str_col_name] = target_series.str[start_idx:end_idx]
                    elif str_op == "Ekstrak Angka dari Teks": df[new_str_col_name] = target_series.apply(lambda x: ''.join(re.findall(r'\d+', x)))
                    elif str_op == "Ekstrak Huruf dari Teks": df[new_str_col_name] = target_series.apply(lambda x: ''.join(re.findall(r'[a-zA-Z]+', x)))
                    elif str_op == "Hapus Spasi (Trim)": df[new_str_col_name] = target_series.str.strip()
                    elif str_op == "Ubah ke Huruf Kapital": df[new_str_col_name] = target_series.str.upper()
                    elif str_op == "Ubah ke Huruf Kecil": df[new_str_col_name] = target_series.str.lower()
                    
                    st.session_state.df = df.copy()
                    st.success(f"✅ Kolom '{new_str_col_name}' berhasil dibuat!")
                    st.dataframe(df[[str_col, new_str_col_name]].head(10), use_container_width=True)
                except Exception as e:
                    st.error(f"Error: {e}")

    # =============================================
    # EXPANDER: STATISTIK DESKRIPTIF
    # =============================================
    with st.expander("📊 4. Statistik Deskriptif"):
        numeric_cols = get_numeric_columns(df)
        cat_cols = get_categorical_columns(df)
        tab1, tab2, tab3 = st.tabs(["Numerik", "Kategorikal", "Korelasi"])
        with tab1:
            if numeric_cols:
                desc = df[numeric_cols].describe().T
                desc['median'] = df[numeric_cols].median()
                desc['variance'] = df[numeric_cols].var()
                st.dataframe(desc.round(3), use_container_width=True)
            else: st.info("Tidak ada kolom numerik.")
        with tab2:
            if cat_cols:
                for col in cat_cols[:5]:
                    st.markdown(f"**{col}**")
                    vc = df[col].value_counts().head(10)
                    fig = px.bar(x=vc.index.astype(str), y=vc.values, title=f"Top 10: {col}")
                    st.plotly_chart(fig, use_container_width=True)
            else: st.info("Tidak ada kolom kategorikal.")
        with tab3:
            if len(numeric_cols) > 1:
                corr = df[numeric_cols].corr()
                fig = px.imshow(corr, title="Heatmap Korelasi", color_continuous_scale='RdBu')
                st.plotly_chart(fig, use_container_width=True)
            else: st.info("Butuh minimal 2 kolom numerik.")

    # =============================================
    # EXPANDER: FILTER DATA
    # =============================================
    with st.expander("🔍 5. Filter Data"):
        df_filtered = df.copy()
        cols_to_filter = st.multiselect("Pilih kolom untuk filter:", df.columns.tolist(), key="filter_cols")
        
        for col in cols_to_filter:
            if df[col].dtype in ['int64', 'float64']:
                min_val, max_val = float(df[col].min()), float(df[col].max())
                selected_range = st.slider(f"Rentang {col}:", min_val, max_val, (min_val, max_val), key=f"slider_{col}")
                df_filtered = df_filtered[(df_filtered[col] >= selected_range[0]) & (df_filtered[col] <= selected_range[1])]
            else:
                unique_vals = df[col].dropna().unique().tolist()
                selected_vals = st.multiselect(f"Pilih nilai {col}:", unique_vals, default=unique_vals, key=f"multi_{col}")
                df_filtered = df_filtered[df_filtered[col].isin(selected_vals)]
        
        c1, c2 = st.columns(2)
        with c1: 
            if st.checkbox("Hapus Duplikat", key="chk_dup"): df_filtered = df_filtered.drop_duplicates()
        with c2: 
            if st.checkbox("Hapus Baris Kosong", key="chk_null"): df_filtered = df_filtered.dropna()
            
        col1, col2 = st.columns(2)
        with col1: st.metric("Sebelum Filter", df.shape[0])
        with col2: st.metric("Sesudah Filter", df_filtered.shape[0])
        
        st.dataframe(df_filtered, use_container_width=True)
        st.session_state.df_filtered = df_filtered
        
        if st.button("💾 Gunakan Hasil Filter untuk Fitur Lain", key="btn_filter"):
            st.session_state.df = df_filtered.copy()
            st.success("✅ Data hasil filter disimpan! Fitur lain kini menggunakan data ini.")

    # =============================================
    # EXPANDER: AGREGASI
    # =============================================
    with st.expander("📈 6. Agregasi Data (Group By)"):
        numeric_cols = get_numeric_columns(df)
        col1, col2, col3 = st.columns(3)
        with col1: group_cols = st.multiselect("Group By:", df.columns.tolist(), key="grp_cols")
        with col2: agg_cols = st.multiselect("Kolom Agregasi:", numeric_cols, key="agg_cols")
        with col3: agg_funcs = st.multiselect("Fungsi:", ['sum', 'mean', 'median', 'min', 'max', 'count', 'std'], default=['mean'], key="agg_funcs")
        
        if group_cols and agg_cols and agg_funcs:
            result = df.groupby(group_cols)[agg_cols].agg(agg_funcs)
            result.columns = ['_'.join(col).strip() for col in result.columns.values]
            result = result.reset_index()
            st.dataframe(result, use_container_width=True)
            st.session_state.df_aggregated = result
            if len(group_cols) == 1:
                y_col = st.selectbox("Visualisasi Y:", result.columns[1:], key="vis_agg")
                fig = px.bar(result, x=group_cols[0], y=y_col, color=group_cols[0])
                st.plotly_chart(fig, use_container_width=True)

    # =============================================
    # EXPANDER: PIVOT TABLE
    # =============================================
    with st.expander("🔄 7. Pivot Table"):
        numeric_cols = get_numeric_columns(df)
        col1, col2, col3, col4 = st.columns(4)
        with col1: index_col = st.selectbox("Index (Baris):", [""] + df.columns.tolist(), key="pvt_idx")
        with col2: columns_col = st.selectbox("Columns:", [""] + df.columns.tolist(), key="pvt_col")
        with col3: values_col = st.selectbox("Values:", [""] + numeric_cols, key="pvt_val")
        with col4: aggfunc = st.selectbox("Fungsi:", ['mean', 'sum', 'count', 'min', 'max'], key="pvt_func")
        
        if index_col and values_col:
            pivot_kwargs = {'index': index_col, 'values': values_col, 'aggfunc': aggfunc}
            if columns_col: pivot_kwargs['columns'] = columns_col
            pivot_table = pd.pivot_table(df, **pivot_kwargs).reset_index()
            st.dataframe(pivot_table, use_container_width=True)
            st.session_state.df_pivot = pivot_table
            if columns_col:
                fig = px.imshow(pivot_table.set_index(index_col).select_dtypes(include=[np.number]), color_continuous_scale='Viridis')
                st.plotly_chart(fig, use_container_width=True)

    # =============================================
    # EXPANDER: VISUALISASI DASHBOARD
    # =============================================
    with st.expander("📉 8. Visualisasi Dashboard"):
        numeric_cols = get_numeric_columns(df)
        chart_type = st.selectbox("Jenis Chart:", ["Bar", "Line", "Scatter", "Histogram", "Pie", "Box", "Violin", "Area"], key="vis_type")
        col1, col2, col3 = st.columns(3)
        with col1: x_col = st.selectbox("Sumbu X:", [""] + df.columns.tolist(), key="vis_x")
        with col2: y_col = st.selectbox("Sumbu Y:", [""] + numeric_cols, key="vis_y")
        with col3: color_col = st.selectbox("Warna:", [""] + df.columns.tolist(), key="vis_color")
        
        kwargs = {}
        if x_col: kwargs['x'] = x_col
        if y_col: kwargs['y'] = y_col
        if color_col: kwargs['color'] = color_col
        
        try:
            if chart_type == "Bar": fig = px.bar(df, **kwargs)
            elif chart_type == "Line": fig = px.line(df, **kwargs)
            elif chart_type == "Scatter": fig = px.scatter(df, **kwargs)
            elif chart_type == "Histogram": fig = px.histogram(df, x=x_col if x_col else y_col, color=color_col if color_col else None)
            elif chart_type == "Pie":
                pie_df = df.groupby(x_col).size().reset_index(name='count')
                fig = px.pie(pie_df, names=x_col, values='count')
            elif chart_type == "Box": fig = px.box(df, **kwargs)
            elif chart_type == "Violin": fig = px.violin(df, **kwargs)
            elif chart_type == "Area": fig = px.area(df, **kwargs)
            st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.error(f"Error: {e}")

    # =============================================
    # EXPANDER: PEMBERSIHAN DATA
    # =============================================
    with st.expander("🧹 9. Pembersihan Data"):
        df_clean = df.copy()
        if st.checkbox("Hapus Duplikat", key="cln_dup"): df_clean = df_clean.drop_duplicates()
        
        st.markdown("**Handle Missing Values**")
        missing_cols = df_clean.columns[df_clean.isnull().any()].tolist()
        if missing_cols:
            col = st.selectbox("Pilih Kolom:", missing_cols, key="cln_col")
            strategy = st.radio("Strategi:", ["Hapus Baris", "Isi Mean", "Isi Median", "Isi Modus"], key="cln_strat")
            if st.button("Terapkan", key="cln_btn"):
                if strategy == "Hapus Baris": df_clean = df_clean.dropna(subset=[col])
                elif strategy == "Isi Mean": df_clean[col] = df_clean[col].fillna(df_clean[col].mean())
                elif strategy == "Isi Median": df_clean[col] = df_clean[col].fillna(df_clean[col].median())
                elif strategy == "Isi Modus": df_clean[col] = df_clean[col].fillna(df_clean[col].mode()[0])
                st.session_state.df = df_clean.copy()
                st.success("Diterapkan! Perubahan tersimpan.")
        
        st.dataframe(df_clean.head(50), use_container_width=True)

    # =============================================
    # EXPANDER: EXPORT HASIL
    # =============================================
    with st.expander("📤 10. Export Hasil"):
        export_options = {"Data Asli/Saat Ini": df}
        if 'df_filtered' in st.session_state and st.session_state.df_filtered is not None: 
            export_options["Data Filtered"] = st.session_state.df_filtered
        if 'df_aggregated' in st.session_state: 
            export_options["Data Aggregated"] = st.session_state.df_aggregated
        if 'df_pivot' in st.session_state: 
            export_options["Data Pivot"] = st.session_state.df_pivot
        
        selected = st.selectbox("Pilih Data:", list(export_options.keys()), key="exp_sel")
        export_df = export_options[selected]
        st.dataframe(export_df.head(20), use_container_width=True)
        
        col1, col2 = st.columns(2)
        with col1:
            st.download_button("📥 Download Excel", convert_df_to_excel(export_df), "hasil.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        with col2:
            st.download_button("📥 Download CSV", export_df.to_csv(index=False).encode('utf-8'), "hasil.csv", "text/csv")