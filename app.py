
import streamlit as st
import pandas as pd
from io import BytesIO
import os
from datetime import date
from PIL import Image

st.set_page_config(page_title="SPINTEGRA - Gestión de Maletas Técnicas", layout="wide")

# Colores personalizados
COLOR_OK = "#28a745"
COLOR_FALTANTE = "#ffc107"
COLOR_EXCESO = "#dc3545"
COLOR_TEXTO = "#014F96"
COLOR_FONDO = "#FFFFFF"

# Logo y encabezado
col1, col2 = st.columns([0.2, 0.8])
with col1:
    st.image("logo_spintegra.png", width=180)
with col2:
    st.markdown(f"<h1 style='color:{COLOR_TEXTO};'>SPINTEGRA – Gestión de Maletas Técnicas</h1>", unsafe_allow_html=True)
    st.write("Control inteligente de inventario y consumo técnico")

# Menú lateral
menu = st.sidebar.radio("Navegación", [
    "Inicio",
    "Análisis de maleta",
    "Historial de análisis",
    "Ayuda y guía de uso"

DOTACION_PATH = "dotacion_fija.xlsx"
ADQ_DIR = "historial_adquisicion"
ANALISIS_DIR = "historial"

@st.cache_data
def cargar_dotacion():
    return pd.read_excel(DOTACION_PATH)

def generar_resumen(df):
    ok = df[df["Estado"] == "OK"].shape[0]
    faltantes = df[df["Estado"] == "Faltante"].shape[0]
    excesos = df[df["Estado"] == "Exceso"].shape[0]
    no_en_dotacion = df[df["Estado"] == "No en dotación"].shape[0]
    total = df["Contadas"].sum()
    return ok, faltantes, excesos, no_en_dotacion, total

