import streamlit as st

from athena_client import (
    buscar_solicitud_por_id,
    explorar_solicitudes,
    obtener_opciones_filtros,
    obtener_particiones_validas,
)

CACHE_TTL_SECONDS = 3600
PAGE_SIZE = 20


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def buscar_solicitud_cached(id_solicitud: str, fechas_particion: tuple[str, ...]):
    return buscar_solicitud_por_id(
        id_solicitud,
        fecha_dias=list(fechas_particion),
    )


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def cargar_opciones_filtros(fecha_str: str):
    return obtener_opciones_filtros(fecha_str)


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def explorar_solicitudes_cached(
    fecha_str: str,
    entidad: str,
    medio: str,
    decision: str,
    limite: int,
    offset: int,
):
    return explorar_solicitudes(
        fecha_dia=fecha_str,
        entidad=entidad,
        medio=medio,
        decision=decision,
        limite=limite,
        offset=offset,
    )


def consultar_pagina_solicitudes(
    fecha_str: str,
    entidad: str,
    medio: str,
    decision: str,
    pagina: int,
) -> None:
    limite_consulta = PAGE_SIZE + 1
    offset = pagina * PAGE_SIZE
    df = explorar_solicitudes_cached(
        fecha_str=fecha_str,
        entidad=entidad,
        medio=medio,
        decision=decision,
        limite=limite_consulta,
        offset=offset,
    )

    st.session_state["df_filtrado"] = df.head(PAGE_SIZE)
    st.session_state["explorador_tiene_siguiente"] = len(df) > PAGE_SIZE
    st.session_state["explorador_pagina"] = pagina
    st.session_state["criterios_df_filtrado"] = {
        "fecha": fecha_str,
        "entidad": entidad,
        "medio": medio,
        "decision": decision,
        "pagina": pagina,
        "registros_por_pagina": PAGE_SIZE,
    }


particiones_validas = obtener_particiones_validas()

st.title("Sistema de consulta de cobertura médica")

st.markdown("### 🔎 Buscar solicitud por ID")

id_ingresado = st.text_input("ID de solicitud", placeholder="Ej: CHV-0447260")

if st.button("Buscar solicitud"):
    if not id_ingresado:
        st.warning("Ingresa un ID de solicitud.")
    else:
        with st.spinner("Consultando datos Gold en Athena..."):
            fila = buscar_solicitud_cached(id_ingresado, tuple(particiones_validas))

        if fila.empty:
            st.error(f"❌ No se encontró ninguna solicitud con ID: {id_ingresado}")
        else:
            row = fila.iloc[0]

            decision = str(row["decision_cobertura"]).upper()
            cubre = decision == "CUBRE"

            valor_procedimiento = float(row["valor_procedimiento"])
            monto_cubierto = float(row["monto_cubierto"])
            valor_paciente = valor_procedimiento - monto_cubierto

            st.markdown("---")

            if cubre:
                st.success(
                    f"✅ SOLICITUD CUBIERTA — "
                    f"{int(row['porcentaje_cobertura'])}% de cobertura aplicada"
                )
            else:
                st.error("❌ SOLICITUD NO CUBIERTA")

            st.info(f"Razón de decisión: {row['razon_decision']}")

            col_a, col_b = st.columns(2)

            with col_a:
                st.markdown("#### 👤 Datos del paciente")
                st.write(f"Nombre: {row['paciente_nombre']}")
                st.write(f"DNO: {row['paciente_dno']}")
                st.write(f"Seguro Social: {row['paciente_seguro_social']}")
                st.write(f"Edad: {int(row['edad'])} años")
                st.write(f"Perfil de cobertura: {row['perfil_cobertura']}")

                st.markdown("#### 💊 Medicación")
                medicacion_raw = str(row["medicacion"])
                medicacion_limpia = medicacion_raw.replace("[", "").replace("]", "")

                medicamentos = medicacion_limpia.split("|")

                for med in medicamentos:
                    med = med.strip()
                    if med:
                        st.write(f"- {med}")

            with col_b:
                st.markdown("#### 🏥 Datos de la solicitud")
                st.write(f"ID Solicitud: {row['id_solicitud']}")
                st.write(f"Fecha: {row['fecha_solicitud']}")
                st.write(f"Medio emisor: {row['medio_emisor']}")
                st.write(f"Entidad emisora: {row['entidad_emisora']}")
                st.write(f"Servicio solicitado: {row['servicio_solicitado']}")
                st.write(f"Valor del procedimiento: ${valor_procedimiento:,.0f}")

                st.markdown("#### 💰 Decisión de cobertura")
                st.write(f"¿Cubre?: {'✅ Sí' if cubre else '❌ No'}")
                st.write(f"Porcentaje aplicado: {int(row['porcentaje_cobertura'])}%")
                st.write(f"Monto cubierto por el Estado: ${monto_cubierto:,.0f}")
                st.write(f"Valor a cargo del paciente: ${valor_paciente:,.0f}")

                st.markdown("#### 🧾 Trazabilidad")
                st.write(
                    f"Timestamp de procesamiento: {row['timestamp_procesamiento']}"
                )
                st.write(f"Día de partición: {row['fecha_dia']}")

st.markdown("---")
st.subheader("📊 Explorar solicitudes por filtro")

fecha_filtro_str = st.selectbox(
    "Día a explorar",
    particiones_validas,
    key="fecha_explorador",
)

with st.spinner("Cargando filtros disponibles..."):
    opciones_filtros = cargar_opciones_filtros(fecha_filtro_str)

entidades = ["Todas"] + opciones_filtros.get("entidad_emisora", [])
medios = ["Todos"] + opciones_filtros.get("medio_emisor", [])
decisiones = ["Todas"] + opciones_filtros.get("decision_cobertura", [])

with st.form("form_explorar_solicitudes"):
    col_f1, col_f2, col_f3 = st.columns(3)

    with col_f1:
        entidad_sel = st.selectbox("Entidad emisora", entidades)

    with col_f2:
        medio_sel = st.selectbox("Medio emisor", medios)

    with col_f3:
        decision_sel = st.selectbox("Decisión", decisiones)

    consultar = st.form_submit_button("Consultar solicitudes")

if consultar:
    with st.spinner("Consultando solicitudes..."):
        consultar_pagina_solicitudes(
            fecha_str=fecha_filtro_str,
            entidad=entidad_sel,
            medio=medio_sel,
            decision=decision_sel,
            pagina=0,
        )

if "df_filtrado" in st.session_state:
    criterios = st.session_state.get("criterios_df_filtrado", {})
    pagina_actual = int(st.session_state.get("explorador_pagina", 0))
    tiene_siguiente = bool(st.session_state.get("explorador_tiene_siguiente", False))

    st.caption(
        "Última consulta: "
        f"fecha={criterios.get('fecha', '-')}, "
        f"entidad={criterios.get('entidad', '-')}, "
        f"medio={criterios.get('medio', '-')}, "
        f"decisión={criterios.get('decision', '-')}, "
        f"página={pagina_actual + 1}, "
        f"registros por página={PAGE_SIZE}"
    )
    st.dataframe(st.session_state["df_filtrado"], use_container_width=True)

    col_prev, col_page, col_next = st.columns([1, 2, 1])

    with col_prev:
        anterior = st.button("Anterior", disabled=pagina_actual == 0)

    with col_page:
        st.markdown(f"<center>Página {pagina_actual + 1}</center>", unsafe_allow_html=True)

    with col_next:
        siguiente = st.button("Siguiente", disabled=not tiene_siguiente)

    if anterior or siguiente:
        nueva_pagina = pagina_actual - 1 if anterior else pagina_actual + 1
        with st.spinner("Consultando solicitudes..."):
            consultar_pagina_solicitudes(
                fecha_str=criterios["fecha"],
                entidad=criterios["entidad"],
                medio=criterios["medio"],
                decision=criterios["decision"],
                pagina=nueva_pagina,
            )
        st.rerun()
else:
    st.info("Configura los filtros y presiona Consultar solicitudes.")
