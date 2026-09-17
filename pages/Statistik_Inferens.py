# -*- coding: utf-8 -*-
"""
====================================================================
 APLIKASI PENGOLAH DATA & ANALISIS STATISTIK INFERENSIAL
====================================================================
Menjalankan :  streamlit run app_statistik.py
"""

import io, os, tempfile, warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import streamlit as st
from scipy import stats

import statsmodels.api as sm
import statsmodels.formula.api as smf
from statsmodels.stats.anova import anova_lm
from statsmodels.stats.multicomp import pairwise_tukeyhsd
from statsmodels.stats.diagnostic import het_breuschpagan
from statsmodels.stats.stattools import durbin_watson, jarque_bera
from statsmodels.stats.outliers_influence import variance_inflation_factor
from statsmodels.stats.weightstats import ttest_ind as sm_ttest
from statsmodels.multivariate.manova import MANOVA
from statsmodels.miscmodels.ordinal_model import OrderedModel

from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.model_selection import cross_val_score
from sklearn.metrics import confusion_matrix, accuracy_score, silhouette_score

from factor_analyzer import FactorAnalyzer
from factor_analyzer.factor_analyzer import calculate_kmo, calculate_bartlett_sphericity

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams.update({"figure.dpi": 100, "font.size": 9})

RUN = "🚀 RUN ANALISIS"

# ==================================================================
# KONFIGURASI HALAMAN & HELPER
# ==================================================================
st.set_page_config(page_title="Analisis Statistik Inferensial", page_icon="📊", layout="wide")


def persiapkan(df, cols):
    """Ambil kolom terpilih, buang baris kosong, samakan kategori ke string."""
    sub = df[cols].dropna().copy()
    for c in sub.columns:
        if not pd.api.types.is_numeric_dtype(sub[c]):
            sub[c] = sub[c].astype(str).str.strip()
    return sub


def hasil_uji(label, stat, p):
    """Tampilkan hasil uji + keputusan otomatis berdasarkan alpha."""
    al = st.session_state.get("alpha", 0.05)
    sig = pd.notna(p) and p < al
    teks = (f"**{label}** — Statistik = **{stat:.4f}** | p-value = **{p:.4f}** → "
            + (f"**Tolak H₀** (signifikan pada α = {al})" if sig
               else f"**Gagal Tolak H₀** (tidak signifikan pada α = {al})"))
    (st.success if sig else st.info)(teks)


def konversi_numerik(df):
    """Coba ubah kolom teks menjadi numerik bila mayoritas isinya angka."""
    df = df.copy()
    for c in df.columns:
        if df[c].dtype == object:
            bersih = df[c].astype(str).str.replace(",", "", regex=False).str.strip()
            num = pd.to_numeric(bersih, errors="coerce")
            if num.notna().mean() > 0.6:
                df[c] = num
    return df


# ==================================================================
# PEMBACAAN FILE MULTI-FORMAT
# ==================================================================
@st.cache_data(show_spinner=False)
def baca_data(raw: bytes, nama: str, sheet=None) -> pd.DataFrame:
    ext = os.path.splitext(nama.lower())[1]

    if ext == ".csv":
        for enc in ("utf-8", "utf-8-sig", "latin1", "cp1252"):
            try:
                teks = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            teks = raw.decode("utf-8", errors="replace")
        return pd.read_csv(io.StringIO(teks), sep=None, engine="python")

    if ext in (".xls", ".xlsx", ".xlsm"):
        return pd.read_excel(io.BytesIO(raw), sheet_name=sheet if sheet is not None else 0)

    if ext == ".dbf":
        with tempfile.NamedTemporaryFile(suffix=".dbf", delete=False) as tmp:
            tmp.write(raw); path = tmp.name
        try:
            from dbfread import DBF
            return pd.DataFrame(iter(DBF(path, load=True, encoding="latin1")))
        finally:
            os.remove(path)

    if ext == ".json":
        buf = io.BytesIO(raw)
        try:
            return pd.read_json(buf)
        except ValueError:
            buf.seek(0)
            return pd.read_json(buf, lines=True)

    if ext == ".sav":
        import pyreadstat
        with tempfile.NamedTemporaryFile(suffix=".sav", delete=False) as tmp:
            tmp.write(raw); path = tmp.name
        try:
            d, _ = pyreadstat.read_sav(path)
            return d
        finally:
            os.remove(path)

    if ext == ".dta":
        return pd.read_stata(io.BytesIO(raw))

    if ext == ".parquet":
        return pd.read_parquet(io.BytesIO(raw))

    if ext in (".pkl", ".pickle"):
        return pd.read_pickle(io.BytesIO(raw))

    # default: coba sebagai CSV dengan pemisah otomatis (juga menangani .txt)
    return pd.read_csv(io.BytesIO(raw), sep=None, engine="python")


# ==================================================================
# 1) REGRESI LINEAR (OLS)
# ==================================================================
def a_regresi_linear(df):
    st.subheader("📈 Regresi Linear Berganda (OLS)")
    num = df.select_dtypes("number").columns.tolist()
    if len(num) < 2:
        st.warning("Butuh minimal 2 kolom numerik."); return

    y = st.selectbox("Variabel Dependen / Y (numerik)", num)
    xs = st.multiselect("Variabel Independen / X (numerik)",
                        [c for c in num if c != y],
                        default=[c for c in num if c != y][:3])

    if st.button(RUN, type="primary", use_container_width=True):
        if not xs:
            st.error("Pilih minimal satu variabel X."); return
        data = persiapkan(df, [y] + xs)
        X = sm.add_constant(data[xs])
        model = sm.OLS(data[y], X).fit()

        c1, c2, c3 = st.columns(3)
        c1.metric("R²", f"{model.rsquared:.4f}")
        c2.metric("Adj. R²", f"{model.rsquared_adj:.4f}")
        c3.metric("p-value F-statistik", f"{model.f_pvalue:.4g}")

        st.markdown("#### Ringkasan Model")
        st.code(model.summary().as_text(), language=None)

        coef = pd.DataFrame({"Koefisien": model.params, "Std.Err": model.bse,
                             "t": model.tvalues, "p-value": model.pvalues,
                             "IC 2.5%": model.conf_int()[0], "IC 97.5%": model.conf_int()[1]})
        st.markdown("#### Tabel Koefisien")
        st.dataframe(coef.round(4), use_container_width=True)

        if len(xs) >= 2:
            vif = pd.DataFrame({"Variabel": xs,
                                "VIF": [variance_inflation_factor(X.values, i)
                                        for i in range(1, X.shape[1])]})
            st.markdown("#### Uji Multikolinearitas (VIF)")
            st.dataframe(vif.round(3), use_container_width=True)
            st.caption("VIF > 10 mengindikasikan multikolinearitas serius.")

        resid, fitted = model.resid, model.fittedvalues
        dw = durbin_watson(resid)
        bp_lm, bp_p, _, _ = het_breuschpagan(resid, X)
        jb, jb_p, _, _ = jarque_bera(resid)
        st.markdown("#### Uji Asumsi Klasik")
        st.dataframe(pd.DataFrame({
            "Uji": ["Durbin-Watson (autokorelasi)", "Breusch-Pagan (heteroskedastisitas)",
                    "Jarque-Bera (normalitas residual)"],
            "Statistik": [dw, bp_lm, jb],
            "p-value": [np.nan, bp_p, jb_p],
            "Kriteria": ["≈ 2 → bebas autokorelasi", "p > α → residual homogen", "p > α → residual normal"],
        }).round(4), use_container_width=True)

        fig, ax = plt.subplots(1, 2, figsize=(11, 4))
        ax[0].scatter(fitted, resid, alpha=.6, edgecolor="k", linewidth=.3)
        ax[0].axhline(0, color="red", ls="--")
        ax[0].set(title="Residual vs Fitted", xlabel="Nilai Prediksi", ylabel="Residual")
        sm.qqplot(resid, line="45", fit=True, ax=ax[1]); ax[1].set_title("QQ-Plot Residual")
        st.pyplot(fig); plt.close(fig)


# ==================================================================
# 2) REGRESI LOGISTIK BINER
# ==================================================================
def a_logit_biner(df):
    st.subheader("🎯 Regresi Logistik Biner")
    kandidat = [c for c in df.columns if df[c].nunique(dropna=True) == 2]
    num = df.select_dtypes("number").columns.tolist()
    if not kandidat or not num:
        st.warning("Butuh 1 kolom biner (Y) + minimal 1 kolom numerik (X)."); return

    ycol = st.selectbox("Variabel Dependen (tepat 2 kategori)", kandidat)
    xs = st.multiselect("Variabel Independen (numerik)", [c for c in num if c != ycol],
                        default=[c for c in num if c != ycol][:3])

    if st.button(RUN, type="primary", use_container_width=True):
        if not xs:
            st.error("Pilih minimal satu variabel X."); return
        data = persiapkan(df, [ycol] + xs)
        levels = sorted(data[ycol].unique(), key=str)
        y = (data[ycol] == levels[1]).astype(int)
        X = sm.add_constant(data[xs])
        model = sm.Logit(y, X).fit(disp=0)

        st.markdown("#### Ringkasan Model")
        st.code(model.summary().as_text(), language=None)
        st.caption(f"Encoding: {levels[0]} = 0, {levels[1]} = 1")

        st.markdown("#### Odds Ratio (e^β)")
        st.dataframe(pd.DataFrame({"Odds Ratio": np.exp(model.params),
                                   "IC 2.5%": np.exp(model.conf_int()[0]),
                                   "IC 97.5%": np.exp(model.conf_int()[1]),
                                   "p-value": model.pvalues}).round(4), use_container_width=True)

        pred = (model.predict(X) >= .5).astype(int)
        c1, c2 = st.columns(2)
        c1.metric("Akurasi Klasifikasi", f"{accuracy_score(y, pred):.1%}")
        c2.dataframe(pd.DataFrame(confusion_matrix(y, pred),
                                  index=[f"Aktual {l}" for l in levels],
                                  columns=[f"Pred {l}" for l in levels]))


# ==================================================================
# 3) REGRESI LOGISTIK MULTINOMIAL
# ==================================================================
def a_mnlogit(df):
    st.subheader("🎲 Regresi Logistik Multinomial")
    num = df.select_dtypes("number").columns.tolist()
    cats = [c for c in df.columns if 2 <= df[c].nunique(dropna=True) <= 10]
    if not cats or not num:
        st.warning("Butuh 1 kolom kategori (Y, 2–10 level) + kolom numerik (X)."); return

    ycol = st.selectbox("Variabel Dependen (kategori)", cats)
    xs = st.multiselect("Variabel Independen (numerik)", [c for c in num if c != ycol],
                        default=[c for c in num if c != ycol][:3])

    if st.button(RUN, type="primary", use_container_width=True):
        if not xs:
            st.error("Pilih minimal satu variabel X."); return
        data = persiapkan(df, [ycol] + xs)
        ycodes, uniques = pd.factorize(data[ycol], sort=True)
        X = sm.add_constant(data[xs])
        model = sm.MNLogit(ycodes, X).fit(disp=0)

        st.markdown("#### Ringkasan Model")
        st.code(model.summary().as_text(), language=None)
        st.caption("Pemetaan kategori: " + ", ".join(f"{i} = {u}" for i, u in enumerate(uniques)))

        st.markdown("#### Relative Risk Ratio (e^β) terhadap kategori dasar (0)")
        st.dataframe(np.exp(model.params).round(4), use_container_width=True)


# ==================================================================
# 4) REGRESI ORDINAL
# ==================================================================
def a_regresi_ordinal(df):
    st.subheader("🎚️ Regresi Logistik Ordinal")
    num = df.select_dtypes("number").columns.tolist()
    cats = [c for c in df.columns if 2 <= df[c].nunique(dropna=True) <= 8]
    if not cats or not num:
        st.warning("Butuh 1 kolom ordinal (Y) + kolom numerik (X)."); return

    ycol = st.selectbox("Variabel Dependen (ordinal)", cats)
    xs = st.multiselect("Variabel Independen (numerik)", [c for c in num if c != ycol],
                        default=[c for c in num if c != ycol][:3])
    level_default = sorted(df[ycol].dropna().astype(str).unique())
    urutan = st.multiselect("Urutan level Y (terendah → tertinggi)", level_default,
                            default=level_default)

    if st.button(RUN, type="primary", use_container_width=True):
        if len(urutan) < 2 or not xs:
            st.error("Pilih minimal 2 level Y dan 1 variabel X."); return
        data = df[[ycol] + xs].dropna()
        data[ycol] = pd.Categorical(data[ycol].astype(str), categories=urutan, ordered=True)
        model = OrderedModel(data[ycol], data[xs], distr="logit")
        res = model.fit(method="bfgs", disp=0)
        st.markdown("#### Ringkasan Model")
        st.code(res.summary().as_text(), language=None)
        st.caption("e^β > 1 → X menaikkan peluang menuju kategori yang lebih tinggi.")


# ==================================================================
# 5) REGRESI POISSON
# ==================================================================
def a_poisson(df):
    st.subheader("📉 Regresi Poisson (Data Hitungan)")
    num = df.select_dtypes("number").columns.tolist()
    if len(num) < 2:
        st.warning("Butuh minimal 2 kolom numerik."); return

    y = st.selectbox("Variabel Dependen (hitungan, ≥ 0)", num)
    xs = st.multiselect("Variabel Independen (numerik)", [c for c in num if c != y],
                        default=[c for c in num if c != y][:3])

    if st.button(RUN, type="primary", use_container_width=True):
        if not xs:
            st.error("Pilih minimal satu variabel X."); return
        data = persiapkan(df, [y] + xs)
        if (data[y] < 0).any():
            st.error("Regresi Poisson membutuhkan nilai Y ≥ 0."); return
        X = sm.add_constant(data[xs])
        model = sm.GLM(data[y], X, family=sm.families.Poisson()).fit()
        st.markdown("#### Ringkasan Model")
        st.code(model.summary().as_text(), language=None)
        st.markdown("#### IRR (Incidence Rate Ratio, e^β)")
        st.dataframe(pd.DataFrame({"IRR": np.exp(model.params),
                                   "p-value": model.pvalues}).round(4), use_container_width=True)
        st.caption("IRR > 1 → X menaikkan laju kejadian; IRR < 1 → menurunkan.")


# ==================================================================
# 6) ANOVA SATU ARAH
# ==================================================================
def a_anova1(df):
    st.subheader("🧪 ANOVA Satu Arah (One-Way)")
    num = df.select_dtypes("number").columns.tolist()
    cats = df.select_dtypes(exclude="number").columns.tolist()
    if not num or not cats:
        st.warning("Butuh 1 kolom numerik (Y) + 1 kolom kategori (faktor)."); return

    y = st.selectbox("Variabel Dependen (numerik)", num)
    f = st.selectbox("Faktor (kategori)", cats)

    if st.button(RUN, type="primary", use_container_width=True):
        data = persiapkan(df, [y, f]); data.columns = ["Y", "G"]
        groups = [g["Y"].values for _, g in data.groupby("G")]

        st.markdown("#### Statistik Deskriptif per Kelompok")
        st.dataframe(data.groupby("G")["Y"].agg(
            ["count", "mean", "median", "std", "min", "max"]).round(3), use_container_width=True)

        if 2 <= len(groups) <= 12:
            sh = [stats.shapiro(g)[1] if len(g) >= 3 else np.nan for g in groups]
            st.caption("p-value Shapiro-Wilk per kelompok: " +
                       ", ".join(f"{p:.3f}" if pd.notna(p) else "-" for p in sh))
        lev = stats.levene(*groups, center="median")
        hasil_uji("Uji Homogenitas Varians (Levene)", lev.statistic, lev.pvalue)

        model = smf.ols("Y ~ C(G)", data=data).fit()
        tbl = anova_lm(model, typ=2)
        tbl.index = ["Faktor (Antar Kelompok)", "Residual (Dalam Kelompok)"]
        st.markdown("#### Tabel ANOVA")
        st.dataframe(tbl.round(4), use_container_width=True)

        F, p = tbl["F"].iloc[0], tbl["PR(>F)"].iloc[0]
        eta = tbl["sum_sq"].iloc[0] / tbl["sum_sq"].sum()
        st.metric("Eta Squared (ukuran efek)", f"{eta:.3f}")
        hasil_uji("ANOVA F-Test", F, p)

        fig, ax = plt.subplots(figsize=(7, 4))
        data.boxplot(column="Y", by="G", ax=ax)
        ax.set(xlabel="Kelompok", ylabel="Y"); fig.suptitle("")
        st.pyplot(fig); plt.close(fig)

        al = st.session_state.get("alpha", .05)
        if p < al and len(groups) > 2:
            st.markdown("#### Post-Hoc: Tukey HSD")
            tukey = pairwise_tukeyhsd(data["Y"], data["G"])
            tb = tukey.summary()
            st.dataframe(pd.DataFrame(tb.data[1:], columns=tb.data[0]), use_container_width=True)
            try:
                figt = tukey.plot_simultaneous()[0]
                st.pyplot(figt); plt.close(figt)
            except Exception:
                pass


# ==================================================================
# 7) ANOVA DUA ARAH
# ==================================================================
def a_anova2(df):
    st.subheader("🧪 ANOVA Dua Arah (Two-Way)")
    num = df.select_dtypes("number").columns.tolist()
    cats = df.select_dtypes(exclude="number").columns.tolist()
    if not num or len(cats) < 2:
        st.warning("Butuh 1 kolom numerik (Y) + 2 kolom kategori (faktor A & B)."); return

    y = st.selectbox("Variabel Dependen (numerik)", num)
    a = st.selectbox("Faktor A", cats)
    b = st.selectbox("Faktor B", [c for c in cats if c != a])
    interaksi = st.checkbox("Sertakan interaksi A × B", value=True)

    if st.button(RUN, type="primary", use_container_width=True):
        data = persiapkan(df, [y, a, b]); data.columns = ["Y", "A", "B"]
        formula = "Y ~ C(A) * C(B)" if interaksi else "Y ~ C(A) + C(B)"
        tbl = anova_lm(smf.ols(formula, data).fit(), typ=2)
        st.markdown("#### Tabel ANOVA")
        st.dataframe(tbl.round(4), use_container_width=True)
        for idx, row in tbl.iterrows():
            if idx != "Residual" and pd.notna(row.get("F")):
                hasil_uji(str(idx), row["F"], row["PR(>F)"])

        means = data.groupby(["A", "B"])["Y"].mean().unstack()
        fig, ax = plt.subplots(figsize=(7, 4))
        for col in means.columns:
            ax.plot(means.index.astype(str), means[col], marker="o", label=str(col))
        ax.set(title="Plot Interaksi (rata-rata Y)", xlabel="Faktor A", ylabel="Rata-rata Y")
        ax.legend(title="Faktor B")
        st.pyplot(fig); plt.close(fig)


# ==================================================================
# 8) ANCOVA
# ==================================================================
def a_ancova(df):
    st.subheader("📐 ANCOVA")
    num = df.select_dtypes("number").columns.tolist()
    cats = df.select_dtypes(exclude="number").columns.tolist()
    if not num or not cats:
        st.warning("Butuh Y numerik, faktor kategori, dan kovariat numerik."); return

    y = st.selectbox("Variabel Dependen (numerik)", num)
    f = st.selectbox("Faktor (kategori)", cats)
    covs = st.multiselect("Kovariat (numerik)", [c for c in num if c != y],
                          default=[c for c in num if c != y][:1])
    interaksi = st.checkbox("Sertakan interaksi Faktor × Kovariat", value=False)

    if st.button(RUN, type="primary", use_container_width=True):
        if not covs:
            st.error("Pilih minimal satu kovariat."); return
        data = persiapkan(df, [y, f] + covs)
        data.columns = ["Y", "F"] + [f"K{i+1}" for i in range(len(covs))]
        cov_term = " + ".join(data.columns[2:])
        if interaksi:
            formula = "Y ~ C(F) + " + cov_term + " + " + " + ".join(f"C(F):{k}" for k in data.columns[2:])
        else:
            formula = "Y ~ C(F) + " + cov_term
        tbl = anova_lm(smf.ols(formula, data).fit(), typ=2)
        st.markdown("#### Tabel ANCOVA")
        st.dataframe(tbl.round(4), use_container_width=True)
        for idx, row in tbl.iterrows():
            if idx != "Residual" and pd.notna(row.get("F")):
                hasil_uji(str(idx), row["F"], row["PR(>F)"])


# ==================================================================
# 9) MANOVA
# ==================================================================
def a_manova(df):
    st.subheader("🧮 MANOVA")
    num = df.select_dtypes("number").columns.tolist()
    cats = df.select_dtypes(exclude="number").columns.tolist()
    if len(num) < 2 or not cats:
        st.warning("Butuh minimal 2 Y numerik + 1 faktor kategori."); return

    ys = st.multiselect("Variabel Dependen (numerik, ≥ 2)", num, default=num[:2])
    g = st.selectbox("Faktor (kategori)", cats)

    if st.button(RUN, type="primary", use_container_width=True):
        if len(ys) < 2:
            st.error("Pilih minimal 2 variabel dependen."); return
        data = persiapkan(df, ys + [g])
        safe_y = [f"Y{i+1}" for i in range(len(ys))]
        data.columns = safe_y + ["G"]
        maov = MANOVA.from_formula(" + ".join(safe_y) + " ~ C(G)", data=data)
        st.markdown("#### Hasil Uji Multivariat")
        st.code(str(maov.mv_test()), language=None)
        st.markdown("#### Rata-rata per Kelompok")
        st.dataframe(data.groupby("G")[safe_y].mean().round(3), use_container_width=True)


# ==================================================================
# 10) UJI t
# ==================================================================
def a_ttest(df):
    st.subheader("⚖️ Uji t")
    mode = st.radio("Jenis uji", ["Sampel Independen", "Sampel Berpasangan", "Satu Sampel"],
                    horizontal=True)
    num = df.select_dtypes("number").columns.tolist()
    al = st.session_state.get("alpha", .05)

    if mode == "Satu Sampel":
        v = st.selectbox("Variabel (numerik)", num)
        mu = st.number_input("Nilai hipotesis μ₀", value=0.0)
        if st.button(RUN, type="primary", use_container_width=True):
            x = df[v].dropna()
            t, p = stats.ttest_1samp(x, mu)
            d = (x.mean() - mu) / x.std(ddof=1)
            st.dataframe(pd.DataFrame(
                {"Nilai": [len(x), x.mean(), x.std(ddof=1), t, len(x) - 1, p, d]},
                index=["n", "Mean sampel", "Std", "t-statistik", "df", "p-value", "Cohen's d"]).round(4))
            hasil_uji(f"Uji t Satu Sampel (H₀: μ = {mu})", t, p)
            st.caption("Cohen's d: 0.2 kecil · 0.5 sedang · 0.8 besar")

    elif mode == "Sampel Independen":
        cats = df.select_dtypes(exclude="number").columns.tolist()
        if not num or not cats:
            st.warning("Butuh 1 variabel numerik + 1 variabel kelompok."); return
        v = st.selectbox("Variabel (numerik)", num)
        g = st.selectbox("Variabel kelompok", cats)
        levels = sorted(df[g].dropna().astype(str).unique())
        dua = st.multiselect("Pilih 2 kelompok yang dibandingkan", levels, default=levels[:2])
        if st.button(RUN, type="primary", use_container_width=True):
            if len(dua) != 2:
                st.error("Pilih tepat 2 kelompok."); return
            data = persiapkan(df, [v, g]); data.columns = ["V", "G"]
            data["G"] = data["G"].astype(str)
            a = data.loc[data.G == dua[0], "V"]; b = data.loc[data.G == dua[1], "V"]
            lev = stats.levene(a, b, center="median")
            equal = lev.pvalue >= al
            hasil_uji("Uji Levene (homogenitas varians)", lev.statistic, lev.pvalue)
            t, p, dfr = sm_ttest(a, b, usevar="pooled" if equal else "unequal")
            n1, n2 = len(a), len(b)
            sp = np.sqrt(((n1-1)*a.std(ddof=1)**2 + (n2-1)*b.std(ddof=1)**2) / (n1+n2-2))
            d = (a.mean() - b.mean()) / sp
            st.markdown("#### Statistik Kelompok")
            st.dataframe(pd.DataFrame({"n": [n1, n2], "Mean": [a.mean(), b.mean()],
                                       "Std": [a.std(ddof=1), b.std(ddof=1)]}, index=dua).round(4))
            st.dataframe(pd.DataFrame({"Nilai": [t, dfr, p, d]},
                                      index=["t-statistik", "df", "p-value", "Cohen's d"]).round(4))
            hasil_uji(f"Uji t Independen (varians {'homogen' if equal else 'tidak homogen'})", t, p)

    else:  # Berpasangan
        v1 = st.selectbox("Pengukuran 1 (sebelum)", num)
        v2 = st.selectbox("Pengukuran 2 (sesudah)", [c for c in num if c != v1])
        if st.button(RUN, type="primary", use_container_width=True):
            sub = df[[v1, v2]].dropna()
            t, p = stats.ttest_rel(sub[v1], sub[v2])
            diff = sub[v1] - sub[v2]
            st.dataframe(pd.DataFrame(
                {"Nilai": [len(sub), sub[v1].mean(), sub[v2].mean(),
                           diff.mean(), diff.std(ddof=1), t, p,
                           diff.mean() / diff.std(ddof=1)]},
                index=["n pasangan", f"Mean {v1}", f"Mean {v2}", "Mean selisih",
                       "Std selisih", "t-statistik", "p-value", "Cohen's dz"]).round(4))
            hasil_uji("Uji t Berpasangan", t, p)


# ==================================================================
# 11) CHI-SQUARE
# ==================================================================
def a_chisquare(df):
    st.subheader("🔀 Uji Chi-Square (Independensi)")
    cats = [c for c in df.columns if df[c].nunique(dropna=True) <= 20]
    if len(cats) < 2:
        st.warning("Butuh minimal 2 variabel kategorik."); return

    c1 = st.selectbox("Variabel 1", cats)
    c2 = st.selectbox("Variabel 2", [c for c in cats if c != c1])

    if st.button(RUN, type="primary", use_container_width=True):
        data = df[[c1, c2]].dropna().astype(str)
        tab = pd.crosstab(data[c1], data[c2])
        chi2v, p, dof, exp = stats.chi2_contingency(tab)
        n = tab.values.sum()
        cramers = np.sqrt(chi2v / (n * (min(tab.shape) - 1)))

        st.markdown("#### Tabel Kontingensi (Observed)")
        st.dataframe(tab, use_container_width=True)
        st.markdown("#### Frekuensi Harapan")
        st.dataframe(pd.DataFrame(exp, index=tab.index, columns=tab.columns).round(2),
                     use_container_width=True)
        st.markdown("#### Persentase per Baris (%)")
        st.dataframe((pd.crosstab(data[c1], data[c2], normalize="index") * 100).round(2),
                     use_container_width=True)

        st.metric("Cramér's V (ukuran efek)", f"{cramers:.3f}")
        hasil_uji(f"Chi-Square Independensi (df = {dof})", chi2v, p)
        if (exp < 5).any():
            st.warning("Ada sel dengan frekuensi harapan < 5 — interpretasikan dengan hati-hati.")
        st.caption("Cramér's V: < 0.1 kecil · < 0.3 sedang · < 0.5 besar")


# ==================================================================
# 12) KORELASI
# ==================================================================
def a_korelasi(df):
    st.subheader("🔗 Analisis Korelasi")
    num = df.select_dtypes("number").columns.tolist()
    if len(num) < 2:
        st.warning("Butuh minimal 2 kolom numerik."); return

    cols = st.multiselect("Pilih variabel numerik", num, default=num[:6])
    metode = st.radio("Metode", ["pearson", "spearman", "kendall"], horizontal=True,
                      format_func=str.capitalize)

    if st.button(RUN, type="primary", use_container_width=True):
        if len(cols) < 2:
            st.error("Pilih minimal 2 variabel."); return
        data = df[cols].dropna()
        corr = data.corr(method=metode)

        def matriks_p(data, metode):
            n = len(data.columns)
            pm = pd.DataFrame(np.eye(n), index=data.columns, columns=data.columns)
            for i in range(n):
                for j in range(i + 1, n):
                    x, yy = data.iloc[:, i], data.iloc[:, j]
                    if metode == "pearson":
                        _, pv = stats.pearsonr(x, yy)
                    elif metode == "spearman":
                        _, pv = stats.spearmanr(x, yy)
                    else:
                        _, pv = stats.kendalltau(x, yy)
                    pm.iloc[i, j] = pm.iloc[j, i] = pv
            return pm

        st.markdown(f"#### Matriks Korelasi ({metode.capitalize()})")
        st.dataframe(corr.round(3), use_container_width=True)
        st.markdown("#### Matriks p-value")
        st.dataframe(matriks_p(data, metode).round(4), use_container_width=True)
        st.caption("|r|: < 0.3 lemah · 0.3–0.5 sedang · 0.5–0.7 kuat · > 0.7 sangat kuat")

        n = len(cols)
        fig, ax = plt.subplots(figsize=(0.6 * n + 3, 0.5 * n + 2.5))
        im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1)
        ax.set_xticks(range(n)); ax.set_xticklabels(corr.columns, rotation=45, ha="right")
        ax.set_yticks(range(n)); ax.set_yticklabels(corr.index)
        for i in range(n):
            for j in range(n):
                ax.text(j, i, f"{corr.values[i, j]:.2f}", ha="center", va="center", fontsize=8,
                        color="white" if abs(corr.values[i, j]) > .5 else "black")
        fig.colorbar(im, shrink=.8)
        st.pyplot(fig); plt.close(fig)


# ==================================================================
# 13) ANALISIS FAKTOR (EFA)
# ==================================================================
def a_faktor(df):
    st.subheader("🧩 Analisis Faktor (EFA)")
    num = df.select_dtypes("number").columns.tolist()
    if len(num) < 3:
        st.warning("Butuh minimal 3 kolom numerik."); return

    cols = st.multiselect("Pilih variabel (indikator)", num, default=num[:8])
    try:
        ev = np.sort(np.linalg.eigvalsh(df[cols].dropna().corr().values))[::-1]
        n_kaiser = max(1, int((ev > 1).sum()))
    except Exception:
        n_kaiser = 1

    k = st.number_input("Jumlah faktor", 1, max(1, len(cols)), value=min(n_kaiser, len(cols)))
    rot = st.selectbox("Rotasi", ["varimax", "promax", "none"])
    sembunyi = st.checkbox("Sembunyikan loading dengan |nilai| < 0.40", value=False)

    if st.button(RUN, type="primary", use_container_width=True):
        data = df[cols].dropna()
        if data.shape[0] < 5 * len(cols):
            st.warning("Disarankan jumlah observasi ≥ 5 × jumlah variabel.")

        try:
            chi_b, p_b = calculate_bartlett_sphericity(data)
            hasil_uji("Uji Bartlett's Test of Sphericity", chi_b, p_b)
            _, kmo = calculate_kmo(data)
            st.metric("KMO (Kaiser-Meyer-Olkin)", f"{kmo:.3f}")
            if kmo < .5:
                st.warning("KMO < 0.5 → kecukupan sampling kurang untuk analisis faktor.")
        except Exception as e:
            st.warning(f"KMO/Bartlett gagal dihitung: {e}")

        fa = FactorAnalyzer(n_factors=int(k), rotation=None if rot == "none" else rot)
        fa.fit(data)
        load = pd.DataFrame(fa.loadings_, index=cols,
                            columns=[f"Faktor {i+1}" for i in range(int(k))])
        if sembunyi:
            load = load.where(load.abs() >= .4, "")
        st.markdown("#### Matriks Loading")
        st.dataframe(pd.DataFrame(load).round(3), use_container_width=True)

        st.markdown("#### Komunalitas")
        st.dataframe(pd.DataFrame({"Komunalitas": fa.get_communalities()},
                                  index=cols).round(3), use_container_width=True)

        ss, prop, cum = fa.get_factor_variance()
        st.markdown("#### Varians yang Dijelaskan")
        st.dataframe(pd.DataFrame({"SS Loading": ss, "Proporsi": prop, "Kumulatif": cum},
                                  index=[f"Faktor {i+1}" for i in range(int(k))]).round(3),
                     use_container_width=True)

        fig, ax = plt.subplots(figsize=(7, 4))
        ax.plot(range(1, len(ev) + 1), ev, "o-")
        ax.axhline(1, color="red", ls="--", label="Eigenvalue = 1 (kaidah Kaiser)")
        ax.set(xlabel="Komponen", ylabel="Eigenvalue", title="Scree Plot"); ax.legend()
        st.pyplot(fig); plt.close(fig)


# ==================================================================
# 14) PCA
# ==================================================================
def a_pca(df):
    st.subheader("🧭 Analisis Komponen Utama (PCA)")
    num = df.select_dtypes("number").columns.tolist()
    if len(num) < 2:
        st.warning("Butuh minimal 2 kolom numerik."); return

    cols = st.multiselect("Pilih variabel", num, default=num[:6])
    skala = st.checkbox("Standarisasi data (z-score)", value=True)
    n_show = st.slider("Jumlah komponen pada tabel loading", 2, max(2, len(cols)),
                       min(3, len(cols)))

    if st.button(RUN, type="primary", use_container_width=True):
        data = df[cols].dropna()
        Z = StandardScaler().fit_transform(data) if skala else data.values
        pca = PCA().fit(Z)
        evr = pca.explained_variance_ratio_

        st.markdown("#### Varians yang Dijelaskan")
        st.dataframe(pd.DataFrame({"Eigenvalue": pca.explained_variance_,
                                   "Proporsi": evr, "Kumulatif": np.cumsum(evr)},
                                  index=[f"PC{i+1}" for i in range(len(evr))]).round(4),
                     use_container_width=True)

        st.markdown("#### Loading Komponen")
        st.dataframe(pd.DataFrame(pca.components_.T[:, :n_show], index=cols,
                                  columns=[f"PC{i+1}" for i in range(n_show)]).round(3),
                     use_container_width=True)

        fig, ax = plt.subplots(figsize=(7, 4))
        ax.bar(range(1, len(evr) + 1), evr, alpha=.7, label="Proporsi varians")
        ax2 = ax.twinx()
        ax2.plot(range(1, len(evr) + 1), np.cumsum(evr), "ro-", label="Kumulatif")
        ax2.axhline(.8, ls="--", color="gray"); ax2.set_ylim(0, 1.05)
        ax.set(xlabel="Komponen Utama", ylabel="Proporsi Varians", title="Scree Plot PCA")
        st.pyplot(fig); plt.close(fig)

        scores = PCA(n_components=2).fit_transform(Z)
        fig, ax = plt.subplots(figsize=(7, 5.5))
        ax.scatter(scores[:, 0], scores[:, 1], alpha=.5, s=15)
        vsc = np.abs(scores[:, :2]).max(axis=0)
        for i, c in enumerate(cols):
            xv, yv = pca.components_[0, i] * vsc[0], pca.components_[1, i] * vsc[1]
            ax.arrow(0, 0, xv, yv, color="red", alpha=.7, head_width=vsc[0] * .03)
            ax.text(xv * 1.12, yv * 1.12, c, color="red", fontsize=8)
        ax.axhline(0, color="grey", lw=.5); ax.axvline(0, color="grey", lw=.5)
        ax.set(title="Biplot PCA (PC1 vs PC2)", xlabel="PC1", ylabel="PC2")
        st.pyplot(fig); plt.close(fig)
        st.caption(f"PC1 + PC2 menjelaskan **{evr[:2].sum():.1%}** dari total varians.")


# ==================================================================
# 15) ANALISIS DISKRIMINAN (LDA)
# ==================================================================
def a_lda(df):
    st.subheader("🧿 Analisis Diskriminan (LDA)")
    num = df.select_dtypes("number").columns.tolist()
    cats = df.select_dtypes(exclude="number").columns.tolist()
    if not num or not cats:
        st.warning("Butuh kolom numerik (X) + kolom kategori (kelompok)."); return

    y = st.selectbox("Variabel kelompok (kategori)", cats)
    xs = st.multiselect("Variabel pembeda (numerik)", [c for c in num if c != y],
                        default=[c for c in num if c != y][:4])

    if st.button(RUN, type="primary", use_container_width=True):
        if not xs:
            st.error("Pilih minimal satu variabel X."); return
        data = persiapkan(df, xs + [y])
        X, yv = data[xs].values, data[y].values
        lda = LinearDiscriminantAnalysis().fit(X, yv)
        pred = lda.predict(X)

        c1, c2 = st.columns(2)
        c1.metric("Akurasi (resubstitusi)", f"{accuracy_score(yv, pred):.1%}")
        try:
            cv = min(5, pd.Series(yv).value_counts().min())
            if cv >= 2:
                sc = cross_val_score(LinearDiscriminantAnalysis(), X, yv, cv=cv)
                c2.metric(f"Akurasi Cross-Validation ({cv}-fold)", f"{sc.mean():.1%}")
        except Exception:
            pass

        st.markdown("#### Rata-rata Variabel per Kelompok")
        st.dataframe(pd.DataFrame(lda.means_, index=lda.classes_, columns=xs).round(3),
                     use_container_width=True)
        st.markdown("#### Koefisien Fungsi Diskriminan")
        st.dataframe(pd.DataFrame(lda.scalings_, index=xs,
                                  columns=[f"LD{i+1}" for i in range(lda.scalings_.shape[1])]).round(4),
                     use_container_width=True)
        st.markdown("#### Matriks Klasifikasi")
        cm = confusion_matrix(yv, pred, labels=lda.classes_)
        st.dataframe(pd.DataFrame(cm, index=[f"Aktual {c}" for c in lda.classes_],
                                  columns=[f"Pred {c}" for c in lda.classes_]),
                     use_container_width=True)


# ==================================================================
# 16) K-MEANS CLUSTERING
# ==================================================================
def a_kmeans(df):
    st.subheader("🧲 K-Means Clustering")
    num = df.select_dtypes("number").columns.tolist()
    if len(num) < 2:
        st.warning("Butuh minimal 2 kolom numerik."); return

    xs = st.multiselect("Variabel clustering", num, default=num[:4])
    k = st.slider("Jumlah cluster (k)", 2, 10, 3)
    skala = st.checkbox("Standarisasi variabel", value=True)

    if st.button(RUN, type="primary", use_container_width=True):
        if len(xs) < 2:
            st.error("Pilih minimal 2 variabel."); return
        data = df[xs].dropna()
        Z = StandardScaler().fit_transform(data) if skala else data.values
        km = KMeans(n_clusters=k, n_init=10, random_state=42).fit(Z)
        lab = km.labels_

        c1, c2 = st.columns(2)
        sil = silhouette_score(Z, lab) if k < len(Z) else np.nan
        c1.metric("Silhouette Score", f"{sil:.3f}")
        c2.bar_chart(pd.Series(lab).value_counts().sort_index().rename("Jumlah anggota"))

        centers = km.cluster_centers_
        if skala:
            centers = StandardScaler().fit(data).inverse_transform(centers)
        st.markdown("#### Pusat Cluster (skala asli)")
        st.dataframe(pd.DataFrame(centers, columns=xs,
                                  index=[f"Cluster {i}" for i in range(k)]).round(3),
                     use_container_width=True)

        inert = [KMeans(n_clusters=i, n_init=10, random_state=42).fit(Z).inertia_
                 for i in range(1, 9)]
        fig, ax = plt.subplots(figsize=(6, 3.5))
        ax.plot(range(1, 9), inert, "o-")
        ax.set(title="Elbow Method (bantu menentukan k)", xlabel="k", ylabel="Inertia")
        st.pyplot(fig); plt.close(fig)

        p2 = PCA(n_components=2).fit_transform(Z)
        fig, ax = plt.subplots(figsize=(7, 5))
        for i in range(k):
            ax.scatter(p2[lab == i, 0], p2[lab == i, 1], alpha=.6, label=f"Cluster {i}", s=18)
        ax.legend(); ax.set(title="Visualisasi Cluster (proyeksi PCA 2D)")
        st.pyplot(fig); plt.close(fig)

        hasil = data.copy(); hasil["Cluster"] = lab
        st.markdown("#### Data + Label Cluster (pratinjau)")
        st.dataframe(hasil.head(100), use_container_width=True)
        st.download_button("⬇️ Unduh hasil clustering (CSV)",
                           hasil.to_csv(index=False).encode("utf-8"),
                           "hasil_cluster.csv", "text/csv")


# ==================================================================
# 17) KRUSKAL-WALLIS
# ==================================================================
def a_kruskal(df):
    st.subheader("🧪 Uji Kruskal-Wallis (Non-Parametrik)")
    num = df.select_dtypes("number").columns.tolist()
    cats = df.select_dtypes(exclude="number").columns.tolist()
    if not num or not cats:
        st.warning("Butuh 1 variabel numerik + 1 faktor kategori."); return

    y = st.selectbox("Variabel Dependen (numerik)", num)
    g = st.selectbox("Faktor (kategori)", cats)

    if st.button(RUN, type="primary", use_container_width=True):
        data = persiapkan(df, [y, g]); data.columns = ["Y", "G"]
        groups = [gg["Y"].values for _, gg in data.groupby("G")]
        H, p = stats.kruskal(*groups)
        k = len(groups)
        ranks = data["Y"].rank()
        mr = data.assign(R=ranks).groupby("G")["R"].mean()
        st.markdown("#### Statistik per Kelompok")
        st.dataframe(data.groupby("G")["Y"].agg(["count", "median", "mean"])
                     .join(mr.rename("Mean Rank")).round(3), use_container_width=True)
        hasil_uji("Kruskal-Wallis H", H, p)
        st.caption(f"Epsilon-squared (ukuran efek) = {(H - k + 1) / (len(data) - k):.3f}")

        al = st.session_state.get("alpha", .05)
        if p < al and k > 2:
            st.markdown("#### Post-Hoc: Mann-Whitney U (koreksi Bonferroni)")
            lv = sorted(data.G.unique(), key=str)
            n_tes = k * (k - 1) // 2
            rows = []
            for i in range(k):
                for j in range(i + 1, k):
                    u, pp = stats.mannwhitneyu(data.loc[data.G == lv[i], "Y"],
                                               data.loc[data.G == lv[j], "Y"])
                    rows.append({"Perbandingan": f"{lv[i]} vs {lv[j]}", "U": u,
                                 "p-value": pp, "p terkoreksi": min(pp * n_tes, 1.0)})
            st.dataframe(pd.DataFrame(rows).round(4), use_container_width=True)


# ==================================================================
# 18) MANN-WHITNEY U
# ==================================================================
def a_mwu(df):
    st.subheader("⚖️ Uji Mann-Whitney U (Non-Parametrik)")
    num = df.select_dtypes("number").columns.tolist()
    cats = df.select_dtypes(exclude="number").columns.tolist()
    if not num or not cats:
        st.warning("Butuh 1 variabel numerik + 1 variabel kelompok."); return

    y = st.selectbox("Variabel (numerik)", num)
    g = st.selectbox("Variabel kelompok", cats)
    lv = sorted(df[g].dropna().astype(str).unique())
    dua = st.multiselect("Pilih 2 kelompok", lv, default=lv[:2])

    if st.button(RUN, type="primary", use_container_width=True):
        if len(dua) != 2:
            st.error("Pilih tepat 2 kelompok."); return
        data = persiapkan(df, [y, g]); data.columns = ["Y", "G"]
        data["G"] = data["G"].astype(str)
        a = data.loc[data.G == dua[0], "Y"]; b = data.loc[data.G == dua[1], "Y"]
        u, p = stats.mannwhitneyu(a, b, alternative="two-sided")
        n1, n2 = len(a), len(b)
        mu_u, sd_u = n1 * n2 / 2, np.sqrt(n1 * n2 * (n1 + n2 + 1) / 12)
        z = (u - mu_u) / sd_u
        st.dataframe(pd.DataFrame({"n": [n1, n2], "Median": [a.median(), b.median()],
                                   "Mean Rank approx": [mu_u / n2, mu_u / n1]},
                                  index=dua).round(3))
        st.dataframe(pd.DataFrame({"Nilai": [u, z, p, abs(z) / np.sqrt(n1 + n2)]},
                                  index=["U", "Z", "p-value", "r (ukuran efek)"]).round(4))
        hasil_uji("Mann-Whitney U", u, p)


# ==================================================================
# 19) WILCOXON SIGNED-RANK
# ==================================================================
def a_wilcoxon(df):
    st.subheader("⚖️ Uji Wilcoxon Signed-Rank (Non-Parametrik)")
    num = df.select_dtypes("number").columns.tolist()
    if len(num) < 2:
        st.warning("Butuh 2 kolom numerik (pasangan pengukuran)."); return

    v1 = st.selectbox("Pengukuran 1 (sebelum)", num)
    v2 = st.selectbox("Pengukuran 2 (sesudah)", [c for c in num if c != v1])

    if st.button(RUN, type="primary", use_container_width=True):
        sub = df[[v1, v2]].dropna()
        w, p = stats.wilcoxon(sub[v1], sub[v2])
        d = (sub[v1] - sub[v2]); d = d[d != 0]
        n = len(d)
        z = (w - n * (n + 1) / 4) / np.sqrt(n * (n + 1) * (2 * n + 1) / 24)
        st.dataframe(pd.DataFrame(
            {"Nilai": [n, sub[v1].median(), sub[v2].median(), w, z, p,
                       abs(z) / np.sqrt(n)]},
            index=["n (selisih ≠ 0)", f"Median {v1}", f"Median {v2}",
                   "W", "Z", "p-value", "r (ukuran efek)"]).round(4))
        hasil_uji("Wilcoxon Signed-Rank", w, p)


# ==================================================================
# 20) FRIEDMAN
# ==================================================================
def a_friedman(df):
    st.subheader("⚖️ Uji Friedman (Non-Parametrik, ≥ 3 pengukuran berulang)")
    num = df.select_dtypes("number").columns.tolist()
    if len(num) < 3:
        st.warning("Butuh minimal 3 kolom numerik."); return

    cols = st.multiselect("Pilih ≥ 3 kondisi/pengukuran", num, default=num[:3])

    if st.button(RUN, type="primary", use_container_width=True):
        if len(cols) < 3:
            st.error("Pilih minimal 3 variabel."); return
        data = df[cols].dropna()
        chi_sq, p = stats.friedmanchisquare(*[data[c] for c in cols])
        n, k = data.shape
        st.markdown("#### Median per Kondisi")
        st.dataframe(data[cols].median().to_frame("Median").round(3), use_container_width=True)
        hasil_uji("Friedman Test", chi_sq, p)
        st.caption(f"Kendall's W (ukuran efek) = {chi_sq / (n * (k - 1)):.3f}")


# ==================================================================
# DISPATCH — DAFTAR SEMUA ANALISIS
# ==================================================================
DISPATCH = {
    "Regresi Linear (OLS)":                          a_regresi_linear,
    "Regresi Logistik Biner":                        a_logit_biner,
    "Regresi Logistik Multinomial":                  a_mnlogit,
    "Regresi Ordinal":                               a_regresi_ordinal,
    "Regresi Poisson (Data Hitungan)":               a_poisson,
    "ANOVA Satu Arah (One-Way)":                     a_anova1,
    "ANOVA Dua Arah (Two-Way)":                      a_anova2,
    "ANCOVA":                                        a_ancova,
    "MANOVA":                                        a_manova,
    "Uji t (Satu Sampel / Independen / Berpasangan)": a_ttest,
    "Uji Chi-Square (Independensi)":                 a_chisquare,
    "Korelasi (Pearson / Spearman / Kendall)":       a_korelasi,
    "Analisis Faktor (EFA)":                         a_faktor,
    "Analisis Komponen Utama (PCA)":                 a_pca,
    "Analisis Diskriminan (LDA)":                    a_lda,
    "K-Means Clustering":                            a_kmeans,
    "Kruskal-Wallis (Non-Parametrik)":               a_kruskal,
    "Mann-Whitney U (Non-Parametrik)":               a_mwu,
    "Wilcoxon Signed-Rank (Non-Parametrik)":         a_wilcoxon,
    "Friedman (Non-Parametrik)":                     a_friedman,
}

# ==================================================================
# ANTARMUKA UTAMA
# ==================================================================
st.title("📊 Aplikasi Pengolah Data & Analisis Statistik Inferensial")
st.markdown("Unggah data → pilih analisis → tekan **RUN** → hasil tampil di layar.")

with st.sidebar:
    st.header("1️⃣ Unggah Data")
    file = st.file_uploader(
        "CSV · XLS · XLSX · DBF · JSON · SAV · DTA · TXT · PARQUET",
        type=["csv", "xls", "xlsx", "xlsm", "dbf", "json", "sav",
              "dta", "txt", "tsv", "dat", "parquet", "pkl"])
    st.session_state["alpha"] = st.select_slider(
        "Taraf signifikansi (α)", options=[0.10, 0.05, 0.01], value=0.05)

if file is None:
    st.info("⬅️ Silakan unggah file data pada panel sidebar untuk memulai.")
    st.markdown("**20 analisis tersedia:** regresi (linear, logistik biner/multinomial, "
                "ordinal, Poisson), ANOVA (1 & 2 arah), ANCOVA, MANOVA, uji t, chi-square, "
                "korelasi, analisis faktor, PCA, diskriminan, K-means, Kruskal-Wallis, "
                "Mann-Whitney, Wilcoxon, Friedman.")
    st.stop()

raw = file.getvalue()
ext = os.path.splitext(file.name.lower())[1]

with st.spinner("Membaca data…"):
    if ext in (".xls", ".xlsx", ".xlsm"):
        sheets = pd.ExcelFile(io.BytesIO(raw)).sheet_names
        if len(sheets) > 1:
            with st.sidebar:
                sheet = st.selectbox("Pilih sheet Excel", sheets)
        else:
            sheet = sheets[0]
        df = baca_data(raw, file.name, sheet)
    else:
        df = baca_data(raw, file.name)

if st.sidebar.checkbox("Konversi otomatis kolom teks → numerik", value=True):
    df = konversi_numerik(df)

# ---------- PRATINJAU DATA ----------
tab1, tab2, tab3 = st.tabs(["🔍 Pratinjau Data", "ℹ️ Informasi Variabel", "📈 Statistik Deskriptif"])
with tab1:
    st.dataframe(df.head(200), use_container_width=True)
    st.caption(f"Menampilkan {min(200, len(df))} dari {len(df):,} baris × {df.shape[1]} kolom")
    st.download_button("⬇️ Unduh data yang dimuat (CSV)",
                       df.to_csv(index=False).encode("utf-8"),
                       "data_dimuat.csv", "text/csv")
with tab2:
    st.dataframe(pd.DataFrame({
        "Tipe Data": df.dtypes.astype(str),
        "Data Terisi": df.notna().sum(),
        "Data Kosong": df.isna().sum(),
        "Jumlah Unik": df.nunique()}), use_container_width=True)
with tab3:
    st.dataframe(df.describe(include="all").T.round(3), use_container_width=True)

# ---------- PILIH ANALISIS & RUN ----------
with st.sidebar:
    st.header("2️⃣ Pilih Analisis")
    pilihan = st.selectbox("Analisis Statistik Inferensial", list(DISPATCH.keys()))

st.divider()
try:
    DISPATCH[pilihan](df)
except Exception as e:
    st.error("Terjadi kesalahan saat menjalankan analisis:")
    st.exception(e)