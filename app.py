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
        "Nombre del paciente","Edad","Número de expediente","Número de contacto","Nombre del responsable",
        "Contacto de responsable","Servicio","Fecha de ingreso","Diagnóstico de ingreso",
        "Fecha de egreso","Diagnóstico de egreso","Llamada de seguimiento",
        "Médico que realiza seguimiento","RESUMEN DE SEGUIMIENTO"
    ]

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

        # 1) igualdad exacta normalizada
        for syn in syns:
            if syn in norm_cols:
                return norm_cols[syn]
        # 2) inclusión (laxto)
        for syn in syns:
            for nc, orig in norm_cols.items():
                if syn and (syn in nc or nc in syn):
                    return orig
        # 3) intersección de tokens
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

    # Nombre completo del paciente
    EXCLUDE_TOKENS = ["responsable", "medico", "médico", "telefono", "teléfono", "whatsapp"]
    name_candidates = []
    for col in df.columns:
        nc = normalize(col)
        if any(tok in nc for tok in ["nombre", "nombres", "apellido", "apellidos", "paciente"]):
            if not any(ex in nc for ex in EXCLUDE_TOKENS):
                name_candidates.append(col)

    priority = [
        "primer nombre", "segundo nombre", "1er nombre", "2do nombre", "nombres", "nombre",
        "primer apellido", "segundo apellido", "1er apellido", "2do apellido", "apellidos", "apellido",
        "nombre del paciente", "paciente"
    ]
    final_name_cols = []
    for patt in priority:
        for nc, orig in norm_cols.items():
            if patt in nc and orig in name_candidates and orig not in final_name_cols:
                final_name_cols.append(orig)
    if not final_name_cols:
        final_name_cols = name_candidates

    if final_name_cols:
        df["Nombre del paciente"] = df.apply(lambda r: join_tokens(r, final_name_cols), axis=1)
    else:
        if "Nombre del paciente" not in df.columns:
            df["Nombre del paciente"] = ""

    # Reglas fijas
    if "Nombre Responsable" in df.columns:
        nombre_responsable_series = df["Nombre Responsable"]
    else:
        nombre_responsable_series = ""

    if "Fecha egreso" in df.columns:
        fecha_egreso_series = as_date(df["Fecha egreso"])
    else:
        fecha_egreso_series = ""

    # Diferenciación entre "Número de contacto" y "Contacto de responsable"
    if "Teléfono Paciente" in df.columns:
        numero_contacto_series = df["Teléfono Paciente"]
    else:
        numero_contacto_series = ""
    
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

    return final_df

# =========================
# UI
# =========================
st.title("🧹 Reordenamiento de CSV para las altas de hospitales")
st.write("Sube tu **CSV**, lo normalizo y ordeno según tu regla. Descarga el resultado listo para usar.")

with st.expander("Opciones de lectura"):
    col1, col2, col3 = st.columns(3)
    encoding = col1.selectbox("Codificación", ["utf-8", "latin1", "utf-16"], index=0)
    sep_choice = col2.selectbox("Separador", ["auto", ",", ";", "\\t"], index=0)
    decimal = col3.selectbox("Separador decimal", [".", ","], index=0)

uploaded = st.file_uploader("Sube tu archivo (.csv)", type=["csv"])

if uploaded:
    # Determinar separador y engine
    if sep_choice == "auto":
        sep_arg, engine = None, "python"
    else:
        sep_arg = "\t" if sep_choice == "\\t" else sep_choice
        engine = "python" if sep_arg in [";", "\t"] else "c"

    try:
        df_in = pd.read_csv(uploaded, encoding=encoding, sep=sep_arg, decimal=decimal, engine=engine)
        st.success(f"Archivo leído correctamente. Filas: {len(df_in):,}  |  Columnas: {len(df_in.columns):,}")
        with st.expander("Vista previa del CSV original (primeras 10 filas)", expanded=False):
            st.dataframe(df_in.head(10), use_container_width=True)

        # Procesar
        df_out = ordenar_csv(df_in)

        st.subheader("Resultado (primeras 20 filas)")
        st.dataframe(df_out.head(20), use_container_width=True)

        # Descarga
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_name = f"pacientes_ordenado_14_columnas_{stamp}.csv"
        buffer = io.StringIO()
        df_out.to_csv(buffer, index=False, encoding="utf-8-sig")
        st.download_button(
            label="⬇️ Descargar CSV resultado",
            data=buffer.getvalue().encode("utf-8-sig"),
            file_name=out_name,
            mime="text/csv"
        )

        # Log informativo
        st.info(
            "‘Nombre del responsable’ ← ‘Nombre Responsable’  \n"
            "‘Fecha de egreso’ ← ‘Fecha egreso’ (DD/MM/YYYY)  \n"
            "‘Nombre del paciente’ se construye si hay nombres/apellidos  \n"
            "Diagnósticos: limpieza de códigos CIE-10"
        )

    except Exception as e:
        st.error("No pude leer o procesar el CSV. Revisa el separador, codificación o contenido.")
        st.exception(e)
else:
    st.warning("Carga un archivo CSV para iniciar.")
