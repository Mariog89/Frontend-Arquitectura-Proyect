import streamlit as st

from athena_client import (
    buscar_solicitud_por_id,
    explorar_solicitudes,
    obtener_valores_filtro,
)

st.title("Sistema de consulta de cobertura médica")

st.markdown("### 🔎 Buscar solicitud por ID")

col_id, col_fecha = st.columns(2)

with col_id:
    id_ingresado = st.text_input("ID de solicitud", placeholder="Ej: CHV-0447260")

with col_fecha:
    fecha_dia = st.date_input("Día de partición")

if st.button("Buscar solicitud"):
    if not id_ingresado:
        st.warning("Ingresa un ID de solicitud.")
    else:
        fecha_str = fecha_dia.strftime("%Y-%m-%d")

        with st.spinner("Consultando datos Gold en Athena..."):
            fila = buscar_solicitud_por_id(id_ingresado, fecha_str)

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

fecha_filtro = st.date_input("Día a explorar", key="fecha_explorador")
fecha_filtro_str = fecha_filtro.strftime("%Y-%m-%d")


@st.cache_data(ttl=300)
def cargar_entidades(fecha_str):
    return ["Todas"] + obtener_valores_filtro(fecha_str, "entidad_emisora")


@st.cache_data(ttl=300)
def cargar_medios(fecha_str):
    return ["Todos"] + obtener_valores_filtro(fecha_str, "medio_emisor")


@st.cache_data(ttl=300)
def cargar_decisiones(fecha_str):
    return ["Todas"] + obtener_valores_filtro(fecha_str, "decision_cobertura")


col_f1, col_f2, col_f3, col_f4 = st.columns(4)

with col_f1:
    entidad_sel = st.selectbox("Entidad emisora", cargar_entidades(fecha_filtro_str))

with col_f2:
    medio_sel = st.selectbox("Medio emisor", cargar_medios(fecha_filtro_str))

with col_f3:
    decision_sel = st.selectbox("Decisión", cargar_decisiones(fecha_filtro_str))

with col_f4:
    n_filas = st.slider("Registros", 5, 100, 20)

with st.spinner("Consultando solicitudes..."):
    df_filtrado = explorar_solicitudes(
        fecha_dia=fecha_filtro_str,
        entidad=entidad_sel,
        medio=medio_sel,
        decision=decision_sel,
        limite=n_filas,
    )

st.dataframe(df_filtrado, use_container_width=True)
