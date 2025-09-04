# app.py
import streamlit as st
import pandas as pd
import unicodedata
import re
import io
from datetime import datetime

st.set_page_config(page_title="Ordenador de CSV", page_icon="🧹", layout="wide")

st.sidebar.title("ℹ️ Instrucciones")
st.sidebar.markdown("""
1. **Descargar el reporte de SIS "Tabulador de egresos"** en formato excel
2. **Abrir el archivo** Y guardarlo en formato CSV cambiando el nombre y colocando el formato del CSV en UTF-8
3. **Subir el archivo CSV**
4. **Descarga** el archivo procesado con el botón de descarga.
""")

# =========================
# Utilidades de tu script
# =========================
def normalize(s: str) -> str:
    s = str(s)
    s = s.strip().lower()
    s = ''.join(c for c in unicodedata.normalize('NFKD', s)
                if not unicodedata.combining(c))
    s = re.sub(r'[^a-z0-9\s#]+', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def join_tokens(row, cols):
    parts = []
    for c in cols:
        if c in row and pd.notna(row[c]):
            txt = str(row[c]).strip()
            if txt and txt.lower() != "nan":
                parts.append(txt)
    return re.sub(r"\s+", " ", " ".join(parts)).strip()

def as_date(series):
    # Convierte a fecha en formato DD/MM/YYYY
    dt = pd.to_datetime(series, dayfirst=True, errors="coerce")
    out = dt.dt.strftime("%d/%m/%Y")
    return out.fillna("")

def clean_diagnosis(text: str) -> str:
    # Elimina códigos CIE-10 y limpia paréntesis/espacios
    if pd.isna(text):
        return ""
    s = str(text)
    s = re.sub(r'\b[A-Z]\d{2}(?:\.[0-9A-Z]{1,2})?\b', '', s)
    s = re.sub(r'\(\s*\)', '', s)
    s = re.sub(r'\s{2,}', ' ', s).strip(" -;,")
    return s.strip()

# =========================
# Tu lógica principal
# =========================
def ordenar_csv(df: pd.DataFrame) -> pd.DataFrame:
    TARGET_ORDER = [
        "Nombre del paciente", "Edad", "Número de expediente", "Número de contacto", "Nombre del responsable",
        "Contacto de responsable", "Servicio", "Fecha de ingreso", "Diagnóstico de ingreso",
        "Fecha de egreso", "Diagnóstico de egreso", "Llamada de seguimiento",
        "Médico que realiza seguimiento", "RESUMEN DE SEGUIMIENTO"
    ]

    norm_cols = {normalize(c): c for c in df.columns}

    # Mostrar las columnas disponibles para depuración
    st.write("Columnas disponibles en el archivo CSV:")
    st.write(list(df.columns))

    # Normalización y ajuste de las columnas
    def find_source_col(target_name):
        if target_name not in synonyms:
            return None
        syns = [normalize(s) for s in synonyms[target_name]]

        # 1) Igualdad exacta normalizada
        for syn in syns:
            if syn in norm_cols:
                return norm_cols[syn]
        # 2) Inclusión (laxto)
        for syn in syns:
            for nc, orig in norm_cols.items():
                if syn and (syn in nc or nc in syn):
                    return orig
        # 3) Intersección de tokens
        best, score = None, 0
        for nc, orig in norm_cols.items():
            for syn in syns:
                toks_syn = set(syn.split())
                toks_nc = set(nc.split())
                inter = len(toks_syn & toks_nc)
                if inter > score:
                    score = inter
                    best = orig
        return best

    # Asignación de contacto de paciente y responsable
    if "Teléfono Paciente" in df.columns:
        numero_contacto_series = df["Teléfono Paciente"]
    else:
        numero_contacto_series = ""
    
    if "Teléfono Responsable" in df.columns:
        contacto_responsable_series = df["Teléfono Responsable"]
    else:
        contacto_responsable_series = ""

    # Creación del DataFrame final con las columnas ordenadas
    final_df = pd.DataFrame()
    for tgt in TARGET_ORDER:
        if tgt == "Nombre del paciente":
            final_df[tgt] = df["Nombre del paciente"]; continue
        if tgt == "Número de contacto":
            final_df[tgt] = numero_contacto_series; continue
        if tgt == "Contacto de responsable":
            final_df[tgt] = contacto_responsable_series; continue
        # Continuar asignando valores a las demás columnas de manera similar...
    
    # Reorganización final
    final_df = final_df.reindex(columns=TARGET_ORDER)
    return final_df

# =========================
# UI
# =========================
st.title("🧹 Reordenamiento de CSV para las altas de hospitales")
st.write("Sube tu archivo CSV para que lo reordenemos y limpiemos.")

uploaded_file = st.file_uploader("Cargar archivo CSV", type=["csv"])

if uploaded_file:
    try:
        # Leer el archivo CSV
        df = pd.read_csv(uploaded_file)
        st.write(f"Archivo cargado con {len(df)} filas y {len(df.columns)} columnas.")
        
        # Llamar la función para procesar el archivo
        df_processed = ordenar_csv(df)

        # Mostrar las primeras filas del archivo procesado
        st.subheader("Vista previa del archivo procesado:")
        st.write(df_processed.head())

        # Botón para descargar el archivo procesado
        st.download_button(
            label="Descargar archivo procesado",
            data=df_processed.to_csv(index=False).encode("utf-8"),
            file_name="archivo_procesado.csv",
            mime="text/csv"
        )
    except Exception as e:
        st.error(f"Ocurrió un error: {e}")
