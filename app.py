
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
    "Adquisición por escáner",
    "Historial de adquisiciones",
    "Análisis de maleta",
    "Historial de análisis",
    "Ayuda y guía de uso"
])

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

if menu == "Adquisición por escáner":
    st.subheader("Adquisición de inventario con escáner")

    tecnico = st.selectbox("Selecciona el técnico responsable", ["Francisco Javier", "Rigoberto"])
    fecha = st.date_input("Fecha del inventario", value=date.today())
    dotacion = cargar_dotacion()

    st.info("Escanea los códigos uno por uno. El sistema suma automáticamente las cantidades.")

    if "conteo" not in st.session_state:
        st.session_state.conteo = {}

    
if "clear_input" in st.session_state and st.session_state["clear_input"]:
    st.session_state["clear_input"] = False
    sku_input = st.text_input("Escanea aquí el código", value="", key="sku_input", label_visibility="visible")
else:
    sku_input = st.text_input("Escanea aquí el código", key="sku_input", label_visibility="visible")


    
if sku_input and sku_input != st.session_state.get("last_scanned", ""):
    sku = sku_input.strip().upper()
    st.session_state.conteo[sku] = st.session_state.conteo.get(sku, 0) + 1
    st.session_state.last_scanned = sku
    st.session_state["clear_input"] = True

        sku = sku_input.strip().upper()
        st.session_state.conteo[sku] = st.session_state.conteo.get(sku, 0) + 1
        st.experimental_set_query_params()  # Forzar limpieza visual
        # eliminado experimental_rerun

    if st.session_state.get("conteo"):
        conteo_df = pd.DataFrame(list(st.session_state.conteo.items()), columns=["SKU", "Contadas"])
        df = pd.merge(conteo_df, dotacion[["SKU", "DOTACIÓN"]], on="SKU", how="left")
        df["DOTACIÓN"] = df["DOTACIÓN"].fillna(0).astype(int)
        df["Diferencia"] = df["Contadas"] - df["DOTACIÓN"]

        def clasificar(row):
            if row["DOTACIÓN"] == 0:
                return "No en dotación"
            elif row["Contadas"] == row["DOTACIÓN"]:
                return "OK"
            elif row["Contadas"] < row["DOTACIÓN"]:
                return "Faltante"
            else:
                return "Exceso"

        df["Estado"] = df.apply(clasificar, axis=1)

        st.markdown("### Resumen del inventario")
        ok, faltantes, excesos, no_en_dotacion, total = generate_summary = generate_summary = generar_resumen(df)
        st.success(f"✔️ OK: {ok} | 🟠 Faltantes: {faltantes} | 🔴 Excesos: {excesos} | ❓ No en dotación: {no_en_dotacion} | Total unidades: {total}")

        st.markdown("### Revisión del conteo (editable)")
        
        df_display = df.copy()
        for i, sku in enumerate(df_display["SKU"]):
            col1, col2, col3, col4, col5, col6 = st.columns([2, 2, 2, 2, 2, 1])
            with col1: st.write(sku)
            with col2: st.write(df_display.loc[i, "Contadas"])
            with col3: st.write(df_display.loc[i, "DOTACIÓN"])
            with col4: st.write(df_display.loc[i, "Diferencia"])
            with col5: st.write(df_display.loc[i, "Estado"])
            with col6:
                if st.button("🗑️", key=f"delete_{sku}"):
                    del st.session_state.conteo[sku]
                    # eliminado experimental_rerun
        st.markdown("Puedes editar la cantidad directamente en la tabla si lo prefieres.")
        edit_df = st.data_editor(df[["SKU", "Contadas", "DOTACIÓN", "Diferencia", "Estado"]],
    
                                 use_container_width=True, num_rows="dynamic")

        if st.button("Finalizar adquisición y guardar"):
            export = edit_df[["SKU", "Contadas"]].rename(columns={"Contadas": "Cantidad"})
            filename = f"adquisicion_{tecnico.lower().replace(' ', '_')}_{fecha}.xlsx"
            path = os.path.join(ADQ_DIR, filename)
            export.to_excel(path, index=False)

            st.success(f"Inventario guardado como {filename}")
            st.download_button("Descargar archivo", data=export.to_excel(index=False, engine='openpyxl'),
                               file_name=filename, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
