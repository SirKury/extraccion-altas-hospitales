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

    # Sinónimos de las columnas
    synonyms = {
        "Edad": ["edad", "anos", "años"],
        "Número de expediente": [
            "numero de expediente", "n de expediente", "n expediente", "no expediente",
            "expediente", "n expediente clinico", "nº expediente", "num expediente"
        ],
        "Número de contacto": [
            "numero de contacto", "telefono", "teléfono", "celular", "whatsapp",
            "contacto", "telefono responsable", "tel responsable", "tel paciente", "telefono paciente"
        ],
        "Servicio": ["servicio", "area", "área", "departamento", "unidad", "servicio hospitalario"],
        "Fecha de ingreso": [
            "fecha de ingreso", "ingreso", "fecha ingreso", "f ingreso", "fecha de admision", "admision", "admisión"
        ],
        "Diagnóstico de ingreso": [
            "diagnostico de ingreso", "dx ingreso", "diagnostico ingreso", "diagnóstico de ingreso"
        ],
        "Diagnóstico de egreso": [
            "diagnostico de egreso", "dx egreso", "diagnostico egreso", "diagnóstico de egreso"
        ],
        "Llamada de seguimiento": [
            "llamada de seguimiento", "seguimiento", "llamada", "contacto seguimiento", "follow up"
        ],
        "Médico que realiza seguimiento": [
            "medico que realiza seguimiento", "médico que realiza seguimiento",
            "medico seguimiento", "médico seguimiento", "medico responsable", "doctor seguimiento",
            "quien realiza seguimiento"
        ],
        "RESUMEN DE SEGUIMIENTO": [
            "resumen de seguimiento", "nota de seguimiento", "observaciones", "comentarios",
            "plan", "resumen"
        ],
    }

    norm_cols = {normalize(c): c for c in df.columns}

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

    # Reglas fijas
    if "Nombre Responsable" in df.columns:
        nombre_responsable_series = df["Nombre Responsable"]
    else:
        nombre_responsable_series = ""

    if "Fecha egreso" in df.columns:
        fecha_egreso_series = as_date(df["Fecha egreso"])
    else:
        fecha_egreso_series = ""

    # Teléfono prioritario (responsable > paciente > cualquiera)
    tel_candidates = []
    for col in df.columns:
        if any(t in normalize(col) for t in ["telefono", "teléfono", "whatsapp", "contacto"]):
            tel_candidates.append(col)
    resp_cols = [c for c in tel_candidates if "responsable" in normalize(c)]
    pac_cols  = [c for c in tel_candidates if "paciente" in normalize(c)]
    
    # Asignación de número de contacto (paciente y responsable)
    if "Teléfono Paciente" in df.columns:
        numero_contacto_series = df["Teléfono Paciente"]
    else:
        numero_contacto_series = ""
    
    # Asignación de contacto del responsable
    if "Teléfono Responsable" in df.columns:
        contacto_responsable_series = df["Teléfono Responsable"]
    else:
        contacto_responsable_series = ""

    # Construcción final
    final_df = pd.DataFrame()
    for tgt in [
        "Nombre del paciente","Edad","Número de expediente","Número de contacto","Nombre del responsable",
        "Contacto de responsable","Servicio","Fecha de ingreso","Diagnóstico de ingreso",
        "Fecha de egreso","Diagnóstico de egreso","Llamada de seguimiento",
        "Médico que realiza seguimiento","RESUMEN DE SEGUIMIENTO"
    ]:
        if tgt == "Nombre del paciente":
            final_df[tgt] = df["Nombre del paciente"]; continue
        if tgt == "Nombre del responsable":
            final_df[tgt] = nombre_responsable_series if isinstance(nombre_responsable_series, pd.Series) else ""; continue
        if tgt == "Fecha de egreso":
            final_df[tgt] = fecha_egreso_series if isinstance(fecha_egreso_series, pd.Series) else ""; continue
        if tgt == "Número de contacto":
            final_df[tgt] = numero_contacto_series if isinstance(numero_contacto_series, pd.Series) else ""; continue
        if tgt == "Contacto de responsable":
            final_df[tgt] = contacto_responsable_series if isinstance(contacto_responsable_series, pd.Series) else ""; continue

        src = find_source_col(tgt)
        if src and src in df.columns:
            if tgt == "Fecha de ingreso":
                final_df[tgt] = as_date(df[src])
            elif tgt in ["Diagnóstico de ingreso", "Diagnóstico de egreso"]:
                final_df[tgt] = df[src].apply(clean_diagnosis)
            else:
                final_df[tgt] = df[src]
        else:
            if tgt in ["Diagnóstico de ingreso", "Diagnóstico de egreso"]:
                guesses = [c for c in df.columns if "diagnost" in normalize(c)]
                final_df[tgt] = df[guesses[0]].apply(clean_diagnosis) if guesses else ""
            else:
                final_df[tgt] = ""

    # Aquí es donde debes reordenar las columnas según TARGET_ORDER
    final_df = final_df.reindex(columns=TARGET_ORDER)

    return final_df

# =========================
# UI
# =========================
st.title("🧹 Reordenamiento de CSV")
st.subheader("Sube tu archivo CSV para reordenarlo y limpiarlo")

uploaded_file = st.file_uploader("Cargar archivo CSV", type=["csv"])

if uploaded_file:
    try:
        df = pd.read_csv(uploaded_file)

        st.write(f"Archivo cargado con {len(df)} filas y {len(df.columns)} columnas.")
        
        # Llamar a la función que reordenará el CSV
        df_processed = ordenar_csv(df)

        # Mostrar un preview del archivo procesado
        st.subheader("Vista previa del archivo procesado:")
        st.write(df_processed.head())

        # Botón de descarga
        st.download_button(
            label="Descargar archivo procesado",
            data=df_processed.to_csv(index=False).encode("utf-8"),
            file_name="archivo_procesado.csv",
            mime="text/csv"
        )
    except Exception as e:
        st.error(f"Ocurrió un error: {e}")
