import streamlit as st
import pandas as pd
import re
import os

# ─────────────────────────────────────────────
# CONFIGURACIÓN DE PÁGINA
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Sistema de Cobertura Médica – Chernovia",
    page_icon="🏥",
    layout="wide"
)

# ─────────────────────────────────────────────
# CARGA DE DATOS (con caché para rendimiento)
# ─────────────────────────────────────────────
@st.cache_data
def cargar_datos():
    df_glosas = pd.read_csv("COIL_dataset_glosas_salud_1_2M.csv")
    df_servicios = pd.read_csv("COIL_catalogo_servicios_cubiertos.csv")
    df_perfiles = pd.read_csv("COIL_catalogo_perfiles_cobertura.csv")
    return df_glosas, df_servicios, df_perfiles

df_glosas, df_servicios, df_perfiles = cargar_datos()

# ─────────────────────────────────────────────
# FUNCIÓN: PARSEAR LA GLOSA
# ─────────────────────────────────────────────
def parsear_glosa(glosa_texto):
    resultado = {}
    campos = {
        "paciente":         r"Paciente:\s*([^;]+)",
        "dno":              r"DNO:\s*([^;]+)",
        "seguro_social":    r"SeguroSocial:\s*([^;]+)",
        "edad":             r"Edad:\s*(\d+)",
        "perfil_cobertura": r"PerfilCobertura:\s*([^;]+)",
        "servicio":         r"ServicioSolicitado:\s*([^;]+)",
        "medicacion":       r"Medicacion:\s*(.+)$"
    }
    for campo, patron in campos.items():
        match = re.search(patron, glosa_texto, re.IGNORECASE)
        resultado[campo] = match.group(1).strip() if match else "N/A"
    return resultado

# ─────────────────────────────────────────────
# FUNCIÓN: APLICAR REGLA DE COBERTURA
# ─────────────────────────────────────────────
def evaluar_cobertura(servicio_solicitado, perfil_cobertura, valor_procedimiento, df_servicios, df_perfiles):
    # Buscar si el servicio está en el catálogo (comparación flexible)
    servicios_lista = df_servicios["servicio"].str.lower().str.strip().tolist()
    servicio_lower = servicio_solicitado.lower().strip()
    cubre = servicio_lower in servicios_lista

    porcentaje = 0
    valor_cubierto = 0.0
    servicio_info = None

    if cubre:
        # Obtener porcentaje según perfil
        perfil_row = df_perfiles[df_perfiles["perfil_cobertura"].str.upper() == perfil_cobertura.upper()]
        porcentaje = int(perfil_row["porcentaje_cobertura_si_el_servicio_esta_cubierto"].values[0]) if not perfil_row.empty else 0
        valor_cubierto = valor_procedimiento * (porcentaje / 100)
        # Info del servicio
        servicio_info = df_servicios[df_servicios["servicio"].str.lower() == servicio_lower].iloc[0]

    return cubre, porcentaje, round(valor_cubierto, 2), servicio_info

# ─────────────────────────────────────────────
# ENCABEZADO
# ─────────────────────────────────────────────
st.title("🏥 Sistema de Cobertura Médica")
st.markdown("### Gobierno de Chernovia — Clasificación de Solicitudes")
st.markdown("---")

# ─────────────────────────────────────────────
# MÉTRICAS GENERALES (panel superior)
# ─────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total solicitudes", f"{len(df_glosas):,}")
col2.metric("Fecha desde", str(df_glosas["fecha_solicitud"].min())[:10])
col3.metric("Fecha hasta", str(df_glosas["fecha_solicitud"].max())[:10])
col4.metric("Entidades emisoras", df_glosas["entidad_emisora"].nunique())

st.markdown("---")

# ─────────────────────────────────────────────
# BUSCADOR
# ─────────────────────────────────────────────
st.subheader("🔍 Consultar solicitud")

col_busq1, col_busq2 = st.columns([2, 1])

with col_busq1:
    id_ingresado = st.text_input("Ingresa el ID de la solicitud", placeholder="Ej: CHV-0000001")

with col_busq2:
    buscar = st.button("Buscar", type="primary", use_container_width=True)

# ─────────────────────────────────────────────
# RESULTADO DE LA CONSULTA
# ─────────────────────────────────────────────
if buscar and id_ingresado:
    fila = df_glosas[df_glosas["id_solicitud"].str.strip() == id_ingresado.strip()]

    if fila.empty:
        st.error(f"❌ No se encontró ninguna solicitud con ID: **{id_ingresado}**")
    else:
        row = fila.iloc[0]
        datos_glosa = parsear_glosa(str(row["glosa"]))
        cubre, porcentaje, valor_cubierto, servicio_info = evaluar_cobertura(
            datos_glosa["servicio"],
            datos_glosa["perfil_cobertura"],
            float(row["valor_procedimiento"]),
            df_servicios,
            df_perfiles
        )

        st.markdown("---")
        # Resultado principal
        if cubre:
            st.success(f"✅ SOLICITUD CUBIERTA — {porcentaje}% de cobertura aplicada")
        else:
            st.error("❌ SOLICITUD NO CUBIERTA — El servicio no está en el catálogo público")

        # Detalle en columnas
        col_a, col_b = st.columns(2)

        with col_a:
            st.markdown("#### 👤 Datos del paciente")
            st.write(f"**Nombre:** {datos_glosa['paciente']}")
            st.write(f"**DNO:** {datos_glosa['dno']}")
            st.write(f"**Seguro Social:** {datos_glosa['seguro_social']}")
            st.write(f"**Edad:** {datos_glosa['edad']} años")
            st.write(f"**Perfil de cobertura:** {datos_glosa['perfil_cobertura']}")

            st.markdown("#### 💊 Medicación")
            medicamentos = datos_glosa["medicacion"].split("|")
            for med in medicamentos:
                st.write(f"- {med.strip()}")

        with col_b:
            st.markdown("#### 🏥 Datos de la solicitud")
            st.write(f"**ID Solicitud:** {row['id_solicitud']}")
            st.write(f"**Fecha:** {row['fecha_solicitud']}")
            st.write(f"**Medio emisor:** {row['medio_emisor']}")
            st.write(f"**Entidad emisora:** {row['entidad_emisora']}")
            st.write(f"**Servicio solicitado:** {datos_glosa['servicio']}")
            st.write(f"**Valor del procedimiento:** ${float(row['valor_procedimiento']):,.0f}")

            st.markdown("#### 💰 Decisión de cobertura")
            st.write(f"**¿Cubre?:** {'✅ Sí' if cubre else '❌ No'}")
            st.write(f"**Porcentaje aplicado:** {porcentaje}%")
            st.write(f"**Valor cubierto por el Estado:** ${valor_cubierto:,.0f}")
            st.write(f"**Valor a cargo del paciente:** ${float(row['valor_procedimiento']) - valor_cubierto:,.0f}")

            if servicio_info is not None:
                st.markdown("#### 📋 Info del catálogo")
                st.write(f"**Código:** {servicio_info['codigo_servicio']}")
                st.write(f"**Categoría:** {servicio_info['categoria']}")
                st.write(f"**Rango referencia:** ${servicio_info['valor_min_referencia']:,} – ${servicio_info['valor_max_referencia']:,}")

# ─────────────────────────────────────────────
# EXPLORADOR POR FILTROS (sección secundaria)
# ─────────────────────────────────────────────
st.markdown("---")
st.subheader("📊 Explorar solicitudes por filtro")

col_f1, col_f2, col_f3 = st.columns(3)
with col_f1:
    entidades = ["Todas"] + sorted(df_glosas["entidad_emisora"].dropna().unique().tolist())
    entidad_sel = st.selectbox("Entidad emisora", entidades)
with col_f2:
    medios = ["Todos"] + sorted(df_glosas["medio_emisor"].dropna().unique().tolist())
    medio_sel = st.selectbox("Medio emisor", medios)
with col_f3:
    n_filas = st.slider("Cantidad de registros a mostrar", 5, 100, 20)

df_filtrado = df_glosas.copy()
if entidad_sel != "Todas":
    df_filtrado = df_filtrado[df_filtrado["entidad_emisora"] == entidad_sel]
if medio_sel != "Todos":
    df_filtrado = df_filtrado[df_filtrado["medio_emisor"] == medio_sel]

st.dataframe(
    df_filtrado[["id_solicitud", "fecha_solicitud", "medio_emisor", "valor_procedimiento", "entidad_emisora"]]
    .head(n_filas)
    .reset_index(drop=True),
    use_container_width=True
)