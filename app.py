
import streamlit as st
import pandas as pd
from io import BytesIO
import os
from datetime import date
from PIL import Image

# Configuración de la página
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
    total = df["Contadas"].sum()
    return ok, faltantes, excesos, total

if menu == "Inicio":
    st.subheader("Bienvenido")
    st.write("Utiliza el menú lateral para acceder a las funcionalidades.")
    st.success("¿Nuevo por aquí? Revisa la sección 'Ayuda y guía de uso' para empezar.")

elif menu == "Adquisición por escáner":
    st.subheader("Adquisición de inventario con escáner")

    tecnico = st.selectbox("Selecciona el técnico responsable", ["Francisco Javier", "Rigoberto"])
    fecha = st.date_input("Fecha del inventario", value=date.today())
    dotacion = cargar_dotacion()

    st.info("Escanea los códigos uno por uno. El sistema suma automáticamente las cantidades.")

    sku_input = st.text_input("Campo de escaneo activo (coloca el cursor aquí)", "")
    if "input_cleared" in st.session_state and st.session_state["input_cleared"]:
        st.session_state["input_cleared"] = False
        st.experimental_set_query_params()  # Resetea input indirectamente
        st.stop()

    if "conteo" not in st.session_state:
        st.session_state.conteo = {}

    if sku_input:
        sku = sku_input.strip().upper()
        st.session_state.conteo[sku] = st.session_state.conteo.get(sku, 0) + 1
        # Eliminado st.experimental_rerun() para evitar errores
        st.session_state["last_scanned"] = sku_input
        st.session_state["input_cleared"] = True

    if st.session_state.conteo:
        conteo_df = pd.DataFrame(list(st.session_state.conteo.items()), columns=["SKU", "Contadas"])
        df = pd.merge(conteo_df, dotacion[["SKU", "DOTACIÓN"]], on="SKU", how="left").fillna(0)
        df["DOTACIÓN"] = df["DOTACIÓN"].astype(int)
        df["Diferencia"] = df["Contadas"] - df["DOTACIÓN"]

        def clasificar(row):
            if row["Contadas"] == row["DOTACIÓN"]:
                return "OK"
            elif row["Contadas"] < row["DOTACIÓN"]:
                return "Faltante"
            else:
                return "Exceso"

        df["Estado"] = df.apply(clasificar, axis=1)

        st.markdown("### Resumen del inventario")
        ok, faltantes, excesos, total = generar_resumen(df)
        st.success(f"✔️ OK: {ok} | 🟠 Faltantes: {faltantes} | 🔴 Excesos: {excesos} | Total unidades: {total}")

        st.markdown("### Revisión del conteo (editable)")
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

elif menu == "Historial de adquisiciones":
    st.subheader("Historial de adquisiciones")
    archivos = sorted(os.listdir(ADQ_DIR))
    seleccion = st.selectbox("Selecciona un archivo:", archivos)
    if seleccion:
        df_hist = pd.read_excel(os.path.join(ADQ_DIR, seleccion))
        st.write(f"Vista previa de: **{seleccion}**")
        st.dataframe(df_hist, use_container_width=True)
        with open(os.path.join(ADQ_DIR, seleccion), "rb") as f:
            st.download_button("Descargar este archivo", f, file_name=seleccion)

elif menu == "Análisis de maleta":
    st.subheader("Análisis de maleta técnica")

    tecnico = st.selectbox("Técnico responsable", ["Francisco Javier", "Rigoberto"])
    fecha_inicio = st.date_input("Desde:", value=date.today())
    fecha_fin = st.date_input("Hasta:", value=date.today())
    conteo_file = st.file_uploader("Sube el archivo de conteo físico", type=["xlsx"])
    consumo_file = st.file_uploader("Sube el archivo de consumo registrado", type=["xlsx", "csv"])

    if conteo_file and consumo_file:
        dotacion = cargar_dotacion()
        conteo = pd.read_excel(conteo_file)
        conteo = conteo[["SKU", "Cantidad"]].groupby("SKU").sum().reset_index()
        conteo.rename(columns={"Cantidad": "Contada"}, inplace=True)

        consumo = pd.read_excel(consumo_file) if consumo_file.name.endswith("xlsx") else pd.read_csv(consumo_file)
        consumo["SKU"] = consumo["Articulo"].str.extract(r'(^\S+)', expand=False).str.strip()
        consumo_agg = consumo.groupby("SKU")["Cantidad"].sum().reset_index()
        consumo_agg.rename(columns={"Cantidad": "Usada"}, inplace=True)

        consumo_ids = consumo.groupby("SKU")["ID Parte"].apply(lambda x: ', '.join(sorted(set(x)))).reset_index()
        consumo_ids.rename(columns={"ID Parte": "Origen de la diferencia"}, inplace=True)

        df = pd.merge(dotacion, conteo, on="SKU", how="outer")
        df = pd.merge(df, consumo_agg, on="SKU", how="outer")
        df = pd.merge(df, consumo_ids, on="SKU", how="left")
        df.fillna(0, inplace=True)
        df["Diferencia"] = df["DOTACIÓN"] - (df["Contada"] + df["Usada"])

        def diagnostico(row):
            if row["Diferencia"] == 0:
                return "OK"
            if row["Contada"] > row["DOTACIÓN"]:
                return "Exceso en maleta"
            if row["Contada"] + row["Usada"] < row["DOTACIÓN"]:
                if row["Usada"] == 0:
                    return "Error de conteo"
                elif row["Usada"] > 0 and row["Origen de la diferencia"] == 0:
                    return "Consumo no registrado"
                else:
                    return "Consumo no repuesto"
            return "Revisión necesaria"

        df["Diagnóstico"] = df.apply(diagnostico, axis=1)
        df["Origen de la diferencia"] = df["Origen de la diferencia"].replace(0, "No registrado")

        resumen = df[df["Diferencia"] != 0]
        st.success(f"Total diferencias: {len(resumen)} | Unidades afectadas: {int(resumen['Diferencia'].abs().sum())}")

        st.dataframe(df[["SKU", "DOTACIÓN", "Contada", "Usada", "Diferencia", "Diagnóstico", "Origen de la diferencia"]],
                     use_container_width=True)

        filename = f"analisis_{tecnico.lower().replace(' ', '_')}_{fecha_inicio}_a_{fecha_fin}.xlsx"
        df_export = df[["SKU", "DOTACIÓN", "Contada", "Usada", "Diferencia", "Diagnóstico", "Origen de la diferencia"]]
        df_export.to_excel(os.path.join(ANALISIS_DIR, filename), index=False)

        st.download_button("Descargar resultado en Excel", data=df_export.to_excel(index=False, engine='openpyxl'),
                           file_name=filename, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

elif menu == "Historial de análisis":
    st.subheader("Historial de análisis de maletas")
    archivos = sorted(os.listdir(ANALISIS_DIR))
    seleccion = st.selectbox("Selecciona un análisis:", archivos)
    if seleccion:
        df_hist = pd.read_excel(os.path.join(ANALISIS_DIR, seleccion))
        st.write(f"Vista previa de: **{seleccion}**")
        st.dataframe(df_hist, use_container_width=True)
        with open(os.path.join(ANALISIS_DIR, seleccion), "rb") as f:
            st.download_button("Descargar este análisis", f, file_name=seleccion)

elif menu == "Ayuda y guía de uso":
    st.subheader("Guía de uso de la aplicación")
    st.markdown("""
**¿Cómo funciona la adquisición por escáner?**  
Escanea los códigos de producto con tu lector. Cada lectura incrementa 1 unidad en la tabla. Puedes corregir manualmente antes de finalizar.

**¿Qué significan los colores?**  
- 🟢 Verde: cantidad correcta  
- 🟠 Naranja: faltan unidades  
- 🔴 Rojo: hay más de la dotación

**¿Cómo se hace el análisis de maleta?**  
Sube el conteo físico y el consumo. El sistema calculará diferencias y te dirá qué reponer o revisar.

**¿Qué archivos puedo usar?**  
- Excel (.xlsx) o CSV  
- Columnas requeridas: SKU y Cantidad para conteo, SKU y Cantidad y Articulo para consumo

**¿Dónde se guardan los análisis?**  
En la sección de historial, puedes ver todos los análisis anteriores y descargarlos.
""")
