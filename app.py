import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

st.set_page_config(page_title="Minimarket Nube", layout="wide", page_icon="🏪")

# --- CONEXIÓN A GOOGLE SHEETS ---
@st.cache_resource
def conectar_gsheets():
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_url(st.secrets["url_planilla"])

try:
    sheet = conectar_gsheets()
    ws_productos = sheet.worksheet("Productos")
    ws_ventas = sheet.worksheet("Ventas")
except Exception as e:
    st.error("Error al conectar con Google Sheets. Verifique sus secretos (Secrets) y permisos.")
    st.stop()

# Funciones de lectura rápida
def obtener_inventario():
    records = ws_productos.get_all_records()
    if not records:
        return pd.DataFrame(columns=["Codigo", "Nombre", "Precio", "Stock", "Granel"])
    df = pd.DataFrame(records)
    df["Codigo"] = df["Codigo"].astype(str) # Asegurar que el código sea texto
    return df

if 'carrito' not in st.session_state:
    st.session_state.carrito = []

st.title("🏪 Sistema POS Web - Conectado a Google Sheets")

tab1, tab2, tab3, tab4 = st.tabs(["🛒 Caja / Ventas", "📦 Control de Inventario", "⚙️ Actualizar", "📊 Historial Diario"])

# ==========================================
# TAB 1: CAJA / VENTAS
# ==========================================
with tab1:
    df_inv = obtener_inventario()
    col_izq, col_der = st.columns([1, 1.2])
    
    with col_izq:
        st.subheader("Lectura de Productos")
        codigo_ingresado = st.text_input("Escanee o digite el código (Enter para buscar):", key="lector")
        
        if codigo_ingresado:
            # Buscar en el dataframe
            producto = df_inv[df_inv["Codigo"] == codigo_ingresado.strip()]
            
            if not producto.empty:
                prod_data = producto.iloc[0]
                codigo = prod_data["Codigo"]
                nombre = prod_data["Nombre"]
                precio = float(prod_data["Precio"])
                stock = float(prod_data["Stock"])
                es_granel = str(prod_data["Granel"]).strip().upper() == "SI"
                
                if stock <= 0:
                    st.error(f"⚠️ {nombre} no tiene stock disponible.")
                else:
                    if es_granel:
                        peso = st.number_input(f"Ingrese peso en Kg para {nombre}:", min_value=0.01, max_value=float(stock), step=0.05)
                        if st.button(f"Confirmar peso", key=f"btn_{codigo}"):
                            subtotal = round(precio * peso, 2)
                            st.session_state.carrito.append({
                                'codigo': codigo, 'nombre': nombre, 'precio': precio, 'cantidad': peso, 'subtotal': subtotal
                            })
                            st.success(f"Agregado {peso}kg de {nombre}")
                            st.rerun()
                    else:
                        st.session_state.carrito.append({
                            'codigo': codigo, 'nombre': nombre, 'precio': precio, 'cantidad': 1, 'subtotal': precio
                        })
                        st.success(f"Agregado {nombre}")
                        st.rerun()
            else:
                st.error("❌ Código no encontrado en Google Sheets.")

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
                
                # Guardar Venta en Google Sheets
                ws_ventas.append_row([fecha_str, float(total), metodo_pago, detalles])
                
                # Descontar Stock
                for item in st.session_state.carrito:
                    # Encontrar la fila del producto
                    try:
                        cell = ws_productos.find(str(item['codigo']))
                        # Columna 4 es Stock (asumiendo orden: Codigo, Nombre, Precio, Stock, Granel)
                        stock_actual = float(ws_productos.cell(cell.row, 4).value)
                        ws_productos.update_cell(cell.row, 4, stock_actual - item['cantidad'])
                    except Exception as e:
                        st.error(f"Error al descontar stock de {item['nombre']}")
                
                st.session_state.carrito = []
                st.success("🎉 ¡Venta registrada en Google Sheets exitosamente!")
                st.rerun()
            
            if st.button("🗑️ Cancelar Venta", use_container_width=True):
                st.session_state.carrito = []
                st.rerun()
        else:
            st.info("Carrito vacío.")

# ==========================================
# TAB 2 & 3: INVENTARIO Y PRECIOS
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
                ws_productos.append_row([c_cod, c_nom, float(c_pre), float(c_sto), c_gra])
                st.success(f"Producto {c_nom} guardado en la nube.")
            else:
                st.error("Ingrese código y nombre válidos.")

with tab4:
    st.subheader("📊 Ventas Registradas en Google Sheets")
    records_v = ws_ventas.get_all_records()
    if records_v:
        df_v = pd.DataFrame(records_v)
        st.dataframe(df_v, use_container_width=True)
        st.metric("Total Acumulado", f"S/. {df_v['Total'].sum():.2f}")
    else:
        st.info("Aún no hay ventas registradas.")
