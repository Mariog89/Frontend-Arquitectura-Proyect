import altair as alt
import pandas as pd
import streamlit as st

from athena_client import (
    buscar_solicitud_por_id_s3,
    calcular_id_bucket,
    explorar_solicitudes,
    leer_cobertura_por_perfil_s3,
    leer_costos_por_entidad_s3,
    leer_total_ordenes_por_dia_s3,
    leer_trazabilidad_por_entidad_s3,
    obtener_opciones_filtros,
    obtener_particiones_validas,
)

CACHE_TTL_SECONDS = 3600
PAGE_SIZE = 20


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def buscar_solicitud_cached(id_solicitud: str):
    return buscar_solicitud_por_id_s3(id_solicitud)


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def cargar_opciones_filtros(fecha_str: str):
    return obtener_opciones_filtros(fecha_str)


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def explorar_solicitudes_cached(
    fecha_str: str,
    perfil: str,
    servicio: str,
    decision: str,
    limite: int,
    offset: int,
):
    return explorar_solicitudes(
        fecha_dia=fecha_str,
        perfil=perfil,
        servicio=servicio,
        decision=decision,
        limite=limite,
        offset=offset,
    )


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def leer_cobertura_por_perfil_cached():
    return leer_cobertura_por_perfil_s3()


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def leer_costos_por_entidad_cached(fecha_dia: str | None = None):
    return leer_costos_por_entidad_s3(fecha_dia=fecha_dia)


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def leer_total_ordenes_por_dia_cached():
    return leer_total_ordenes_por_dia_s3()


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def leer_trazabilidad_por_entidad_cached():
    return leer_trazabilidad_por_entidad_s3()


def consultar_pagina_solicitudes(
    fecha_str: str,
    perfil: str,
    servicio: str,
    decision: str,
    pagina: int,
) -> None:
    limite_consulta = PAGE_SIZE + 1
    offset = pagina * PAGE_SIZE
    df = explorar_solicitudes_cached(
        fecha_str=fecha_str,
        perfil=perfil,
        servicio=servicio,
        decision=decision,
        limite=limite_consulta,
        offset=offset,
    )

    st.session_state["df_filtrado"] = df.head(PAGE_SIZE)
    st.session_state["explorador_tiene_siguiente"] = len(df) > PAGE_SIZE
    st.session_state["explorador_pagina"] = pagina
    st.session_state["criterios_df_filtrado"] = {
        "fecha": fecha_str,
        "perfil": perfil,
        "servicio": servicio,
        "decision": decision,
        "pagina": pagina,
        "registros_por_pagina": PAGE_SIZE,
    }


def numero(valor, default: float = 0.0) -> float:
    convertido = pd.to_numeric(pd.Series([valor]), errors="coerce").iloc[0]
    if pd.isna(convertido):
        return default
    return float(convertido)


def moneda(valor) -> str:
    return f"${numero(valor):,.0f}"


def porcentaje(valor) -> str:
    return f"{numero(valor):,.2f}%"


def normalizar_medicamentos(valor) -> list[str]:
    if isinstance(valor, (list, tuple, set)):
        return [str(item).strip() for item in valor if str(item).strip()]

    texto = str(valor).strip()
    if not texto or texto.lower() in {"nan", "none", "<na>"}:
        return []

    texto = texto.replace("[", "").replace("]", "").replace("'", "").replace('"', "")
    separador = "|" if "|" in texto else ","
    return [item.strip() for item in texto.split(separador) if item.strip()]


def preparar_numericas(df: pd.DataFrame, columnas: list[str]) -> pd.DataFrame:
    df = df.copy()
    for columna in columnas:
        if columna in df.columns:
            df[columna] = pd.to_numeric(df[columna], errors="coerce")
    return df


def mostrar_error_carga(nombre: str, error: Exception) -> None:
    st.error(f"No fue posible cargar {nombre}: {error}")


def render_busqueda() -> None:
    st.markdown("### 🔎 Buscar solicitud por ID")

    id_ingresado = st.text_input("ID de solicitud", placeholder="Ej: CHV-0447004")

    if st.button("Buscar solicitud"):
        if not id_ingresado:
            st.warning("Ingresa un ID de solicitud.")
            return

        try:
            id_bucket = calcular_id_bucket(id_ingresado)
            with st.spinner(f"Consultando bucket Gold S3 id_bucket={id_bucket}..."):
                fila = buscar_solicitud_cached(id_ingresado)
        except ValueError as error:
            st.error(str(error))
            return
        except Exception as error:
            st.error(f"No fue posible consultar la solicitud: {error}")
            return

        if fila.empty:
            st.error(f"❌ No se encontró ninguna solicitud con ID: {id_ingresado}")
            return

        row = fila.iloc[0]
        decision = str(row.get("decision_cobertura", "")).upper()
        cubre = decision == "CUBRE"
        valor_procedimiento = numero(row.get("valor_procedimiento"))
        monto_cubierto = numero(row.get("monto_cubierto"))
        valor_paciente = valor_procedimiento - monto_cubierto

        st.markdown("---")

        if cubre:
            st.success(
                "✅ SOLICITUD CUBIERTA — "
                f"{int(numero(row.get('porcentaje_cobertura')))}% de cobertura aplicada"
            )
        else:
            st.error("❌ SOLICITUD NO CUBIERTA")

        st.info(f"Razón de decisión: {row.get('razon_decision', '-')}")

        col_a, col_b = st.columns(2)

        with col_a:
            st.markdown("#### 👤 Datos del paciente")
            st.write(f"Nombre: {row.get('paciente_nombre', '-')}")
            st.write(f"DNO: {row.get('paciente_dno', '-')}")
            st.write(f"Seguro Social: {row.get('paciente_seguro_social', '-')}")
            st.write(f"Edad: {int(numero(row.get('edad')))} años")
            st.write(f"Perfil de cobertura: {row.get('perfil_cobertura', '-')}")

            st.markdown("#### 💊 Medicación")
            medicamentos = normalizar_medicamentos(row.get("medicacion", ""))
            if medicamentos:
                for med in medicamentos:
                    st.write(f"- {med}")
            else:
                st.write("Sin medicación registrada.")

        with col_b:
            st.markdown("#### 🏥 Datos de la solicitud")
            st.write(f"ID Solicitud: {row.get('id_solicitud', '-')}")
            st.write(f"Fecha: {row.get('fecha_solicitud', '-')}")
            st.write(f"Medio emisor: {row.get('medio_emisor', '-')}")
            st.write(f"Entidad emisora: {row.get('entidad_emisora', '-')}")
            st.write(f"Servicio solicitado: {row.get('servicio_solicitado', '-')}")
            st.write(f"Valor del procedimiento: {moneda(valor_procedimiento)}")

            st.markdown("#### 💰 Decisión de cobertura")
            st.write(f"¿Cubre?: {'✅ Sí' if cubre else '❌ No'}")
            st.write(
                f"Porcentaje aplicado: {int(numero(row.get('porcentaje_cobertura')))}%"
            )
            st.write(f"Monto cubierto por el Estado: {moneda(monto_cubierto)}")
            st.write(f"Valor a cargo del paciente: {moneda(valor_paciente)}")

            st.markdown("#### 🧾 Trazabilidad")
            st.write(
                f"Timestamp de procesamiento: {row.get('timestamp_procesamiento', '-')}"
            )
            st.write(f"Día de partición: {row.get('fecha_dia', '-')}")


def render_explorador(particiones_validas: list[str]) -> None:
    st.subheader("📊 Explorar solicitudes por filtro")

    fecha_filtro_str = st.selectbox(
        "Día a explorar",
        particiones_validas,
        key="fecha_explorador",
    )

    if st.session_state.get("explorador_filtros_fecha") != fecha_filtro_str:
        st.session_state.pop("explorador_opciones_filtros", None)

    if st.button("Cargar filtros disponibles"):
        with st.spinner("Cargando filtros disponibles..."):
            st.session_state["explorador_opciones_filtros"] = cargar_opciones_filtros(
                fecha_filtro_str
            )
            st.session_state["explorador_filtros_fecha"] = fecha_filtro_str

    opciones_filtros = st.session_state.get("explorador_opciones_filtros")

    if opciones_filtros is None:
        st.info("Carga los filtros disponibles antes de consultar solicitudes.")
        return

    perfiles = ["Todos"] + opciones_filtros.get("perfil_cobertura", [])
    servicios = ["Todos"] + opciones_filtros.get("servicio_solicitado", [])
    decisiones = ["Todas"] + opciones_filtros.get("decision_cobertura", [])

    with st.form("form_explorar_solicitudes"):
        col_f1, col_f2, col_f3 = st.columns(3)

        with col_f1:
            perfil_sel = st.selectbox("Perfil de cobertura", perfiles)

        with col_f2:
            servicio_sel = st.selectbox("Servicio solicitado", servicios)

        with col_f3:
            decision_sel = st.selectbox("Decisión", decisiones)

        consultar = st.form_submit_button("Consultar solicitudes")

    if consultar:
        with st.spinner("Consultando solicitudes..."):
            consultar_pagina_solicitudes(
                fecha_str=fecha_filtro_str,
                perfil=perfil_sel,
                servicio=servicio_sel,
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
            f"perfil={criterios.get('perfil', '-')}, "
            f"servicio={criterios.get('servicio', '-')}, "
            f"decisión={criterios.get('decision', '-')}, "
            f"página={pagina_actual + 1}, "
            f"registros por página={PAGE_SIZE}"
        )
        st.dataframe(st.session_state["df_filtrado"], use_container_width=True)

        col_prev, col_page, col_next = st.columns([1, 2, 1])

        with col_prev:
            anterior = st.button("Anterior", disabled=pagina_actual == 0)

        with col_page:
            st.markdown(
                f"<center>Página {pagina_actual + 1}</center>",
                unsafe_allow_html=True,
            )

        with col_next:
            siguiente = st.button("Siguiente", disabled=not tiene_siguiente)

        if anterior or siguiente:
            nueva_pagina = pagina_actual - 1 if anterior else pagina_actual + 1
            with st.spinner("Consultando solicitudes..."):
                consultar_pagina_solicitudes(
                    fecha_str=criterios["fecha"],
                    perfil=criterios["perfil"],
                    servicio=criterios["servicio"],
                    decision=criterios["decision"],
                    pagina=nueva_pagina,
                )
            st.rerun()
    else:
        st.info("Configura los filtros y presiona Consultar solicitudes.")


def render_cobertura_por_perfil() -> None:
    try:
        df = leer_cobertura_por_perfil_cached()
    except Exception as error:
        mostrar_error_carga("cobertura por perfil", error)
        return

    if df.empty:
        st.info("No hay datos de cobertura por perfil disponibles.")
        return

    df = preparar_numericas(
        df,
        [
            "total_ordenes",
            "ordenes_cubiertas",
            "ordenes_no_cubiertas",
            "monto_total_cubierto",
            "porcentaje_cobertura_aplicado",
        ],
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total órdenes", f"{int(df.get('total_ordenes', pd.Series()).sum()):,}")
    col2.metric("Cubiertas", f"{int(df.get('ordenes_cubiertas', pd.Series()).sum()):,}")
    col3.metric(
        "No cubiertas", f"{int(df.get('ordenes_no_cubiertas', pd.Series()).sum()):,}"
    )
    col4.metric("Monto cubierto", moneda(df.get("monto_total_cubierto", pd.Series()).sum()))

    chart = (
        alt.Chart(df)
        .mark_bar(cornerRadiusEnd=4)
        .encode(
            y=alt.Y("perfil_cobertura:N", sort="-x", title="Perfil"),
            x=alt.X("total_ordenes:Q", title="Total órdenes"),
            color=alt.Color(
                "porcentaje_cobertura_aplicado:Q",
                title="% cobertura",
                scale=alt.Scale(scheme="tealblues"),
            ),
            tooltip=[
                "perfil_cobertura:N",
                "total_ordenes:Q",
                "ordenes_cubiertas:Q",
                "ordenes_no_cubiertas:Q",
                alt.Tooltip("porcentaje_cobertura_aplicado:Q", format=".2f"),
                alt.Tooltip("monto_total_cubierto:Q", format=",.0f"),
            ],
        )
    )
    st.altair_chart(chart, use_container_width=True)
    st.dataframe(df, use_container_width=True)


def render_costos_por_entidad(particiones_validas: list[str]) -> None:
    fecha_dia = st.selectbox(
        "Día de costos",
        ["Todos"] + particiones_validas,
        key="fecha_costos_entidad",
    )

    try:
        df = leer_costos_por_entidad_cached(None if fecha_dia == "Todos" else fecha_dia)
    except Exception as error:
        mostrar_error_carga("costos por entidad", error)
        return

    if df.empty:
        st.info("No hay datos de costos por entidad disponibles.")
        return

    columnas_costo = [
        "costo_total_procedimientos",
        "costo_total_cubierto",
        "costo_no_cubierto",
    ]
    df = preparar_numericas(df, columnas_costo)
    columnas_presentes = [col for col in columnas_costo if col in df.columns]

    if not columnas_presentes or "entidad_emisora" not in df.columns:
        st.warning("La tabla de costos no contiene las columnas esperadas.")
        st.dataframe(df, use_container_width=True)
        return

    df_largo = df.melt(
        id_vars=["entidad_emisora"],
        value_vars=columnas_presentes,
        var_name="tipo_costo",
        value_name="valor",
    )
    chart = (
        alt.Chart(df_largo)
        .mark_bar(cornerRadiusEnd=4)
        .encode(
            y=alt.Y("entidad_emisora:N", sort="-x", title="Entidad"),
            x=alt.X("valor:Q", title="Costo"),
            color=alt.Color("tipo_costo:N", title="Tipo"),
            tooltip=["entidad_emisora:N", "tipo_costo:N", alt.Tooltip("valor:Q", format=",.0f")],
        )
    )
    st.altair_chart(chart, use_container_width=True)
    st.dataframe(df, use_container_width=True)


def render_total_ordenes_por_dia() -> None:
    try:
        df = leer_total_ordenes_por_dia_cached()
    except Exception as error:
        mostrar_error_carga("total de órdenes por día", error)
        return

    if df.empty:
        st.info("No hay datos de órdenes por día disponibles.")
        return

    columna_fecha = "fecha" if "fecha" in df.columns else "fecha_dia"
    columna_conteo = "conteo_ordenes" if "conteo_ordenes" in df.columns else "total_ordenes"

    if columna_fecha not in df.columns or columna_conteo not in df.columns:
        st.warning("La tabla de órdenes por día no contiene las columnas esperadas.")
        st.dataframe(df, use_container_width=True)
        return

    df = preparar_numericas(df, [columna_conteo])
    df[columna_fecha] = pd.to_datetime(df[columna_fecha], errors="coerce")
    df = df.dropna(subset=[columna_fecha]).sort_values(columna_fecha)

    chart = (
        alt.Chart(df)
        .mark_line(point=True)
        .encode(
            x=alt.X(f"{columna_fecha}:T", title="Fecha"),
            y=alt.Y(f"{columna_conteo}:Q", title="Órdenes"),
            tooltip=[alt.Tooltip(f"{columna_fecha}:T"), alt.Tooltip(f"{columna_conteo}:Q")],
        )
    )
    st.altair_chart(chart, use_container_width=True)
    st.dataframe(df, use_container_width=True)


def render_indicadores(particiones_validas: list[str]) -> None:
    if st.button("Cargar indicadores", key="cargar_indicadores"):
        st.session_state["indicadores_cargados"] = True

    if not st.session_state.get("indicadores_cargados", False):
        st.info("Carga los indicadores para leer los agregados Gold desde S3.")
        return

    tab_perfil, tab_costos, tab_dia = st.tabs(
        ["Cobertura por perfil", "Costos por entidad", "Órdenes por día"]
    )

    with tab_perfil:
        render_cobertura_por_perfil()

    with tab_costos:
        render_costos_por_entidad(particiones_validas)

    with tab_dia:
        render_total_ordenes_por_dia()


def render_trazabilidad() -> None:
    if st.button("Cargar trazabilidad", key="cargar_trazabilidad"):
        st.session_state["trazabilidad_cargada"] = True

    if not st.session_state.get("trazabilidad_cargada", False):
        st.info("Carga la trazabilidad para leer la tabla Gold desde S3.")
        return

    try:
        df = leer_trazabilidad_por_entidad_cached()
    except Exception as error:
        mostrar_error_carga("trazabilidad por entidad", error)
        return

    if df.empty:
        st.info("No hay datos de trazabilidad por entidad disponibles.")
        return

    df = preparar_numericas(
        df,
        [
            "total_ordenes",
            "ordenes_cubiertas",
            "ordenes_no_cubiertas",
            "porcentaje_cobertura_aplicado",
            "monto_total_cubierto",
        ],
    )
    st.dataframe(df, use_container_width=True)


particiones_validas = obtener_particiones_validas()

st.title("Sistema de consulta de cobertura médica")

tab_busqueda, tab_explorador, tab_indicadores, tab_trazabilidad = st.tabs(
    ["Buscar solicitud", "Explorar solicitudes", "Indicadores", "Trazabilidad"]
)

with tab_busqueda:
    render_busqueda()

with tab_explorador:
    render_explorador(particiones_validas)

with tab_indicadores:
    render_indicadores(particiones_validas)

with tab_trazabilidad:
    render_trazabilidad()
