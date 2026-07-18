import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

st.set_page_config(page_title="Minimarket Nube", layout="wide", page_icon="🏪")

# 1. CONEXIÓN (Se hace solo 1 vez y se mantiene abierta)
@st.cache_resource
def conectar_gsheets():
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    sheet = client.open_by_url(st.secrets["url_planilla"])
    return sheet.worksheet("Productos"), sheet.worksheet("Ventas")

try:
    ws_productos, ws_ventas = conectar_gsheets()
except Exception as e:
    st.error("Error de conexión. Espera 1 minuto y recarga la página.")
    st.stop()

# 2. CACHÉ DE INVENTARIO (Lee los datos 1 vez por minuto, evitando bloqueos de Google)
@st.cache_data(ttl=60)
def obtener_inventario():
    try:
        records = ws_productos.get_all_records()
        if not records:
            return pd.DataFrame(columns=["Codigo", "Nombre", "Precio", "Stock", "Granel"])
        df = pd.DataFrame(records)
        df["Codigo"] = df["Codigo"].astype(str)
        return df
    except:
        return pd.DataFrame()

if 'carrito' not in st.session_state:
    st.session_state.carrito = []

st.title("🏪 Sistema POS Web - Conectado a Google Sheets")

tab1, tab2, tab3, tab4 = st.tabs(["🛒 Caja / Ventas", "📦 Inventario", "⚙️ Actualizar", "📊 Historial Diario"])

# ==========================================
# TAB 1: CAJA / VENTAS
# ==========================================
with tab1:
    df_inv = obtener_inventario()
    col_izq, col_der = st.columns([1, 1.2])
    
    with col_izq:
        st.subheader("Lectura de Productos")
        codigo_ingresado = st.text_input("Escanee o digite el código (Enter para buscar):", key="lector_codigo")
        
        if codigo_ingresado:
            producto = df_inv[df_inv["Codigo"] == codigo_ingresado.strip()]
            
            if not producto.empty:
                prod_data = producto.iloc[0]
                codigo = prod_data["Codigo"]
                nombre = prod_data["Nombre"]
                precio = float(prod_data["Precio"])
                stock = float(prod_data["Stock"])
                
                # Soporta tanto "1" como "SI" para el granel
                es_granel = str(prod_data["Granel"]).strip().upper() == "SI" or str(prod_data["Granel"]) == "1"
                
                if stock <= 0:
                    st.error(f"⚠️ {nombre} no tiene stock disponible.")
                else:
                    if es_granel:
                        peso = st.number_input(f"Ingrese peso en Kg para {nombre}:", min_value=0.01, max_value=float(stock), step=0.05)
                        if st.button(f"Confirmar peso y Agregar"):
                            subtotal = round(precio * peso, 2)
                            st.session_state.carrito.append({'codigo': codigo, 'nombre': nombre, 'precio': precio, 'cantidad': peso, 'subtotal': subtotal})
                            st.success(f"Agregado {peso}kg de {nombre}")
                    else:
                        if st.button(f"Agregar {nombre} (Presione Enter)"):
                            st.session_state.carrito.append({'codigo': codigo, 'nombre': nombre, 'precio': precio, 'cantidad': 1, 'subtotal': precio})
                            st.success(f"Agregado {nombre}")
            else:
                st.error("❌ Código no encontrado.")

    with col_der:
        st.subheader("🧾 Cuenta Actual")
        if st.session_state.carrito:
            df_carrito = pd.DataFrame(st.session_state.carrito)
            st.dataframe(df_carrito[['nombre', 'precio', 'cantidad', 'subtotal']], use_container_width=True)
            total = df_carrito['subtotal'].sum()
            st.metric(label="TOTAL A COBRAR", value=f"S/. {total:.2f}")
            
            metodo_pago = st.selectbox("Método de Pago:", ["Efectivo", "Yape / Plin", "Tarjeta"])
            
            if st.button("✅ Registrar y Cobrar Venta", type="primary", use_container_width=True):
                fecha_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                detalles = " | ".join([f"{r['cantidad']}x {r['nombre']}" for r in st.session_state.carrito])
                
                try:
                    ws_ventas.append_row([fecha_str, float(total), metodo_pago, detalles])
                    
                    for item in st.session_state.carrito:
                        cell = ws_productos.find(str(item['codigo']))
                        stock_actual = float(ws_productos.cell(cell.row, 4).value)
                        ws_productos.update_cell(cell.row, 4, stock_actual - item['cantidad'])
                    
                    st.session_state.carrito = []
                    obtener_inventario.clear() # Fuerza a descargar el nuevo stock
                    st.success("🎉 ¡Venta registrada exitosamente!")
                    st.rerun()
                except Exception as e:
                    st.error("Hubo un error guardando la venta. Revisa la conexión.")
            
            if st.button("🗑️ Cancelar Venta", use_container_width=True):
                st.session_state.carrito = []
                st.rerun()
        else:
            st.info("Carrito vacío. Escanea un producto.")

# ==========================================
# TAB 2 Y 4: INVENTARIO Y REPORTES
# ==========================================
with tab2:
    st.subheader("📦 Registrar Nuevo Producto")
    with st.form("nuevo_prod"):
        c_cod = st.text_input("Código")
        c_nom = st.text_input("Nombre")
        c_pre = st.number_input("Precio", min_value=0.0, step=0.10)
        c_sto = st.number_input("Stock Inicial", min_value=0.0, step=1.0)
        c_gra = st.selectbox("¿Es a Granel?", ["NO", "SI"])
        if st.form_submit_button("Guardar en Google Sheets"):
            if c_cod and c_nom:
                try:
                    ws_productos.append_row([c_cod, c_nom, float(c_pre), float(c_sto), c_gra])
                    obtener_inventario.clear()
                    st.success(f"Producto guardado.")
                except:
                    st.error("Error al guardar.")
            else:
                st.error("Ingrese código y nombre válidos.")

with tab4:
    st.subheader("📊 Ventas Registradas")
    if st.button("🔄 Refrescar Tabla"):
        st.rerun()
    try:    
        records_v = ws_ventas.get_all_records()
        if records_v:
            df_v = pd.DataFrame(records_v)
            st.dataframe(df_v, use_container_width=True)
            st.metric("Total Acumulado", f"S/. {df_v['Total'].sum():.2f}")
        else:
            st.info("Aún no hay ventas registradas.")
    except:
        st.error("No se pudo cargar el historial.")
