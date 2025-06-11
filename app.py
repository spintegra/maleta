import streamlit as st
import pandas as pd
from io import BytesIO
import os
from datetime import date, datetime
import traceback
from typing import Optional, Tuple, Dict, Any
import warnings
warnings.filterwarnings('ignore')

# Configuración de la página
st.set_page_config(
    page_title="Analizador de Maletas Técnicas",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Constantes
HISTORIAL_DIR = "historial"
COLUMNAS_ESPERADAS = {
    'dotacion': ['SKU', 'DOTACIÓN', 'CAJA', 'SECCION', 'Nº ORDEN'],
    'conteo': ['SKU', 'Cantidad'],
    'consumo': ['ID Parte', 'Cantidad', 'Articulo']
}

# Crear directorio de historial
os.makedirs(HISTORIAL_DIR, exist_ok=True)

@st.cache_data
def cargar_dotacion() -> Optional[pd.DataFrame]:
    """Carga el archivo de dotación fija con manejo de errores mejorado."""
    try:
        if not os.path.exists("dotacion_fija.xlsx"):
            st.error("❌ No se encontró el archivo 'dotacion_fija.xlsx'. Asegúrate de que esté en el directorio raíz.")
            return None
        
        df = pd.read_excel("dotacion_fija.xlsx")
        
        # Validar columnas requeridas
        columnas_faltantes = [col for col in COLUMNAS_ESPERADAS['dotacion'] if col not in df.columns]
        if columnas_faltantes:
            st.error(f"❌ El archivo dotacion_fija.xlsx no tiene las columnas: {', '.join(columnas_faltantes)}")
            return None
            
        st.success(f"✅ Dotación fija cargada: {len(df)} elementos")
        return df
        
    except Exception as e:
        st.error(f"❌ Error cargando dotación fija: {str(e)}")
        return None

def validar_archivo_conteo(df: pd.DataFrame) -> bool:
    """Valida que el archivo de conteo tenga la estructura correcta."""
    if df is None or df.empty:
        return False
    
    # Verificar que tenga al menos 3 filas y 4 columnas
    if df.shape[0] < 3 or df.shape[1] < 4:
        st.error("❌ El archivo de conteo debe tener al menos 3 filas y 4 columnas (A, B, C, D)")
        return False
    
    return True

def validar_archivo_consumo(df: pd.DataFrame) -> bool:
    """Valida que el archivo de consumo tenga las columnas necesarias."""
    if df is None or df.empty:
        return False
    
    columnas_faltantes = [col for col in COLUMNAS_ESPERADAS['consumo'] if col not in df.columns]
    if columnas_faltantes:
        st.error(f"❌ El archivo de consumo no tiene las columnas: {', '.join(columnas_faltantes)}")
        return False
    
    return True

def cargar_archivo(nombre: str, tipo: str) -> Optional[pd.DataFrame]:
    """Carga y valida archivos con mejor manejo de errores."""
    archivo = st.file_uploader(
        f"📁 Sube el archivo de {nombre}", 
        type=["xlsx", "csv"],
        help=f"Formatos permitidos: Excel (.xlsx) o CSV (.csv)"
    )
    
    if archivo is None:
        return None
    
    try:
        # Leer archivo
        if archivo.name.endswith(".csv"):
            df = pd.read_csv(archivo, encoding='utf-8')
        else:
            df = pd.read_excel(archivo)
        
        # Validar según el tipo
        if tipo == 'conteo' and not validar_archivo_conteo(df):
            return None
        elif tipo == 'consumo' and not validar_archivo_consumo(df):
            return None
        
        st.success(f"✅ Archivo {nombre} cargado correctamente: {df.shape[0]} filas, {df.shape[1]} columnas")
        
        # Mostrar preview opcional
        if st.checkbox(f"👁️ Vista previa de {nombre}", key=f"preview_{tipo}"):
            st.dataframe(df.head(10), use_container_width=True)
        
        return df
        
    except Exception as e:
        st.error(f"❌ Error cargando {nombre}: {str(e)}")
        st.code(traceback.format_exc())
        return None

def limpiar_datos(dotacion_df: pd.DataFrame, conteo_df: pd.DataFrame, consumo_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Limpia y procesa los datos con mejor manejo de errores."""
    
    with st.spinner("🧹 Limpiando datos..."):
        try:
            # Limpiar dotación
            dotacion = dotacion_df[COLUMNAS_ESPERADAS['dotacion']].copy()
            dotacion = dotacion.dropna(subset=["SKU"])
            dotacion['SKU'] = dotacion['SKU'].astype(str).str.strip().str.upper()
            
            # Limpiar conteo (desde fila 3, columnas B y D)
            if conteo_df.shape[0] < 3:
                raise ValueError("El archivo de conteo debe tener al menos 3 filas")
            
            conteo = conteo_df.iloc[2:, [1, 3]].copy()
            conteo.columns = ['SKU', 'Cantidad']
            
            # Convertir cantidad con mejor manejo de errores
            conteo['Cantidad'] = pd.to_numeric(conteo['Cantidad'], errors='coerce')
            valores_invalidos = conteo['Cantidad'].isna().sum()
            if valores_invalidos > 0:
                st.warning(f"⚠️ Se encontraron {valores_invalidos} valores no numéricos en el conteo, se establecieron como 0")
            
            conteo['Cantidad'] = conteo['Cantidad'].fillna(0)
            conteo = conteo.dropna(subset=['SKU'])
            conteo['SKU'] = conteo['SKU'].astype(str).str.strip().str.upper()
            
            # Limpiar consumo
            consumo = consumo_df[COLUMNAS_ESPERADAS['consumo']].copy()
            consumo = consumo.dropna(subset=['Articulo'])
            
            # Extraer SKU del artículo con mejor regex
            consumo['SKU'] = consumo['Articulo'].str.extract(r'(^\S+)', expand=False)
            consumo = consumo[['SKU', 'Cantidad', 'ID Parte']].copy()
            consumo['SKU'] = consumo['SKU'].astype(str).str.strip().str.upper()
            consumo['Cantidad'] = pd.to_numeric(consumo['Cantidad'], errors='coerce').fillna(0)
            
            # Mostrar estadísticas de limpieza
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("📋 SKUs en dotación", len(dotacion))
            with col2:
                st.metric("📊 Registros de conteo", len(conteo))
            with col3:
                st.metric("🔧 Registros de consumo", len(consumo))
            
            return dotacion, conteo, consumo
            
        except Exception as e:
            st.error(f"❌ Error limpiando datos: {str(e)}")
            st.code(traceback.format_exc())
            raise e

def procesar_analisis(dotacion: pd.DataFrame, conteo: pd.DataFrame, consumo: pd.DataFrame) -> pd.DataFrame:
    """Procesa el análisis principal con lógica mejorada."""
    
    with st.spinner("⚙️ Procesando análisis..."):
        try:
            # Agregar conteo por SKU
            conteo_agg = conteo.groupby('SKU', as_index=False).agg({
                'Cantidad': 'sum'
            }).rename(columns={'Cantidad': 'Contada'})
            
            # Agregar consumo por SKU
            consumo_agg = consumo.groupby('SKU', as_index=False).agg({
                'Cantidad': 'sum'
            }).rename(columns={'Cantidad': 'Usada'})
            
            # Merge de todos los dataframes
            df = pd.merge(dotacion, conteo_agg, on='SKU', how='outer')
            df = pd.merge(df, consumo_agg, on='SKU', how='outer')
            
            # Rellenar valores nulos
            df[['DOTACIÓN', 'Contada', 'Usada']] = df[['DOTACIÓN', 'Contada', 'Usada']].fillna(0)
            
            # Calcular reposición
            df['Reposición'] = df['DOTACIÓN'] - df['Contada']
            
            # Obtener IDs de origen de consumo
            consumo_ids = consumo.groupby('SKU')['ID Parte'].apply(
                lambda x: ', '.join(sorted(set(str(id_parte) for id_parte in x if pd.notna(id_parte))))
            ).reset_index()
            consumo_ids.rename(columns={'ID Parte': 'Origen de la diferencia'}, inplace=True)
            df = pd.merge(df, consumo_ids, on='SKU', how='left')
            
            # Aplicar lógica de diagnóstico mejorada
            def diagnostico_mejorado(row):
                repos = row['Reposición']
                usada = row['Usada']
                
                if repos == 0 and usada == 0:
                    return "✅ Completo"
                elif abs(repos - usada) <= 0.01:  # Tolerancia para errores de redondeo
                    return "✅ OK"
                elif repos > usada:
                    diferencia = repos - usada
                    return f"❌ Faltan {int(diferencia)} piezas sin justificar"
                elif repos < usada:
                    diferencia = usada - repos
                    return f"⚠️ Consumo excesivo: +{int(diferencia)} desde almacén"
                else:
                    return "🔍 Revisión necesaria"
            
            def origen_diferencia_mejorado(row):
                if pd.notna(row['Origen de la diferencia']) and row['Origen de la diferencia'].strip():
                    return row['Origen de la diferencia']
                elif row['Usada'] > 0:
                    return "📝 Consumo no registrado"
                elif row['Contada'] > row['DOTACIÓN']:
                    return "📦 Exceso en inventario"
                elif row['Contada'] > 0:
                    return "👁️ Solo en conteo físico"
                else:
                    return "❓ Sin datos"
            
            df['Diagnóstico'] = df.apply(diagnostico_mejorado, axis=1)
            df['Origen de la diferencia'] = df.apply(origen_diferencia_mejorado, axis=1)
            
            # Extraer ubicación del SKU
            df['Ubicación'] = df['SKU'].str.extract(r'^\d{3}-(\w+)-\d+', expand=False)
            df['Ubicación'] = df['Ubicación'].fillna('SIN_UBICACION')
            
            # Ordenar por ubicación y SKU
            df = df.sort_values(['Ubicación', 'SKU']).reset_index(drop=True)
            
            # Seleccionar y reordenar columnas finales
            columnas_finales = [
                'SKU', 'CAJA', 'SECCION', 'Nº ORDEN', 'Ubicación',
                'DOTACIÓN', 'Contada', 'Usada', 'Reposición', 
                'Diagnóstico', 'Origen de la diferencia'
            ]
            
            return df[columnas_finales]
            
        except Exception as e:
            st.error(f"❌ Error en el procesamiento: {str(e)}")
            st.code(traceback.format_exc())
            raise e

def mostrar_metricas_resumen(df: pd.DataFrame):
    """Muestra métricas de resumen del análisis."""
    
    st.subheader("📊 Resumen del Análisis")
    
    # Métricas principales
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("📋 SKUs Total", len(df))
    
    with col2:
        ok_count = len(df[df['Diagnóstico'].str.contains('✅')])
        st.metric("✅ Estado OK", ok_count)
    
    with col3:
        faltan_count = len(df[df['Diagnóstico'].str.contains('❌')])
        st.metric("❌ Faltan Piezas", faltan_count)
    
    with col4:
        exceso_count = len(df[df['Diagnóstico'].str.contains('⚠️')])
        st.metric("⚠️ Consumo Excesivo", exceso_count)
    
    with col5:
        reposicion_total = df[df['Reposición'] > 0]['Reposición'].sum()
        st.metric("🔧 Total a Reponer", int(reposicion_total))
    
    # Gráfico de diagnósticos
    if len(df) > 0:
        st.subheader("📈 Distribución de Diagnósticos")
        diagnosticos = df['Diagnóstico'].value_counts()
        st.bar_chart(diagnosticos)

def generar_nombre_archivo(tecnico: str, fecha_inicio: date, fecha_fin: date) -> str:
    """Genera nombre de archivo estandarizado."""
    tecnico_clean = tecnico.lower().replace(' ', '_').replace('ñ', 'n')
    timestamp = datetime.now().strftime("%H%M")
    return f"{tecnico_clean}_{fecha_inicio}_a_{fecha_fin}_{timestamp}.xlsx"

def exportar_a_excel(df: pd.DataFrame, nombre_archivo: str, tecnico: str, fecha_inicio: date, fecha_fin: date) -> BytesIO:
    """Exporta los resultados a Excel con formato mejorado."""
    
    output = BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Hoja principal con resultados
        df.to_excel(writer, sheet_name='Análisis Detallado', index=False)
        
        # Hoja de resumen
        resumen_data = {
            'Métrica': ['SKUs Total', 'Estado OK', 'Faltan Piezas', 'Consumo Excesivo', 'Total a Reponer'],
            'Valor': [
                len(df),
                len(df[df['Diagnóstico'].str.contains('✅')]),
                len(df[df['Diagnóstico'].str.contains('❌')]),
                len(df[df['Diagnóstico'].str.contains('⚠️')]),
                int(df[df['Reposición'] > 0]['Reposición'].sum())
            ]
        }
        resumen_df = pd.DataFrame(resumen_data)
        resumen_df.to_excel(writer, sheet_name='Resumen', index=False)
        
        # Hoja de metadatos
        metadata = pd.DataFrame({
            'Campo': ['Técnico', 'Fecha Inicio', 'Fecha Fin', 'Fecha Análisis', 'Total SKUs'],
            'Valor': [tecnico, fecha_inicio, fecha_fin, datetime.now().strftime("%Y-%m-%d %H:%M"), len(df)]
        })
        metadata.to_excel(writer, sheet_name='Metadatos', index=False)
    
    output.seek(0)
    return output

# Interfaz principal
def main():
    st.title("🔧 Analizador de Maletas Técnicas - Reposición")
    st.markdown("### Sistema avanzado de control de inventario y reposición")
    
    # Menú lateral
    menu = st.sidebar.radio(
        "📋 Menú Principal", 
        ["📊 Nuevo análisis", "📂 Historial", "ℹ️ Ayuda"],
        index=0
    )
    
    if menu == "📊 Nuevo análisis":
        st.header("📊 Nuevo Análisis de Reposición")
        
        # Información del análisis
        with st.expander("📋 Información del análisis", expanded=True):
            col1, col2 = st.columns(2)
            
            with col1:
                tecnico = st.selectbox(
                    "👨‍🔧 Técnico responsable", 
                    ["Francisco Javier", "Rigoberto"],
                    help="Selecciona el técnico responsable del análisis"
                )
                fecha_inicio = st.date_input("📅 Desde:", value=date.today())
            
            with col2:
                fecha_fin = st.date_input("📅 Hasta:", value=date.today())
                if fecha_fin < fecha_inicio:
                    st.error("❌ La fecha fin debe ser posterior a la fecha inicio")
                    return
        
        st.divider()
        
        # Carga de archivos
        st.header("📁 Carga de Archivos")
        
        # Dotación fija (automática)
        with st.expander("📋 Dotación Fija", expanded=False):
            dotacion_df = cargar_dotacion()
            if dotacion_df is None:
                st.stop()
        
        # Archivos del usuario
        col1, col2 = st.columns(2)
        
        with col1:
            with st.expander("📊 Conteo Físico", expanded=True):
                st.info("💡 El archivo debe tener SKUs en columna B y cantidades en columna D (las primeras 2 filas se ignoran)")
                conteo_df = cargar_archivo("conteo físico", "conteo")
        
        with col2:
            with st.expander("🔧 Consumo Registrado", expanded=True):
                st.info("💡 Debe contener columnas: 'ID Parte', 'Cantidad', 'Articulo'")
                consumo_df = cargar_archivo("consumo registrado", "consumo")
        
        # Procesar análisis
        if conteo_df is not None and consumo_df is not None and dotacion_df is not None:
            st.divider()
            
            if st.button("🚀 Procesar Análisis", type="primary", use_container_width=True):
                try:
                    # Limpiar datos
                    dotacion, conteo, consumo = limpiar_datos(dotacion_df, conteo_df, consumo_df)
                    
                    # Procesar análisis
                    resultado = procesar_analisis(dotacion, conteo, consumo)
                    
                    st.success("✅ Análisis completado exitosamente")
                    
                    # Mostrar métricas
                    mostrar_metricas_resumen(resultado)
                    
                    # Mostrar tabla con filtros
                    st.subheader("📋 Resultados Detallados")
                    
                    # Filtros
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        ubicaciones = ['Todas'] + sorted(resultado['Ubicación'].unique().tolist())
                        filtro_ubicacion = st.selectbox("🏷️ Filtrar por Ubicación", ubicaciones)
                    
                    with col2:
                        diagnosticos = ['Todos'] + sorted(resultado['Diagnóstico'].unique().tolist())
                        filtro_diagnostico = st.selectbox("🔍 Filtrar por Diagnóstico", diagnosticos)
                    
                    with col3:
                        solo_reposicion = st.checkbox("🔧 Solo items que requieren reposición")
                    
                    # Aplicar filtros
                    df_filtrado = resultado.copy()
                    
                    if filtro_ubicacion != 'Todas':
                        df_filtrado = df_filtrado[df_filtrado['Ubicación'] == filtro_ubicacion]
                    
                    if filtro_diagnostico != 'Todos':
                        df_filtrado = df_filtrado[df_filtrado['Diagnóstico'] == filtro_diagnostico]
                    
                    if solo_reposicion:
                        df_filtrado = df_filtrado[df_filtrado['Reposición'] > 0]
                    
                    # Mostrar tabla filtrada
                    st.dataframe(
                        df_filtrado, 
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "Diagnóstico": st.column_config.TextColumn(
                                "Diagnóstico",
                                help="Estado del item según el análisis"
                            ),
                            "Reposición": st.column_config.NumberColumn(
                                "Reposición",
                                help="Cantidad que debe reponerse",
                                format="%d"
                            )
                        }
                    )
                    
                    # Guardar y descargar
                    st.divider()
                    
                    nombre_archivo = generar_nombre_archivo(tecnico, fecha_inicio, fecha_fin)
                    path_archivo = os.path.join(HISTORIAL_DIR, nombre_archivo)
                    
                    # Guardar en historial
                    try:
                        excel_data = exportar_a_excel(resultado, nombre_archivo, tecnico, fecha_inicio, fecha_fin)
                        
                        # Guardar archivo en historial
                        with open(path_archivo, 'wb') as f:
                            f.write(excel_data.getvalue())
                        
                        # Botón de descarga
                        st.download_button(
                            "📥 Descargar Análisis Completo",
                            data=excel_data.getvalue(),
                            file_name=nombre_archivo,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            type="primary",
                            use_container_width=True
                        )
                        
                        st.success(f"💾 Análisis guardado en historial: {nombre_archivo}")
                        
                    except Exception as e:
                        st.error(f"❌ Error guardando archivo: {str(e)}")
                
                except Exception as e:
                    st.error(f"❌ Error durante el análisis: {str(e)}")
                    with st.expander("🔍 Detalles del error"):
                        st.code(traceback.format_exc())
    
    elif menu == "📂 Historial":
        st.header("📁 Historial de Análisis")
        
        try:
            archivos = [f for f in os.listdir(HISTORIAL_DIR) if f.endswith('.xlsx')]
            archivos = sorted(archivos, reverse=True)  # Más recientes primero
            
            if not archivos:
                st.info("📭 No hay análisis previos guardados")
                return
            
            # Selección de archivo
            seleccion = st.selectbox(
                "📋 Selecciona un análisis:", 
                archivos,
                help="Los archivos están ordenados del más reciente al más antiguo"
            )
            
            if seleccion:
                path_completo = os.path.join(HISTORIAL_DIR, seleccion)
                
                try:
                    # Leer metadatos si existen
                    with pd.ExcelWriter(path_completo, mode='a') as writer:
                        pass  # Solo para verificar que el archivo es válido
                    
                    # Mostrar información del archivo
                    info_archivo = os.stat(path_completo)
                    fecha_creacion = datetime.fromtimestamp(info_archivo.st_mtime)
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.info(f"📅 Creado: {fecha_creacion.strftime('%Y-%m-%d %H:%M')}")
                    with col2:
                        st.info(f"📏 Tamaño: {info_archivo.st_size / 1024:.1f} KB")
                    
                    # Leer y mostrar datos
                    df_hist = pd.read_excel(path_completo, sheet_name='Análisis Detallado')
                    
                    # Mostrar métricas del historial
                    mostrar_metricas_resumen(df_hist)
                    
                    # Mostrar tabla
                    st.subheader(f"📋 Vista previa: {seleccion}")
                    st.dataframe(df_hist, use_container_width=True, hide_index=True)
                    
                    # Botón de descarga
                    with open(path_completo, 'rb') as f:
                        st.download_button(
                            "📥 Descargar este análisis",
                            data=f.read(),
                            file_name=seleccion,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                    
                    # Opción para eliminar
                    if st.button("🗑️ Eliminar este análisis", type="secondary"):
                        if st.checkbox("⚠️ Confirmar eliminación"):
                            os.remove(path_completo)
                            st.success("✅ Análisis eliminado")
                            st.rerun()
                
                except Exception as e:
                    st.error(f"❌ Error leyendo el archivo: {str(e)}")
        
        except Exception as e:
            st.error(f"❌ Error accediendo al historial: {str(e)}")
    
    elif menu == "ℹ️ Ayuda":
        st.header("ℹ️ Guía de Uso")
        
        with st.expander("📋 ¿Cómo usar el sistema?", expanded=True):
            st.markdown("""
            ### Pasos para realizar un análisis:
            
            1. **📊 Nuevo análisis** - Selecciona esta opción en el menú
            2. **👨‍🔧 Técnico** - Elige el técnico responsable
            3. **📅 Fechas** - Define el período de análisis
            4. **📁 Archivos** - Sube los archivos requeridos:
               - **Conteo físico**: Excel/CSV con SKUs en columna B y cantidades en columna D
               - **Consumo registrado**: Excel/CSV con columnas 'ID Parte', 'Cantidad', 'Articulo'
            5. **🚀 Procesar** - Haz clic en "Procesar Análisis"
            6. **📥 Descargar** - Descarga los resultados en Excel
            """)
        
        with st.expander("📁 Formato de archivos"):
            st.markdown("""
            ### Archivo de Conteo Físico:
            - Las **primeras 2 filas se ignoran** (pueden ser encabezados)
            - **Columna B**: SKU del producto
            - **Columna D**: Cantidad contada
            - Formato: `123-ABCDE-5678` (SKU) | `5` (cantidad)
            
            ### Archivo de Consumo:
            - **ID Parte**: Identificador del trabajo/orden
            - **Cantidad**: Cantidad consumida
            - **Articulo**: Descripción que contiene el SKU
            """)
        
        with st.expander("🔍 Interpretación de diagnósticos"):
            st.markdown("""
            - **✅ OK/Completo**: Todo en orden
            - **❌ Faltan X piezas**: Hay faltantes sin justificar
            - **⚠️ Consumo excesivo**: Se consumió más de lo esperado
            - **🔍 Revisión necesaria**: Requiere verificación manual
            """)
        
        with st.expander("💡 Consejos y buenas prácticas"):
            st.markdown("""
            - Revisa la vista previa de los archivos antes de procesarlos
            - Usa nombres descriptivos para los técnicos y fechas precisas
            - Los análisis se guardan automáticamente en el historial
            - Puedes filtrar los resultados por ubicación o diagnóstico
            - El sistema maneja automáticamente SKUs duplicados (los suma)
            """)

if __name__ == "__main__":
    main()