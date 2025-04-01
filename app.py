
import streamlit as st
import pandas as pd
from io import BytesIO
import os
from datetime import date

# Ruta interna para guardar análisis previos
HISTORIAL_DIR = "historial"

# Crear carpeta si no existe
if not os.path.exists(HISTORIAL_DIR):
    os.makedirs(HISTORIAL_DIR)

# Cargar archivo de dotación fijo
@st.cache_data
def cargar_dotacion():
    return pd.read_excel("dotacion_fija.xlsx")

def cargar_archivo(nombre):
    archivo = st.file_uploader(f"Sube el archivo de {nombre}", type=["xlsx", "csv"])
    if archivo:
        if archivo.name.endswith(".csv"):
            return pd.read_csv(archivo)
        else:
            return pd.read_excel(archivo)
    return None

def limpiar_datos(dotacion_df, conteo_df, consumo_df):
    dotacion = dotacion_df[['SKU', 'DOTACIÓN']].dropna()
    dotacion['SKU'] = dotacion['SKU'].str.strip()

    conteo = conteo_df.iloc[2:, [1, 3]].copy()
    conteo.columns = ['SKU', 'Cantidad']
    conteo['Cantidad'] = pd.to_numeric(conteo['Cantidad'], errors='coerce')
    conteo = conteo.dropna(subset=['SKU'])
    conteo['SKU'] = conteo['SKU'].str.strip()

    consumo = consumo_df[['ID Parte', 'Cantidad', 'Articulo']].dropna()
    consumo['SKU'] = consumo['Articulo'].str.extract(r'(^\S+)', expand=False)
    consumo = consumo[['SKU', 'Cantidad', 'ID Parte']]
    consumo['SKU'] = consumo['SKU'].str.strip()

    return dotacion, conteo, consumo

def procesar(dotacion, conteo, consumo):
    conteo_agg = conteo.groupby('SKU', as_index=False).sum()
    conteo_agg.rename(columns={'Cantidad': 'Contada'}, inplace=True)

    consumo_agg = consumo.groupby('SKU', as_index=False).agg({'Cantidad': 'sum'})
    consumo_agg.rename(columns={'Cantidad': 'Usada'}, inplace=True)

    df = pd.merge(dotacion, conteo_agg, on='SKU', how='outer')
    df = pd.merge(df, consumo_agg, on='SKU', how='outer')
    df[['DOTACIÓN', 'Contada', 'Usada']] = df[['DOTACIÓN', 'Contada', 'Usada']].fillna(0)
    df['Diferencia'] = df['DOTACIÓN'] - (df['Contada'] + df['Usada'])

    consumo_ids = consumo.groupby('SKU')['ID Parte'].apply(lambda x: ', '.join(sorted(set(x)))).reset_index()
    consumo_ids.rename(columns={'ID Parte': 'Origen de la diferencia'}, inplace=True)
    df = pd.merge(df, consumo_ids, on='SKU', how='left')

    def diagnostico(row):
        dot, cont, usada, dif = row['DOTACIÓN'], row['Contada'], row['Usada'], row['Diferencia']
        origen = row['Origen de la diferencia']
        if dif == 0:
            return "OK"
        if cont > dot:
            return "Exceso en maleta"
        if cont + usada < dot:
            if usada == 0 and pd.isna(origen):
                return "Error de conteo"
            if usada > 0 and pd.isna(origen):
                return "Consumo no registrado"
            if usada > 0 and not pd.isna(origen):
                return "Consumo no repuesto"
        if cont < dot and usada == 0 and pd.isna(origen):
            return "Error de conteo"
        return "Revisión necesaria"

    def origen_diferencia(row):
        if not pd.isna(row['Origen de la diferencia']):
            return row['Origen de la diferencia']
        elif row['Usada'] > 0:
            return "No registrado"
        elif row['Contada'] > 0:
            return "Solo en conteo físico"
        else:
            return "Sin datos"

    df['Diagnóstico'] = df.apply(diagnostico, axis=1)
    df['Origen de la diferencia'] = df.apply(origen_diferencia, axis=1)
    return df[['SKU', 'DOTACIÓN', 'Contada', 'Usada', 'Diferencia', 'Diagnóstico', 'Origen de la diferencia']]

# Interfaz principal
st.title("🔧 Analizador de Maletas Técnicas")

menu = st.sidebar.radio("Menú", ["📊 Nuevo análisis", "📂 Historial"])

if menu == "📊 Nuevo análisis":
    st.subheader("📋 Información del análisis")

    tecnico = st.selectbox("Técnico responsable", ["Francisco Javier", "Rigoberto"])
    fecha_inicio = st.date_input("Desde:", value=date.today())
    fecha_fin = st.date_input("Hasta:", value=date.today())

    st.divider()

    dotacion_df = cargar_dotacion()
    conteo_df = cargar_archivo("conteo físico")
    consumo_df = cargar_archivo("consumo registrado")

    if conteo_df is not None and consumo_df is not None:
        dotacion, conteo, consumo = limpiar_datos(dotacion_df, conteo_df, consumo_df)
        resultado = procesar(dotacion, conteo, consumo)

        st.success("✅ Análisis completado")
        st.dataframe(resultado)

        nombre_archivo = f"{tecnico.lower().replace(' ', '_')}_{fecha_inicio}_a_{fecha_fin}.xlsx"
        path_archivo = os.path.join(HISTORIAL_DIR, nombre_archivo)

        with pd.ExcelWriter(path_archivo, engine='openpyxl') as writer:
            resultado.to_excel(writer, index=False, sheet_name="Análisis")

        with BytesIO() as output:
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                resultado.to_excel(writer, index=False, sheet_name="Análisis")
            st.download_button("📥 Descargar resultado en Excel", output.getvalue(), file_name=nombre_archivo)

elif menu == "📂 Historial":
    st.subheader("📁 Historial de análisis previos")

    archivos = sorted(os.listdir(HISTORIAL_DIR))
    seleccion = st.selectbox("Selecciona un archivo:", archivos)

    if seleccion:
        df_hist = pd.read_excel(os.path.join(HISTORIAL_DIR, seleccion))
        st.write(f"Vista previa de: **{seleccion}**")
        st.dataframe(df_hist)

        with open(os.path.join(HISTORIAL_DIR, seleccion), "rb") as f:
            st.download_button("📥 Descargar este análisis", f, file_name=seleccion)
