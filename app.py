import streamlit as st
import pandas as pd
from io import BytesIO
import os
from datetime import date, datetime
import traceback
from typing import Optional, Tuple, Dict, Any
import warnings
import requests
import json
import time
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
INVENTARIOS_DIR = "inventarios"
COLUMNAS_ESPERADAS = {
    'dotacion': ['SKU', 'DOTACIÓN', 'CAJA', 'SECCION', 'Nº ORDEN'],
    'conteo': ['SKU', 'Cantidad'],
    'consumo': ['ID Parte', 'Cantidad', 'Articulo']
}

# Configuración de Holded
HOLDED_CONFIG = {
    "api_key": "9371575c4698f7f1109a5d3cfe76ee00",
    "base_url": "https://api.holded.com/api/invoicing/v1",
    "almacen_oficina": "5ac3f3a82e1d932034516b9c"
}

# Configuración de Técnicos
TECNICOS_CONFIG = {
    "Francisco Javier": {
        "warehouse_id": "614b063bc04b9931c13bb1b2",
        "nombre_almacen": "Maleta Francisco Javier"
    },
    "Rigoberto": {
        "warehouse_id": "614b079d02938c166d0de8e2",
        "nombre_almacen": "Maleta Rigoberto"
    }
}

# Configuración de alertas
ALERTA_CONSUMO_OFICINA_UMBRAL = 0.40  # 40%

# Crear directorios
os.makedirs(HISTORIAL_DIR, exist_ok=True)
os.makedirs(INVENTARIOS_DIR, exist_ok=True)

# ============================================================================
# FUNCIONES DE HOLDED API
# ============================================================================

@st.cache_data(ttl=300)  # Cache por 5 minutos
def obtener_stock_warehouse(warehouse_id: str) -> Optional[Dict]:
    """Obtiene el stock de un almacén específico desde Holded API."""
    try:
        headers = {
            "key": HOLDED_CONFIG["api_key"],
            "Content-Type": "application/json"
        }
        
        url = f"{HOLDED_CONFIG['base_url']}/warehouses/{warehouse_id}/stock"
        
        with st.spinner(f"🔗 Consultando stock almacén {warehouse_id[-8:]}..."):
            response = requests.get(url, headers=headers, timeout=10)
            
        if response.status_code == 200:
            try:
                data = response.json()
                
                # Procesar según el tipo de respuesta
                stock_dict = {}
                
                if isinstance(data, list):
                    # Formato lista - procesar cada item
                    for item in data:
                        if isinstance(item, dict) and 'sku' in item:
                            sku = item.get('sku', '').upper().strip()
                            stock = item.get('stock', 0)
                            if sku:  # Solo agregar si el SKU no está vacío
                                stock_dict[sku] = stock
                        else:
                            st.warning(f"⚠️ Item con estructura inesperada: {item}")
                
                elif isinstance(data, dict):
                    # Formato diccionario - puede tener diferentes estructuras
                    if 'data' in data and isinstance(data['data'], list):
                        # Caso: {"data": [items...], "meta": {...}}
                        for item in data['data']:
                            if isinstance(item, dict) and 'sku' in item:
                                sku = item.get('sku', '').upper().strip()
                                stock = item.get('stock', 0)
                                if sku:
                                    stock_dict[sku] = stock
                    
                    elif 'products' in data and isinstance(data['products'], list):
                        # Caso: {"products": [items...]}
                        for item in data['products']:
                            if isinstance(item, dict) and 'sku' in item:
                                sku = item.get('sku', '').upper().strip()
                                stock = item.get('stock', 0)
                                if sku:
                                    stock_dict[sku] = stock
                    
                    elif 'items' in data and isinstance(data['items'], list):
                        # Caso: {"items": [items...]}
                        for item in data['items']:
                            if isinstance(item, dict) and 'sku' in item:
                                sku = item.get('sku', '').upper().strip()
                                stock = item.get('stock', 0)
                                if sku:
                                    stock_dict[sku] = stock
                    
                    else:
                        # Caso: diccionario plano con SKUs como claves
                        for key, value in data.items():
                            if isinstance(value, (int, float)) and key.upper().strip():
                                stock_dict[key.upper().strip()] = value
                            elif isinstance(value, dict) and 'stock' in value:
                                sku = key.upper().strip()
                                stock = value.get('stock', 0)
                                if sku:
                                    stock_dict[sku] = stock
                
                else:
                    st.error(f"❌ Formato de respuesta no soportado de Holded: {type(data)}")
                    st.code(f"Muestra de datos: {str(data)[:200]}...")
                    return None
                
                st.success(f"✅ Stock obtenido del almacén: {len(stock_dict)} productos")
                return stock_dict
                
            except json.JSONDecodeError as e:
                st.error(f"❌ Error decodificando JSON de Holded: {str(e)}")
                st.code(f"Respuesta recibida: {response.text[:500]}...")
                return None
                
        else:
            st.error(f"❌ Error API Holded almacén {warehouse_id[-8:]}: {response.status_code}")
            if response.text:
                st.code(f"Detalle del error: {response.text[:300]}...")
            return None
            
    except requests.exceptions.Timeout:
        st.error("⏰ Timeout conectando con Holded API")
        return None
    except requests.exceptions.RequestException as e:
        st.error(f"🔗 Error de conexión con Holded: {str(e)}")
        return None
    except Exception as e:
        st.error(f"❌ Error inesperado con Holded API: {str(e)}")
        st.code(f"Tipo de error: {type(e).__name__}")
        return None

@st.cache_data(ttl=300)
def obtener_stock_oficina() -> Optional[Dict]:
    """Obtiene el stock del almacén oficina."""
    return obtener_stock_warehouse(HOLDED_CONFIG["almacen_oficina"])

def analizar_origen_consumo(sku: str, consumo: float, inventario_maleta: float, 
                           stock_oficina: Dict) -> Tuple[str, float, float, str]:
    """Analiza el origen real del consumo (maleta vs oficina)."""
    
    consumo = consumo or 0
    inventario_maleta = inventario_maleta or 0
    
    # Obtener stock de oficina de forma segura
    stock_oficina_sku = 0
    if stock_oficina and isinstance(stock_oficina, dict):
        stock_oficina_sku = stock_oficina.get(sku, 0)
    
    # Calcular cuánto se puede consumir desde maleta
    disponible_maleta = inventario_maleta
    
    if consumo == 0:
        return "⚪ Sin consumo", 0, 0, "Sin uso registrado"
    elif consumo <= disponible_maleta:
        return "✅ Solo desde maleta", consumo, 0, f"Cubierto por maleta ({int(consumo)} uds)"
    elif consumo <= (disponible_maleta + stock_oficina_sku):
        desde_maleta = disponible_maleta
        desde_oficina = consumo - disponible_maleta
        porcentaje_oficina = (desde_oficina / consumo) * 100 if consumo > 0 else 0
        return ("📦 Consumo mixto", desde_maleta, desde_oficina, 
                f"Maleta: {int(desde_maleta)}, Oficina: {int(desde_oficina)} ({porcentaje_oficina:.1f}%)")
    else:
        # Stock insuficiente total
        deficit = consumo - (disponible_maleta + stock_oficina_sku)
        return ("⚠️ Stock insuficiente", disponible_maleta, stock_oficina_sku, 
                f"Falta stock: {int(deficit)} uds")

def generar_alertas_dotacion(df_analisis: pd.DataFrame, consumo_df: pd.DataFrame) -> list:
    """Genera alertas para SKUs candidatos a añadir a dotación fija."""
    
    alertas = []
    
    try:
        # Analizar SKUs que tienen consumo desde oficina
        skus_con_consumo_oficina = df_analisis[
            (df_analisis['Desde Oficina'] > 0) & 
            (df_analisis['Usada'] > 0)
        ].copy()
        
        for _, row in skus_con_consumo_oficina.iterrows():
            sku = row['SKU']
            consumo_total = row['Usada']
            desde_oficina = row['Desde Oficina']
            
            if consumo_total > 0:
                porcentaje_oficina = (desde_oficina / consumo_total) * 100
                
                if porcentaje_oficina >= (ALERTA_CONSUMO_OFICINA_UMBRAL * 100):
                    alertas.append({
                        'sku': sku,
                        'consumo_total': consumo_total,
                        'desde_oficina': desde_oficina,
                        'porcentaje_oficina': porcentaje_oficina,
                        'dotacion_actual': row.get('DOTACIÓN', 0),
                        'sugerencia': f"Considerar aumentar dotación maleta a {int(consumo_total * 1.2)} uds"
                    })
        
        return alertas
        
    except Exception as e:
        st.warning(f"⚠️ Error generando alertas: {str(e)}")
        return []

# ============================================================================
# FUNCIONES ORIGINALES (MEJORADAS)
# ============================================================================

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
            
        # Limpiar SKUs
        df['SKU'] = df['SKU'].astype(str).str.strip().str.upper()
        
        st.success(f"✅ Dotación fija cargada: {len(df)} elementos")
        return df
        
    except Exception as e:
        st.error(f"❌ Error cargando dotación fija: {str(e)}")
        return None

def determinar_estado_completo(dotacion: float, inventariado: float, usada: float, 
                             stock_maleta: Optional[float] = None, desde_oficina: float = 0,
                             origen_consumo: str = "") -> str:
    """Determina el estado completo del SKU con lógica mejorada incluyendo origen del consumo."""
    
    # Normalizar valores nulos
    dotacion = dotacion or 0
    inventariado = inventariado or 0  
    usada = usada or 0
    stock_maleta = stock_maleta if stock_maleta is not None else 0
    desde_oficina = desde_oficina or 0
    
    # SKU no registrado en dotación
    if dotacion == 0 and inventariado > 0:
        return f"🆕 SKU escaneado no registrado ({int(inventariado)} unidades)"
    
    # Estados óptimos
    if dotacion == inventariado and usada == 0:
        return "✅ Perfecto - Sin consumo"
    
    reposicion_necesaria = dotacion - inventariado
    
    # Considerar solo el consumo que debería haber venido de maleta
    consumo_esperado_maleta = usada - desde_oficina
    
    if abs(reposicion_necesaria - consumo_esperado_maleta) <= 0.01:
        if desde_oficina > 0:
            return f"✅ OK - Parte desde oficina ({int(desde_oficina)} uds)"
        else:
            return "✅ OK - Consumo justificado"
    
    # Estados de faltantes en maleta
    if inventariado == 0 and dotacion > 0:
        if desde_oficina > 0:
            return f"❌ Maleta vacía - Consumo desde oficina ({int(desde_oficina)} uds)"
        else:
            return f"❌ Faltan {int(dotacion)} - No escaneado"
    
    if reposicion_necesaria > consumo_esperado_maleta:
        faltante = reposicion_necesaria - consumo_esperado_maleta
        if desde_oficina > 0:
            return f"❌ Faltan {int(faltante)} + {int(desde_oficina)} desde oficina"
        else:
            return f"❌ Faltan {int(faltante)} - Sin justificar"
    
    # Estados de excesos
    if inventariado > dotacion:
        exceso = inventariado - dotacion
        return f"⚠️ Exceso de {int(exceso)} unidades"
    
    if consumo_esperado_maleta < 0:  # Más consumo del esperado
        consumo_extra = abs(consumo_esperado_maleta)
        return f"⚠️ Consumo excesivo maleta +{int(consumo_extra)}"
    
    # Diferencias con stock Holded
    if stock_maleta is not None and abs(inventariado - stock_maleta) > 0.01:
        diferencia = inventariado - stock_maleta
        if diferencia > 0:
            return f"🏢 +{int(diferencia)} vs Holded"
        else:
            return f"🏢 {int(diferencia)} vs Holded"
    
    # Sin datos
    if dotacion == 0 and inventariado == 0 and usada == 0:
        return "❓ Sin datos de inventario"
    
    # Caso edge
    return "🔍 Revisión - Datos inconsistentes"

# ============================================================================
# FUNCIONES DE INVENTARIO
# ============================================================================

def inicializar_inventario_session():
    """Inicializa las variables de sesión para el inventario."""
    if 'inventario_activo' not in st.session_state:
        st.session_state.inventario_activo = {}
    if 'tecnico_actual' not in st.session_state:
        st.session_state.tecnico_actual = None
    if 'dotacion_df' not in st.session_state:
        st.session_state.dotacion_df = None
    if 'stock_holded' not in st.session_state:
        st.session_state.stock_holded = None

def guardar_inventario(tecnico: str, inventario_data: Dict, completado: bool = False):
    """Guarda el inventario del técnico."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    estado = "completado" if completado else "en_progreso"
    
    nombre_archivo = f"{tecnico.lower().replace(' ', '_')}_{date.today()}_{timestamp}_{estado}.json"
    path_archivo = os.path.join(INVENTARIOS_DIR, nombre_archivo)
    
    datos_completos = {
        "tecnico": tecnico,
        "fecha": date.today().isoformat(),
        "timestamp": timestamp,
        "estado": estado,
        "warehouse_id": TECNICOS_CONFIG[tecnico]["warehouse_id"],
        "inventario": inventario_data,
        "total_skus": len(inventario_data),
        "total_unidades": sum(inventario_data.values())
    }
    
    try:
        with open(path_archivo, 'w') as f:
            json.dump(datos_completos, f, indent=2)
        
        if completado:
            st.success(f"✅ Inventario completado y guardado: {nombre_archivo}")
        else:
            st.info(f"💾 Inventario guardado parcialmente: {nombre_archivo}")
            
        return nombre_archivo
    except Exception as e:
        st.error(f"❌ Error guardando inventario: {str(e)}")
        return None

def cargar_inventarios_disponibles():
    """Carga la lista de inventarios disponibles."""
    try:
        archivos = [f for f in os.listdir(INVENTARIOS_DIR) if f.endswith('.json')]
        inventarios = []
        
        for archivo in archivos:
            try:
                with open(os.path.join(INVENTARIOS_DIR, archivo), 'r') as f:
                    data = json.load(f)
                    inventarios.append({
                        'archivo': archivo,
                        'tecnico': data.get('tecnico'),
                        'fecha': data.get('fecha'),
                        'estado': data.get('estado'),
                        'total_skus': data.get('total_skus', 0),
                        'total_unidades': data.get('total_unidades', 0)
                    })
            except:
                continue
                
        return sorted(inventarios, key=lambda x: x['fecha'], reverse=True)
    except:
        return []

def mostrar_interface_inventario():
    """Muestra la interface principal de inventario."""
    st.header("📱 Inventario en Tiempo Real")
    
    inicializar_inventario_session()
    
    # Selector de técnico
    col1, col2 = st.columns([2, 1])
    
    with col1:
        tecnico_seleccionado = st.selectbox(
            "👨‍🔧 Selecciona el técnico:",
            list(TECNICOS_CONFIG.keys()),
            key="selector_tecnico_inventario"
        )
    
    with col2:
        if st.button("🔄 Nuevo Inventario", type="primary"):
            st.session_state.inventario_activo = {}
            st.session_state.tecnico_actual = tecnico_seleccionado
            st.session_state.dotacion_df = None
            st.session_state.stock_holded = None
            st.rerun()
    
    # Cargar datos si cambió el técnico
    if st.session_state.tecnico_actual != tecnico_seleccionado:
        st.session_state.tecnico_actual = tecnico_seleccionado
        st.session_state.dotacion_df = None
        st.session_state.stock_holded = None
    
    # Cargar dotación y stock de Holded
    if st.session_state.dotacion_df is None:
        st.session_state.dotacion_df = cargar_dotacion()
    
    if st.session_state.stock_holded is None and st.session_state.dotacion_df is not None:
        warehouse_id = TECNICOS_CONFIG[tecnico_seleccionado]["warehouse_id"]
        st.session_state.stock_holded = obtener_stock_warehouse(warehouse_id)
    
    if st.session_state.dotacion_df is None:
        st.error("❌ No se puede continuar sin la dotación fija")
        return
    
    # Mostrar información del almacén
    almacen_info = TECNICOS_CONFIG[tecnico_seleccionado]
    st.info(f"🏢 Almacén: {almacen_info['nombre_almacen']} (ID: {almacen_info['warehouse_id']})")
    
    # Interface de escaneo optimizada para pistolas
    st.divider()
    st.subheader("🔍 Escaneo Rápido de Códigos")
    
    # Inicializar estados necesarios
    if 'ultimo_feedback' not in st.session_state:
        st.session_state.ultimo_feedback = None
    if 'input_scanner' not in st.session_state:
        st.session_state.input_scanner = ""
    
    # Input optimizado para pistola de código de barras
    col1, col2 = st.columns([4, 1])
    
    with col1:
        # Campo de entrada con callback automático
        if st.session_state.get('escaneo_pausado', False):
            st.warning("⏸️ ESCANEO PAUSADO - Reactiva para continuar")
            st.text_input(
                "📱 Escaneo PAUSADO:",
                value="",
                disabled=True,
                help="El escaneo está pausado. Presiona 'Reanudar Escaneo' para continuar"
            )
        else:
            st.text_input(
                "📱 Escanea o introduce el código SKU:",
                key="input_scanner",
                placeholder="Escanea con pistola o escribe código...",
                help="💡 Con pistola: escanea y automáticamente se agrega. Manual: escribe y presiona Enter",
                on_change=procesar_codigo_escaneado_rapido,
                label_visibility="visible"
            )
        
        # Mostrar feedback del último escaneo
        if st.session_state.ultimo_feedback:
            feedback = st.session_state.ultimo_feedback
            if feedback['tipo'] == 'success':
                st.success(feedback['mensaje'])
            else:
                st.warning(feedback['mensaje'])
    
    with col2:
        st.markdown("### Estadísticas")
        if st.session_state.inventario_activo:
            total_items = len(st.session_state.inventario_activo)
            total_unidades = sum(st.session_state.inventario_activo.values())
            st.metric("🏷️ SKUs", total_items)
            st.metric("📦 Unidades", total_unidades)
        else:
            st.metric("🏷️ SKUs", 0)
            st.metric("📦 Unidades", 0)
    
    # Información de ayuda
    with st.expander("💡 Instrucciones de Escaneo"):
        st.markdown("""
        ### 📱 Escaneo con Pistola:
        1. **Apunta** la pistola al código de barras
        2. **Presiona** el gatillo para escanear
        3. **Automáticamente** se agrega al inventario
        4. **Listo** para el siguiente escaneo
        
        ### ⌨️ Entrada Manual:
        1. **Escribe** el código en el campo
        2. **Presiona Enter** para agregar
        3. **Se limpia** automáticamente
        
        ### 🎯 Consejos:
        - Mantén el cursor en el campo de entrada
        - Escanea de forma continua sin parar
        - Los códigos se validan en tiempo real
        - El sistema suma automáticamente duplicados
        """)
    
    # Mostrar último escaneo destacado
    if st.session_state.inventario_activo:
        ultimo_sku = list(st.session_state.inventario_activo.keys())[-1]
        ultima_cantidad = st.session_state.inventario_activo[ultimo_sku]
        st.info(f"🎯 **Último escaneo**: {ultimo_sku} (Total: {ultima_cantidad} uds)")
    
    # Script para mantener el foco en el campo (usando componente HTML)
    st.markdown("""
    <script>
    // Mantener el foco en el campo de entrada para escaneo continuo
    setTimeout(function() {
        const input = document.querySelector('input[aria-label="📱 Escanea o introduce el código SKU:"]');
        if (input) {
            input.focus();
            input.select();
        }
    }, 100);
    </script>
    """, unsafe_allow_html=True)
    
    # Historial de escaneos recientes (opcional)
    if st.session_state.inventario_activo and st.checkbox("📋 Mostrar últimos escaneos", value=False):
        st.subheader("⏱️ Últimos 10 Escaneos")
        items_recientes = list(st.session_state.inventario_activo.items())[-10:]
        
        for sku, cantidad in reversed(items_recientes):
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.text(sku)
            with col2:
                st.text(f"{cantidad} uds")
            with col3:
                # Opción para quitar una unidad
                if st.button("➖", key=f"remove_{sku}", help="Quitar 1 unidad"):
                    if st.session_state.inventario_activo[sku] > 1:
                        st.session_state.inventario_activo[sku] -= 1
                    else:
                        del st.session_state.inventario_activo[sku]
                    st.rerun()
    
    # Mostrar inventario actual
    mostrar_inventario_actual()
    
    # Botones de acción mejorados
    st.divider()
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button("💾 Guardar Parcial", use_container_width=True):
            if st.session_state.inventario_activo:
                guardar_inventario(tecnico_seleccionado, st.session_state.inventario_activo, False)
            else:
                st.warning("⚠️ No hay datos para guardar")
    
    with col2:
        if st.button("✅ Completar Inventario", type="primary", use_container_width=True):
            if st.session_state.inventario_activo:
                nombre_archivo = guardar_inventario(tecnico_seleccionado, st.session_state.inventario_activo, True)
                if nombre_archivo:
                    st.balloons()
                    # Limpiar sesión
                    st.session_state.inventario_activo = {}
                    st.session_state.ultimo_feedback = None
                    st.success("🎉 ¡Inventario completado exitosamente!")
            else:
                st.warning("⚠️ No hay datos para completar")
    
    with col3:
        if st.button("🗑️ Limpiar Todo", use_container_width=True):
            if st.session_state.inventario_activo:
                if st.button("⚠️ Confirmar Limpieza", key="confirm_clear"):
                    st.session_state.inventario_activo = {}
                    st.session_state.ultimo_feedback = None
                    st.success("🧹 Inventario limpiado")
                    st.rerun()
                else:
                    st.warning("👆 Presiona de nuevo para confirmar")
            else:
                st.info("✨ Ya está limpio")
    
    with col4:
        # Botón de pausa/reanudar escaneo
        if 'escaneo_pausado' not in st.session_state:
            st.session_state.escaneo_pausado = False
            
        if st.session_state.escaneo_pausado:
            if st.button("▶️ Reanudar Escaneo", type="secondary", use_container_width=True):
                st.session_state.escaneo_pausado = False
                st.success("▶️ Escaneo reanudado")
                st.rerun()
        else:
            if st.button("⏸️ Pausar Escaneo", use_container_width=True):
                st.session_state.escaneo_pausado = True
                st.warning("⏸️ Escaneo pausado")
                st.rerun()

def procesar_codigo_escaneado_rapido():
    """Procesa códigos escaneados de forma optimizada para pistolas de código de barras."""
    # Verificar si el escaneo está pausado
    if st.session_state.get('escaneo_pausado', False):
        st.session_state.input_scanner = ""  # Limpiar input
        return
    
    if 'input_scanner' not in st.session_state:
        return
    
    codigo = st.session_state.input_scanner
    if not codigo or not codigo.strip():
        return
    
    codigo_limpio = codigo.strip().upper()
    
    # Validar formato básico del SKU (opcional)
    if len(codigo_limpio) < 3:
        st.session_state.ultimo_feedback = {
            'tipo': 'warning',
            'mensaje': f"⚠️ Código muy corto: {codigo_limpio}"
        }
        st.session_state.input_scanner = ""
        return
    
    # Validar contra dotación
    dotacion_df = st.session_state.dotacion_df
    sku_existe = codigo_limpio in dotacion_df['SKU'].values
    
    # Validar contra Holded maleta
    stock_maleta = st.session_state.stock_holded
    stock_en_maleta = stock_maleta.get(codigo_limpio, 0) if stock_maleta else 0
    
    # Agregar al inventario
    if codigo_limpio in st.session_state.inventario_activo:
        st.session_state.inventario_activo[codigo_limpio] += 1
    else:
        st.session_state.inventario_activo[codigo_limpio] = 1
    
    # Limpiar el input inmediatamente
    st.session_state.input_scanner = ""
    
    # Mostrar feedback rápido
    cantidad_actual = st.session_state.inventario_activo[codigo_limpio]
    
    # Almacenar mensaje de feedback en session state para mostrarlo
    if sku_existe:
        dotacion_esperada = dotacion_df[dotacion_df['SKU'] == codigo_limpio]['DOTACIÓN'].iloc[0]
        st.session_state.ultimo_feedback = {
            'tipo': 'success',
            'mensaje': f"✅ {codigo_limpio} → Cantidad: {cantidad_actual} | Dotación: {dotacion_esperada} | Holded: {stock_en_maleta}"
        }
    else:
        st.session_state.ultimo_feedback = {
            'tipo': 'warning', 
            'mensaje': f"⚠️ {codigo_limpio} → Cantidad: {cantidad_actual} | ❌ No está en dotación | Holded: {stock_en_maleta}"
        }

def mostrar_inventario_actual():
    """Muestra el inventario actual en tiempo real."""
    if not st.session_state.inventario_activo:
        st.info("📭 No hay elementos escaneados aún")
        return
    
    st.subheader("📋 Inventario Actual")
    
    # Crear DataFrame con el inventario actual
    inventario_data = []
    dotacion_df = st.session_state.dotacion_df
    stock_maleta = st.session_state.stock_holded or {}
    
    for sku, cantidad in st.session_state.inventario_activo.items():
        # Buscar en dotación
        dotacion_row = dotacion_df[dotacion_df['SKU'] == sku]
        if not dotacion_row.empty:
            dotacion = dotacion_row.iloc[0]['DOTACIÓN']
            seccion = dotacion_row.iloc[0]['SECCION']
            caja = dotacion_row.iloc[0]['CAJA']
        else:
            dotacion = 0
            seccion = "NO REGISTRADO"
            caja = "NO REGISTRADO"
        
        # Stock en Holded maleta
        stock_h = stock_maleta.get(sku, 0)
        
        # Estado (sin análisis de consumo aún)
        estado = determinar_estado_completo(dotacion, cantidad, 0, stock_h, 0, "")
        
        inventario_data.append({
            'SKU': sku,
            'Cantidad Escaneada': cantidad,
            'Dotación': dotacion,
            'Stock Holded Maleta': stock_h,
            'Diferencia vs Dotación': cantidad - dotacion,
            'Diferencia vs Holded': cantidad - stock_h,
            'Estado': estado,
            'Sección': seccion,
            'Caja': caja
        })
    
    df_inventario = pd.DataFrame(inventario_data)
    
    # Métricas rápidas
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📊 SKUs Escaneados", len(df_inventario))
    with col2:
        st.metric("📦 Total Unidades", df_inventario['Cantidad Escaneada'].sum())
    with col3:
        perfectos = len(df_inventario[df_inventario['Estado'].str.contains('✅')])
        st.metric("✅ Estados OK", perfectos)
    with col4:
        problemas = len(df_inventario) - perfectos
        st.metric("⚠️ Requieren Atención", problemas)
    
    # Tabla con filtros
    col1, col2 = st.columns(2)
    with col1:
        filtro_estado = st.selectbox(
            "🔍 Filtrar por estado:",
            ["Todos"] + sorted(df_inventario['Estado'].unique().tolist()),
            key="filtro_estado_inventario"
        )
    with col2:
        solo_problemas = st.checkbox("⚠️ Solo mostrar problemas", key="solo_problemas_inventario")
    
    # Aplicar filtros
    df_filtrado = df_inventario.copy()
    if filtro_estado != "Todos":
        df_filtrado = df_filtrado[df_filtrado['Estado'] == filtro_estado]
    if solo_problemas:
        df_filtrado = df_filtrado[~df_filtrado['Estado'].str.contains('✅')]
    
    # Mostrar tabla
    st.dataframe(
        df_filtrado,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Estado": st.column_config.TextColumn("Estado", help="Estado del SKU según análisis"),
            "Diferencia vs Dotación": st.column_config.NumberColumn("Diff. Dotación", format="%d"),
            "Diferencia vs Holded": st.column_config.NumberColumn("Diff. Holded", format="%d")
        }
    )

def mostrar_historial_inventarios():
    """Muestra el historial de inventarios realizados."""
    st.header("📂 Historial de Inventarios")
    
    inventarios = cargar_inventarios_disponibles()
    
    if not inventarios:
        st.info("📭 No hay inventarios guardados")
        return
    
    # Filtros
    col1, col2 = st.columns(2)
    with col1:
        tecnicos_disponibles = ["Todos"] + list(set([inv['tecnico'] for inv in inventarios]))
        filtro_tecnico = st.selectbox("👨‍🔧 Filtrar por técnico:", tecnicos_disponibles)
    
    with col2:
        estados_disponibles = ["Todos"] + list(set([inv['estado'] for inv in inventarios]))
        filtro_estado = st.selectbox("📊 Filtrar por estado:", estados_disponibles)
    
    # Aplicar filtros
    inventarios_filtrados = inventarios
    if filtro_tecnico != "Todos":
        inventarios_filtrados = [inv for inv in inventarios_filtrados if inv['tecnico'] == filtro_tecnico]
    if filtro_estado != "Todos":
        inventarios_filtrados = [inv for inv in inventarios_filtrados if inv['estado'] == filtro_estado]
    
    # Mostrar lista
    for inv in inventarios_filtrados:
        with st.expander(f"📋 {inv['tecnico']} - {inv['fecha']} ({inv['estado']})"):
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("📊 SKUs", inv['total_skus'])
            with col2:
                st.metric("📦 Unidades", inv['total_unidades'])
            with col3:
                estado_emoji = "✅" if inv['estado'] == "completado" else "⏳"
                st.metric("Estado", f"{estado_emoji} {inv['estado']}")
            
            # Botones de acción
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if st.button(f"👁️ Ver Detalle", key=f"ver_{inv['archivo']}"):
                    mostrar_detalle_inventario(inv['archivo'])
            
            with col2:
                if st.button(f"📥 Usar en Análisis", key=f"usar_{inv['archivo']}"):
                    st.session_state.inventario_seleccionado = inv['archivo']
                    st.success(f"✅ Inventario seleccionado para análisis")
            
            with col3:
                if st.button(f"🗑️ Eliminar", key=f"eliminar_{inv['archivo']}"):
                    if st.checkbox(f"Confirmar eliminación", key=f"confirm_{inv['archivo']}"):
                        try:
                            os.remove(os.path.join(INVENTARIOS_DIR, inv['archivo']))
                            st.success("✅ Inventario eliminado")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Error eliminando: {str(e)}")

def mostrar_detalle_inventario(nombre_archivo: str):
    """Muestra el detalle completo de un inventario."""
    try:
        with open(os.path.join(INVENTARIOS_DIR, nombre_archivo), 'r') as f:
            data = json.load(f)
        
        st.subheader(f"📋 Detalle: {data['tecnico']} - {data['fecha']}")
        
        # Información general
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("👨‍🔧 Técnico", data['tecnico'])
        with col2:
            st.metric("📅 Fecha", data['fecha'])
        with col3:
            st.metric("📊 SKUs", data['total_skus'])
        with col4:
            st.metric("📦 Unidades", data['total_unidades'])
        
        # Tabla de inventario
        inventario_items = []
        for sku, cantidad in data['inventario'].items():
            inventario_items.append({
                'SKU': sku,
                'Cantidad': cantidad
            })
        
        df_detalle = pd.DataFrame(inventario_items)
        st.dataframe(df_detalle, use_container_width=True, hide_index=True)
        
    except Exception as e:
        st.error(f"❌ Error cargando inventario: {str(e)}")

# ============================================================================
# FUNCIONES ORIGINALES ACTUALIZADAS
# ============================================================================

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

def procesar_analisis(dotacion: pd.DataFrame, conteo: pd.DataFrame, consumo: pd.DataFrame, 
                     stock_maleta: Dict = None, tecnico_seleccionado: str = None) -> Tuple[pd.DataFrame, list]:
    """Procesa el análisis principal con lógica completa incluyendo origen del consumo."""
    
    with st.spinner("⚙️ Procesando análisis avanzado..."):
        try:
            # Obtener stock del almacén oficina (con manejo de errores)
            try:
                stock_oficina = obtener_stock_oficina()
                if stock_oficina:
                    st.success(f"✅ Stock oficina obtenido: {len(stock_oficina)} productos")
                else:
                    st.warning("⚠️ No se pudo obtener stock de oficina, continuando sin él")
                    stock_oficina = {}
            except Exception as e:
                st.warning(f"⚠️ Error obteniendo stock oficina: {str(e)}")
                stock_oficina = {}
            
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
            
            # Calcular reposición (SIEMPRE Dotación - Inventario, independiente del origen)
            df['Reposición'] = df['DOTACIÓN'] - df['Contada']
            
            # Agregar stock de maleta Holded si está disponible
            if stock_maleta and isinstance(stock_maleta, dict):
                df['Stock Maleta Holded'] = df['SKU'].map(stock_maleta).fillna(0)
            else:
                df['Stock Maleta Holded'] = 0
            
            # Agregar stock de oficina para todos los SKUs
            if stock_oficina and isinstance(stock_oficina, dict):
                df['Stock Oficina'] = df['SKU'].map(stock_oficina).fillna(0)
            else:
                df['Stock Oficina'] = 0
            
            # Analizar origen del consumo para cada SKU
            origen_data = []
            for _, row in df.iterrows():
                sku = row['SKU']
                consumo_total = row['Usada']
                inventario_maleta = row['Contada']
                
                try:
                    if consumo_total > 0:
                        origen, desde_maleta, desde_oficina, descripcion = analizar_origen_consumo(
                            sku, consumo_total, inventario_maleta, stock_oficina
                        )
                        origen_data.append({
                            'SKU': sku,
                            'Origen Consumo': origen,
                            'Desde Maleta': desde_maleta,
                            'Desde Oficina': desde_oficina,
                            'Descripción Origen': descripcion
                        })
                    else:
                        origen_data.append({
                            'SKU': sku,
                            'Origen Consumo': '⚪ Sin consumo',
                            'Desde Maleta': 0,
                            'Desde Oficina': 0,
                            'Descripción Origen': 'No hay consumo registrado'
                        })
                except Exception as e:
                    st.warning(f"⚠️ Error analizando origen para SKU {sku}: {str(e)}")
                    origen_data.append({
                        'SKU': sku,
                        'Origen Consumo': '🔍 Error en análisis',
                        'Desde Maleta': 0,
                        'Desde Oficina': 0,
                        'Descripción Origen': f'Error: {str(e)}'
                    })
            
            # Merge con datos de origen
            df_origen = pd.DataFrame(origen_data)
            df = pd.merge(df, df_origen, on='SKU', how='left')
            
            # Obtener IDs de origen de consumo
            consumo_ids = consumo.groupby('SKU')['ID Parte'].apply(
                lambda x: ', '.join(sorted(set(str(id_parte) for id_parte in x if pd.notna(id_parte))))
            ).reset_index()
            consumo_ids.rename(columns={'ID Parte': 'Trabajos/Órdenes'}, inplace=True)
            df = pd.merge(df, consumo_ids, on='SKU', how='left')
            
            # Rellenar valores nulos en 'Trabajos/Órdenes'
            df['Trabajos/Órdenes'] = df['Trabajos/Órdenes'].fillna('Sin órdenes registradas')
            
            # Aplicar lógica de diagnóstico mejorada
            def diagnostico_completo(row):
                try:
                    return determinar_estado_completo(
                        row['DOTACIÓN'], 
                        row['Contada'], 
                        row['Usada'],
                        row['Stock Maleta Holded'] if stock_maleta else None,
                        row['Desde Oficina'],
                        row['Origen Consumo']
                    )
                except Exception as e:
                    return f"🔍 Error en diagnóstico: {str(e)}"
            
            df['Diagnóstico'] = df.apply(diagnostico_completo, axis=1)
            
            # Extraer ubicación del SKU
            df['Ubicación'] = df['SKU'].str.extract(r'^\d{3}-(\w+)-\d+', expand=False)
            df['Ubicación'] = df['Ubicación'].fillna('SIN_UBICACION')
            
            # Calcular diferencias adicionales
            if stock_maleta and isinstance(stock_maleta, dict):
                df['Diff. vs Holded Maleta'] = df['Contada'] - df['Stock Maleta Holded']
            
            # Ordenar por ubicación y SKU
            df = df.sort_values(['Ubicación', 'SKU']).reset_index(drop=True)
            
            # Seleccionar y reordenar columnas finales
            columnas_finales = [
                'SKU', 'CAJA', 'SECCION', 'Nº ORDEN', 'Ubicación',
                'DOTACIÓN', 'Contada', 'Usada', 'Reposición'
            ]
            
            # Agregar columnas de stock si están disponibles
            if stock_maleta and isinstance(stock_maleta, dict):
                columnas_finales.extend(['Stock Maleta Holded', 'Diff. vs Holded Maleta'])
            
            if stock_oficina and isinstance(stock_oficina, dict):
                columnas_finales.append('Stock Oficina')
            
            # Agregar columnas de origen del consumo
            columnas_finales.extend([
                'Desde Maleta', 'Desde Oficina', 'Origen Consumo',
                'Diagnóstico', 'Descripción Origen', 'Trabajos/Órdenes'
            ])
            
            # Filtrar columnas que realmente existen en el DataFrame
            columnas_disponibles = [col for col in columnas_finales if col in df.columns]
            df_final = df[columnas_disponibles]
            
            # Generar alertas para dotación
            try:
                alertas = generar_alertas_dotacion(df_final, consumo)
            except Exception as e:
                st.warning(f"⚠️ Error generando alertas: {str(e)}")
                alertas = []
            
            return df_final, alertas
            
        except Exception as e:
            st.error(f"❌ Error en el procesamiento: {str(e)}")
            st.code(traceback.format_exc())
            # Devolver DataFrame vacío y alertas vacías en caso de error
            df_error = pd.DataFrame()
            return df_error, []

def mostrar_metricas_resumen(df: pd.DataFrame, alertas: list = None):
    """Muestra métricas de resumen del análisis incluyendo origen del consumo."""
    
    if df.empty:
        st.warning("⚠️ No hay datos para mostrar métricas")
        return
    
    st.subheader("📊 Resumen del Análisis")
    
    # Métricas principales
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("📋 SKUs Total", len(df))
    
    with col2:
        ok_count = len(df[df['Diagnóstico'].str.contains('✅', na=False)])
        st.metric("✅ Estado OK", ok_count)
    
    with col3:
        faltan_count = len(df[df['Diagnóstico'].str.contains('❌', na=False)])
        st.metric("❌ Faltan Piezas", faltan_count)
    
    with col4:
        exceso_count = len(df[df['Diagnóstico'].str.contains('⚠️', na=False)])
        st.metric("⚠️ Excesos/Problemas", exceso_count)
    
    with col5:
        if 'Reposición' in df.columns:
            reposicion_total = df[df['Reposición'] > 0]['Reposición'].sum()
            st.metric("🔧 Total a Reponer", int(reposicion_total))
        else:
            st.metric("🔧 Total a Reponer", "N/A")
    
    # Métricas de origen del consumo
    if 'Desde Oficina' in df.columns and 'Origen Consumo' in df.columns:
        st.subheader("🏢 Análisis de Origen del Consumo")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            solo_maleta = len(df[df['Origen Consumo'].str.contains('✅ Solo desde maleta', na=False)])
            st.metric("✅ Solo desde Maleta", solo_maleta)
        
        with col2:
            mixto = len(df[df['Origen Consumo'].str.contains('📦 Consumo mixto', na=False)])
            st.metric("📦 Consumo Mixto", mixto)
        
        with col3:
            total_desde_oficina = df['Desde Oficina'].sum()
            st.metric("🏢 Total desde Oficina", int(total_desde_oficina))
        
        with col4:
            if 'Usada' in df.columns:
                skus_con_consumo = len(df[df['Usada'] > 0])
                if skus_con_consumo > 0 and df['Usada'].sum() > 0:
                    porcentaje_oficina = (df['Desde Oficina'].sum() / df['Usada'].sum()) * 100
                    st.metric("📊 % Consumo Oficina", f"{porcentaje_oficina:.1f}%")
                else:
                    st.metric("📊 % Consumo Oficina", "0%")
            else:
                st.metric("📊 % Consumo Oficina", "N/A")
    
    # Mostrar alertas de dotación
    if alertas and len(alertas) > 0:
        st.subheader("🚨 Alertas de Dotación")
        st.warning(f"Se detectaron {len(alertas)} SKUs candidatos para aumentar dotación fija:")
        
        for i, alerta in enumerate(alertas):
            with st.expander(f"⚠️ {alerta['sku']} - {alerta['porcentaje_oficina']:.1f}% desde oficina"):
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric("Consumo Total", int(alerta['consumo_total']))
                    st.metric("Desde Oficina", int(alerta['desde_oficina']))
                
                with col2:
                    st.metric("% desde Oficina", f"{alerta['porcentaje_oficina']:.1f}%")
                    st.metric("Dotación Actual", int(alerta['dotacion_actual']))
                
                with col3:
                    st.info(f"💡 {alerta['sugerencia']}")
                    
                    if alerta['porcentaje_oficina'] >= 60:
                        st.error("🔴 CRÍTICO: Más del 60% desde oficina")
                    elif alerta['porcentaje_oficina'] >= 50:
                        st.warning("🟡 ALTO: Más del 50% desde oficina")
    
    # Métricas adicionales si hay datos de Holded
    if 'Stock Maleta Holded' in df.columns and 'Diff. vs Holded Maleta' in df.columns:
        st.subheader("🏢 Comparación con Holded")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            coinciden_holded = len(df[df['Diff. vs Holded Maleta'] == 0])
            st.metric("🎯 Coinciden con Holded", coinciden_holded)
        
        with col2:
            mayor_holded = len(df[df['Diff. vs Holded Maleta'] > 0])
            st.metric("📈 Mayor que Holded", mayor_holded)
        
        with col3:
            menor_holded = len(df[df['Diff. vs Holded Maleta'] < 0])
            st.metric("📉 Menor que Holded", menor_holded)
    
    # Gráfico de diagnósticos
    if len(df) > 0 and 'Diagnóstico' in df.columns:
        st.subheader("📈 Distribución de Diagnósticos")
        try:
            diagnosticos = df['Diagnóstico'].value_counts()
            if len(diagnosticos) > 0:
                st.bar_chart(diagnosticos)
            else:
                st.info("No hay datos de diagnósticos para mostrar")
        except Exception as e:
            st.warning(f"⚠️ Error creando gráfico de diagnósticos: {str(e)}")
        
        # Gráfico de origen del consumo si está disponible
        if 'Origen Consumo' in df.columns and 'Usada' in df.columns:
            st.subheader("🔄 Distribución de Origen del Consumo")
            try:
                df_con_consumo = df[df['Usada'] > 0]
                if len(df_con_consumo) > 0:
                    origen_consumo = df_con_consumo['Origen Consumo'].value_counts()
                    if len(origen_consumo) > 0:
                        st.bar_chart(origen_consumo)
                    else:
                        st.info("No hay datos de origen de consumo para mostrar")
                else:
                    st.info("No hay SKUs con consumo registrado")
            except Exception as e:
                st.warning(f"⚠️ Error creando gráfico de origen: {str(e)}")

def generar_nombre_archivo(tecnico: str, fecha_inicio: date, fecha_fin: date) -> str:
    """Genera nombre de archivo estandarizado."""
    tecnico_clean = tecnico.lower().replace(' ', '_').replace('ñ', 'n')
    timestamp = datetime.now().strftime("%H%M")
    return f"{tecnico_clean}_{fecha_inicio}_a_{fecha_fin}_{timestamp}.xlsx"

def exportar_a_excel(df: pd.DataFrame, nombre_archivo: str, tecnico: str, fecha_inicio: date, fecha_fin: date, alertas: list = None) -> BytesIO:
    """Exporta los resultados a Excel con formato mejorado incluyendo análisis de origen."""
    
    output = BytesIO()
    
    try:
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Hoja principal con resultados
            df.to_excel(writer, sheet_name='Análisis Detallado', index=False)
            
            # Hoja de resumen
            resumen_data = {
                'Métrica': ['SKUs Total', 'Estado OK', 'Faltan Piezas', 'Excesos/Problemas', 'Total a Reponer'],
                'Valor': [
                    len(df),
                    len(df[df['Diagnóstico'].str.contains('✅', na=False)]) if 'Diagnóstico' in df.columns else 0,
                    len(df[df['Diagnóstico'].str.contains('❌', na=False)]) if 'Diagnóstico' in df.columns else 0,
                    len(df[df['Diagnóstico'].str.contains('⚠️', na=False)]) if 'Diagnóstico' in df.columns else 0,
                    int(df[df['Reposición'] > 0]['Reposición'].sum()) if 'Reposición' in df.columns else 0
                ]
            }
            
            # Agregar métricas de origen del consumo
            if 'Desde Oficina' in df.columns and 'Origen Consumo' in df.columns:
                resumen_data['Métrica'].extend([
                    'Solo desde Maleta', 'Consumo Mixto', 'Total desde Oficina', '% Consumo Oficina'
                ])
                
                solo_maleta = len(df[df['Origen Consumo'].str.contains('✅ Solo desde maleta', na=False)])
                mixto = len(df[df['Origen Consumo'].str.contains('📦 Consumo mixto', na=False)])
                total_oficina = df['Desde Oficina'].sum()
                
                if 'Usada' in df.columns and df['Usada'].sum() > 0:
                    porcentaje_oficina = (df['Desde Oficina'].sum() / df['Usada'].sum()) * 100
                else:
                    porcentaje_oficina = 0
                
                resumen_data['Valor'].extend([
                    solo_maleta, mixto, int(total_oficina), f"{porcentaje_oficina:.1f}%"
                ])
            
            # Agregar métricas de Holded si están disponibles
            if 'Stock Maleta Holded' in df.columns and 'Diff. vs Holded Maleta' in df.columns:
                resumen_data['Métrica'].extend(['Coinciden con Holded', 'Mayor que Holded', 'Menor que Holded'])
                resumen_data['Valor'].extend([
                    len(df[df['Diff. vs Holded Maleta'] == 0]),
                    len(df[df['Diff. vs Holded Maleta'] > 0]),
                    len(df[df['Diff. vs Holded Maleta'] < 0])
                ])
            
            resumen_df = pd.DataFrame(resumen_data)
            resumen_df.to_excel(writer, sheet_name='Resumen', index=False)
            
            # Hoja de alertas si existen
            if alertas and len(alertas) > 0:
                try:
                    alertas_df = pd.DataFrame(alertas)
                    alertas_df.to_excel(writer, sheet_name='Alertas Dotación', index=False)
                except Exception as e:
                    st.warning(f"⚠️ Error exportando alertas: {str(e)}")
            
            # Hoja de metadatos
            metadata = pd.DataFrame({
                'Campo': [
                    'Técnico', 'Fecha Inicio', 'Fecha Fin', 'Fecha Análisis', 
                    'Total SKUs', 'Integración Holded', 'Análisis Oficina', 'Alertas Generadas'
                ],
                'Valor': [
                    tecnico, 
                    fecha_inicio, 
                    fecha_fin, 
                    datetime.now().strftime("%Y-%m-%d %H:%M"), 
                    len(df),
                    'Sí' if 'Stock Maleta Holded' in df.columns else 'No',
                    'Sí' if 'Desde Oficina' in df.columns else 'No',
                    len(alertas) if alertas else 0
                ]
            })
            metadata.to_excel(writer, sheet_name='Metadatos', index=False)
        
        output.seek(0)
        return output
        
    except Exception as e:
        st.error(f"❌ Error exportando a Excel: {str(e)}")
        # Devolver un archivo vacío en caso de error
        output_error = BytesIO()
        with pd.ExcelWriter(output_error, engine='openpyxl') as writer:
            pd.DataFrame({'Error': [f'Error exportando: {str(e)}']}).to_excel(writer, index=False)
        output_error.seek(0)
        return output_error

def cargar_inventario_como_conteo(nombre_archivo: str) -> Optional[pd.DataFrame]:
    """Convierte un inventario guardado en formato de conteo para análisis."""
    try:
        with open(os.path.join(INVENTARIOS_DIR, nombre_archivo), 'r') as f:
            data = json.load(f)
        
        # Convertir inventario a formato de conteo
        conteo_data = []
        for sku, cantidad in data['inventario'].items():
            conteo_data.append({
                'SKU': sku,
                'Cantidad': cantidad
            })
        
        df_conteo = pd.DataFrame(conteo_data)
        df_conteo['SKU'] = df_conteo['SKU'].astype(str).str.strip().str.upper()
        
        return df_conteo
        
    except Exception as e:
        st.error(f"❌ Error cargando inventario: {str(e)}")
        return None

# ============================================================================
# INTERFAZ PRINCIPAL
# ============================================================================

def main():
    st.title("🔧 Analizador de Maletas Técnicas - Sistema Completo")
    st.markdown("### Sistema avanzado de inventario, control y análisis integrado con Holded")
    
    # CSS personalizado para mejor UX en escaneo
    st.markdown("""
    <style>
    /* Estilo para el campo de escaneo */
    .stTextInput > div > div > input {
        font-size: 18px;
        font-weight: bold;
        background-color: #f0f8ff;
        border: 2px solid #4CAF50;
    }
    
    /* Highlight para feedback de escaneo */
    .scan-success {
        background-color: #d4edda;
        border-left: 5px solid #28a745;
        padding: 10px;
        margin: 5px 0;
    }
    
    .scan-warning {
        background-color: #fff3cd;
        border-left: 5px solid #ffc107;
        padding: 10px;
        margin: 5px 0;
    }
    
    /* Botones más grandes para mobile */
    .stButton > button {
        font-size: 16px;
        font-weight: bold;
        height: 3em;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Menú lateral
    menu = st.sidebar.radio(
        "📋 Menú Principal", 
        ["📊 Nuevo análisis", "📱 Inventario", "📂 Historial Análisis", "📁 Historial Inventarios", "ℹ️ Ayuda"],
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
                    list(TECNICOS_CONFIG.keys()),
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
        st.header("📁 Fuentes de Datos")
        
        # Dotación fija (automática)
        with st.expander("📋 Dotación Fija", expanded=False):
            dotacion_df = cargar_dotacion()
            if dotacion_df is None:
                st.stop()
        
        # Opción: Usar inventario o subir archivo de conteo
        st.subheader("📊 Conteo Físico")
        
        opcion_conteo = st.radio(
            "Selecciona la fuente del conteo físico:",
            ["📱 Usar inventario realizado", "📁 Subir archivo de conteo"],
            help="Puedes usar un inventario previamente realizado o subir un archivo tradicional"
        )
        
        conteo_df = None
        stock_holded_data = None
        
        if opcion_conteo == "📱 Usar inventario realizado":
            # Mostrar inventarios disponibles
            inventarios = cargar_inventarios_disponibles()
            inventarios_completados = [inv for inv in inventarios if inv['estado'] == 'completado']
            
            if not inventarios_completados:
                st.warning("⚠️ No hay inventarios completados disponibles")
            else:
                opciones_inventario = [f"{inv['tecnico']} - {inv['fecha']} ({inv['total_skus']} SKUs)" for inv in inventarios_completados]
                
                seleccion_inventario = st.selectbox(
                    "📋 Selecciona el inventario:",
                    opciones_inventario
                )
                
                if seleccion_inventario:
                    idx_seleccionado = opciones_inventario.index(seleccion_inventario)
                    inventario_seleccionado = inventarios_completados[idx_seleccionado]
                    
                    # Cargar el inventario
                    conteo_df = cargar_inventario_como_conteo(inventario_seleccionado['archivo'])
                    
                    if conteo_df is not None:
                        st.success(f"✅ Inventario cargado: {len(conteo_df)} SKUs")
                        
                        # Obtener stock de Holded para este técnico
                        tecnico_inventario = inventario_seleccionado['tecnico']
                        if tecnico_inventario in TECNICOS_CONFIG:
                            warehouse_id = TECNICOS_CONFIG[tecnico_inventario]['warehouse_id']
                            stock_holded_data = obtener_stock_warehouse(warehouse_id)
        
        else:
            # Subir archivo tradicional
            with st.expander("📊 Conteo Físico Manual", expanded=True):
                st.info("💡 El archivo debe tener SKUs en columna B y cantidades en columna D (las primeras 2 filas se ignoran)")
                conteo_df = cargar_archivo("conteo físico", "conteo")
        
        # Archivo de consumo
        with st.expander("🔧 Consumo Registrado", expanded=True):
            st.info("💡 Debe contener columnas: 'ID Parte', 'Cantidad', 'Articulo'")
            consumo_df = cargar_archivo("consumo registrado", "consumo")
        
        # Procesar análisis
        if conteo_df is not None and consumo_df is not None and dotacion_df is not None:
            st.divider()
            
            if st.button("🚀 Procesar Análisis", type="primary", use_container_width=True):
                try:
                    # Para archivos manuales, limpiar datos tradicional
                    if opcion_conteo == "📁 Subir archivo de conteo":
                        dotacion, conteo, consumo = limpiar_datos(dotacion_df, conteo_df, consumo_df)
                    else:
                        # Para inventarios, ya están limpios
                        dotacion = dotacion_df[COLUMNAS_ESPERADAS['dotacion']].copy()
                        dotacion = dotacion.dropna(subset=["SKU"])
                        dotacion['SKU'] = dotacion['SKU'].astype(str).str.strip().str.upper()
                        
                        conteo = conteo_df.copy()
                        
                        consumo = consumo_df[COLUMNAS_ESPERADAS['consumo']].copy()
                        consumo = consumo.dropna(subset=['Articulo'])
                        consumo['SKU'] = consumo['Articulo'].str.extract(r'(^\S+)', expand=False)
                        consumo = consumo[['SKU', 'Cantidad', 'ID Parte']].copy()
                        consumo['SKU'] = consumo['SKU'].astype(str).str.strip().str.upper()
                        consumo['Cantidad'] = pd.to_numeric(consumo['Cantidad'], errors='coerce').fillna(0)
                    
                    # Procesar análisis con datos de Holded si están disponibles
                    resultado, alertas = procesar_analisis(dotacion, conteo, consumo, stock_holded_data, tecnico)
                    
                    st.success("✅ Análisis completado exitosamente")
                    
                    # Mostrar métricas
                    mostrar_metricas_resumen(resultado, alertas)
                    
                    # Mostrar tabla con filtros
                    st.subheader("📋 Resultados Detallados")
                    
                    # Filtros
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        ubicaciones = ['Todas'] + sorted(resultado['Ubicación'].unique().tolist())
                        filtro_ubicacion = st.selectbox("🏷️ Filtrar por Ubicación", ubicaciones)
                    
                    with col2:
                        diagnosticos = ['Todos'] + sorted(resultado['Diagnóstico'].unique().tolist())
                        filtro_diagnostico = st.selectbox("🔍 Filtrar por Diagnóstico", diagnosticos)
                    
                    with col3:
                        solo_reposicion = st.checkbox("🔧 Solo items que requieren reposición")
                    
                    with col4:
                        if 'Origen Consumo' in resultado.columns:
                            origenes = ['Todos'] + sorted(resultado['Origen Consumo'].unique().tolist())
                            filtro_origen = st.selectbox("🏢 Filtrar por Origen", origenes)
                        else:
                            filtro_origen = 'Todos'
                    
                    # Filtros adicionales
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        if 'Stock Maleta Holded' in resultado.columns:
                            solo_diferencias_holded = st.checkbox("🏢 Solo diferencias con Holded")
                        else:
                            solo_diferencias_holded = False
                    
                    with col2:
                        if 'Desde Oficina' in resultado.columns:
                            solo_consumo_oficina = st.checkbox("🏭 Solo consumo desde oficina")
                        else:
                            solo_consumo_oficina = False
                    
                    with col3:
                        if alertas:
                            solo_alertas = st.checkbox("🚨 Solo SKUs con alertas")
                            skus_con_alerta = [a['sku'] for a in alertas]
                        else:
                            solo_alertas = False
                            skus_con_alerta = []
                    
                    # Aplicar filtros
                    df_filtrado = resultado.copy()
                    
                    if filtro_ubicacion != 'Todas':
                        df_filtrado = df_filtrado[df_filtrado['Ubicación'] == filtro_ubicacion]
                    
                    if filtro_diagnostico != 'Todos':
                        df_filtrado = df_filtrado[df_filtrado['Diagnóstico'] == filtro_diagnostico]
                    
                    if filtro_origen != 'Todos':
                        df_filtrado = df_filtrado[df_filtrado['Origen Consumo'] == filtro_origen]
                    
                    if solo_reposicion:
                        df_filtrado = df_filtrado[df_filtrado['Reposición'] > 0]
                    
                    if solo_diferencias_holded and 'Diff. vs Holded Maleta' in df_filtrado.columns:
                        df_filtrado = df_filtrado[df_filtrado['Diff. vs Holded Maleta'] != 0]
                    
                    if solo_consumo_oficina and 'Desde Oficina' in df_filtrado.columns:
                        df_filtrado = df_filtrado[df_filtrado['Desde Oficina'] > 0]
                    
                    if solo_alertas and skus_con_alerta:
                        df_filtrado = df_filtrado[df_filtrado['SKU'].isin(skus_con_alerta)]
                    
                    # Configuración de columnas para display
                    column_config = {
                        "Diagnóstico": st.column_config.TextColumn(
                            "Diagnóstico",
                            help="Estado del item según el análisis completo"
                        ),
                        "Reposición": st.column_config.NumberColumn(
                            "Reposición",
                            help="Cantidad que debe reponerse en maleta",
                            format="%d"
                        ),
                        "Desde Maleta": st.column_config.NumberColumn(
                            "Desde Maleta",
                            help="Cantidad consumida desde la maleta",
                            format="%d"
                        ),
                        "Desde Oficina": st.column_config.NumberColumn(
                            "Desde Oficina", 
                            help="Cantidad consumida desde almacén oficina",
                            format="%d"
                        ),
                        "Origen Consumo": st.column_config.TextColumn(
                            "Origen Consumo",
                            help="Origen predominante del consumo"
                        )
                    }
                    
                    if 'Stock Maleta Holded' in df_filtrado.columns:
                        column_config["Stock Maleta Holded"] = st.column_config.NumberColumn(
                            "Stock Maleta Holded",
                            help="Stock actual en Holded para la maleta",
                            format="%d"
                        )
                        column_config["Diff. vs Holded Maleta"] = st.column_config.NumberColumn(
                            "Diff. vs Holded Maleta",
                            help="Diferencia respecto a Holded maleta",
                            format="%d"
                        )
                    
                    if 'Stock Oficina' in df_filtrado.columns:
                        column_config["Stock Oficina"] = st.column_config.NumberColumn(
                            "Stock Oficina",
                            help="Stock disponible en almacén oficina",
                            format="%d"
                        )
                    
                    # Mostrar tabla filtrada
                    st.dataframe(
                        df_filtrado, 
                        use_container_width=True,
                        hide_index=True,
                        column_config=column_config
                    )
                    
                    # Guardar y descargar
                    st.divider()
                    
                    nombre_archivo = generar_nombre_archivo(tecnico, fecha_inicio, fecha_fin)
                    path_archivo = os.path.join(HISTORIAL_DIR, nombre_archivo)
                    
                    # Guardar en historial
                    try:
                        excel_data = exportar_a_excel(resultado, nombre_archivo, tecnico, fecha_inicio, fecha_fin, alertas)
                        
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
    
    elif menu == "📱 Inventario":
        mostrar_interface_inventario()
    
    elif menu == "📂 Historial Análisis":
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
                    
                    # Mostrar métricas del historial (sin alertas ya que es histórico)
                    mostrar_metricas_resumen(df_hist, [])
                    
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
    
    elif menu == "📁 Historial Inventarios":
        mostrar_historial_inventarios()
    
    elif menu == "ℹ️ Ayuda":
        st.header("ℹ️ Guía de Uso del Sistema")
        
        with st.expander("📱 Módulo de Inventario", expanded=True):
            st.markdown("""
            ### Cómo realizar un inventario:
            
            1. **📱 Ir a "Inventario"** en el menú lateral
            2. **👨‍🔧 Seleccionar técnico** - El sistema carga automáticamente su almacén en Holded
            3. **🔄 Iniciar nuevo inventario** - Limpia datos previos
            4. **🔍 Escanear códigos** - Usar pistola de código de barras o escribir manualmente
            5. **✅ Validación en tiempo real** - El sistema verifica contra dotación y Holded
            6. **💾 Guardar** - Parcial o completar inventario
            
            ### Estados durante el escaneo:
            - **✅ Verde**: SKU válido, coincide con sistemas
            - **⚠️ Amarillo**: SKU no registrado en dotación
            - **🏢 Azul**: Diferencias detectadas con Holded
            """)
        
        with st.expander("📊 Módulo de Análisis"):
            st.markdown("""
            ### Cómo realizar un análisis:
            
            1. **📊 Nuevo análisis** - Selecciona esta opción en el menú
            2. **👨‍🔧 Técnico y fechas** - Define el período de análisis
            3. **📁 Fuentes de datos**:
               - **📱 Usar inventario**: Selecciona un inventario completado
               - **📁 Subir archivo**: Formato tradicional de conteo
               - **🔧 Consumo**: Sube archivo de referencias en partes
            4. **🚀 Procesar** - El sistema integra todos los datos
            5. **📥 Descargar** - Resultados completos en Excel
            
            ### Ventajas del inventario integrado:
            - **🎯 Mayor precisión** - Sin errores de transcripción
            - **⚡ Tiempo real** - Validación inmediata
            - **🏢 Integración Holded** - Comparación automática
            - **📊 Trazabilidad** - Historial completo por técnico
            """)
        
        with st.expander("🔍 Interpretación de estados finales"):
            st.markdown("""
            ### Estados en el análisis final:
            
            **Estados óptimos:**
            - **✅ Perfecto - Sin consumo**: Maleta completa, sin uso
            - **✅ OK - Consumo justificado**: Faltantes explicados por uso desde maleta
            - **✅ OK - Parte desde oficina**: Uso mixto maleta + oficina justificado
            
            **Estados de faltantes:**
            - **❌ Faltan X - Sin justificar**: Faltantes no explicados
            - **❌ Faltan X - No escaneado**: No se encontró en inventario
            - **❌ Maleta vacía - Consumo desde oficina**: Todo el consumo vino de oficina
            - **❌ Faltan X + Y desde oficina**: Faltantes múltiples
            
            **Estados de excesos:**
            - **⚠️ Exceso de X unidades**: Más de lo esperado en maleta
            - **⚠️ Consumo excesivo maleta**: Se usó más de lo justificado desde maleta
            
            **Estados de origen:**
            - **✅ Solo desde maleta**: Todo el consumo vino de la maleta
            - **📦 Consumo mixto**: Parte maleta, parte oficina  
            - **🏢 ±X vs Holded**: Diferencias con sistema Holded
            - **🆕 SKU no registrado**: Encontrado pero no en dotación
            - **🔍 Revisión necesaria**: Requiere verificación manual
            
            ### 🚨 Sistema de Alertas:
            - **Umbral 40%**: Si >40% del consumo viene de oficina → Alerta
            - **Crítico 60%**: Si >60% del consumo viene de oficina → Crítico
            - **Sugerencia automática**: Propone aumentar dotación fija
            """)
        
        with st.expander("🏢 Análisis de Origen del Consumo"):
            st.markdown(f"""
            ### Funcionalidad avanzada:
            
            **Triple análisis de stock:**
            1. **📦 Maleta técnico**: Stock real en maleta del técnico
            2. **🏢 Almacén oficina**: Stock en oficina (`{HOLDED_CONFIG['almacen_oficina']}`)
            3. **📊 Consumo registrado**: Referencias utilizadas en trabajos
            
            **Lógica de origen:**
            - **Si consumo ≤ stock maleta** → "✅ Solo desde maleta"
            - **Si consumo > stock maleta** → Diferencia viene de oficina
            - **Cálculo automático** de cantidades desde cada origen
            
            **Beneficios:**
            - **🎯 Reposición precisa**: Solo lo que falta en maleta
            - **📈 Optimización dotación**: Detecta patrones de consumo
            - **🔍 Trazabilidad completa**: Origen exacto de cada pieza
            - **💡 Sugerencias inteligentes**: Mejora automática del sistema
            
            **Alertas de dotación:**
            - Analiza histórico de consumos
            - Detecta SKUs que se consumen frecuentemente desde oficina
            - Sugiere aumentar dotación fija para optimizar
            - Reduce viajes al almacén oficina
            """)
        
        with st.expander("🏢 Integración con Holded"):
            st.markdown(f"""
            ### Configuración actual:
            
            **Almacenes configurados:**
            - **Francisco Javier**: `{TECNICOS_CONFIG['Francisco Javier']['warehouse_id']}`
            - **Rigoberto**: `{TECNICOS_CONFIG['Rigoberto']['warehouse_id']}`  
            - **Almacén Oficina**: `{HOLDED_CONFIG['almacen_oficina']}`
            
            **APIs utilizadas:**
            - ✅ `/warehouses/{{warehouseId}}/stock` - Stock por almacén específico
            - 🔄 Cache de 5 minutos para optimizar rendimiento
            - 🔍 Validación en tiempo real durante inventario
            - 📊 Análisis de origen automático en análisis
            
            ### Beneficios de la integración completa:
            - **🎯 Cuádruple validación**: Dotación + Inventario + Holded Maleta + Holded Oficina
            - **⚡ Detección inmediata** de discrepancias y origen
            - **📈 Sincronización** con sistema central en tiempo real
            - **🔍 Auditoría completa** de flujos de material
            - **💡 Optimización automática** de dotaciones
            """)
            
            # Agregar información sobre alertas y umbrales
            st.markdown(f"""
            ### Sistema de Alertas Inteligente:
            - **Umbral configurado**: {int(ALERTA_CONSUMO_OFICINA_UMBRAL * 100)}% de consumo desde oficina
            - **Análisis histórico**: Revisa patrones en múltiples análisis
            - **Sugerencias automáticas**: Propone aumentar dotación en +20%
            - **Niveles de alerta**: 
              - 🟡 **{int(ALERTA_CONSUMO_OFICINA_UMBRAL * 100)}%-59%**: Considerar aumentar
              - 🔴 **60%+**: Crítico, aumentar inmediatamente
            """)
            
            st.info("""
            💡 **Consejo**: Las alertas ayudan a optimizar el sistema identificando SKUs que 
            deberían estar en las maletas para reducir dependencia del almacén oficina.
            """)
        
        with st.expander("🏢 Integración con Holded"):
            st.markdown(f"""
            ### Configuración actual:
            
            **Técnicos y almacenes:**
            - **Francisco Javier**: Almacén `{TECNICOS_CONFIG['Francisco Javier']['warehouse_id']}`
            - **Rigoberto**: Almacén `{TECNICOS_CONFIG['Rigoberto']['warehouse_id']}`
            
            **API de Holded:**
            - ✅ Configurada y activa
            - 🔄 Cache de 5 minutos para optimizar rendimiento
            - 🔍 Validación en tiempo real durante inventario
            - 📊 Comparación automática en análisis
            
            ### Beneficios de la integración:
            - **🎯 Triple validación**: Dotación + Inventario + Holded
            - **⚡ Detección inmediata** de discrepancias
            - **📈 Sincronización** con sistema central
            - **🔍 Auditoría completa** de diferencias
            """)
        
        with st.expander("💡 Consejos y buenas prácticas"):
            st.markdown("""
            ### Para inventarios eficientes:
            - **🔋 Batería cargada** en pistola de códigos
            - **📶 Conexión estable** para validación con Holded
            - **🎯 Escaneo sistemático** por secciones
            - **💾 Guardado frecuente** para evitar pérdidas
            - **👥 Un técnico por maleta** para trazabilidad
            
            ### Para análisis precisos:
            - **📅 Fechas exactas** del período analizado
            - **🔄 Inventarios recientes** (máximo 1 semana)
            - **📋 Consumos completos** de todas las órdenes
            - **🔍 Revisión manual** de casos edge
            - **📊 Exportar siempre** resultados finales
            
            ### Solución de problemas:
            - **🔗 Error Holded**: Verificar conexión a internet
            - **❌ SKU no válido**: Verificar formato XXX-XXXXX-XXXX
            - **⚠️ Diferencias grandes**: Revisar manualmente
            - **💾 Error guardando**: Verificar permisos de carpeta
            """)

if __name__ == "__main__":
    main()