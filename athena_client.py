import os
import re

import awswrangler as wr
import pandas as pd

AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
ATHENA_DATABASE = os.getenv("ATHENA_DATABASE", "coil_gold")
ATHENA_WORKGROUP = os.getenv("ATHENA_WORKGROUP", "primary")
ATHENA_OUTPUT = os.getenv("ATHENA_OUTPUT")
GOLD_TABLE = os.getenv("GOLD_TABLE", "ordenes_clasificadas")

# Cambia esto a "date" si Athena muestra fecha_dia como date.
FECHA_DIA_TYPE = os.getenv("FECHA_DIA_TYPE", "date")


def validar_id_solicitud(id_solicitud: str) -> str:
    id_solicitud = id_solicitud.strip()

    if not re.match(r"^[A-Za-z0-9_\-]+$", id_solicitud):
        raise ValueError("ID de solicitud inválido.")

    return id_solicitud


def validar_fecha_dia(fecha_dia: str) -> str:
    fecha_dia = fecha_dia.strip()

    if not re.match(r"^\d{4}-\d{2}-\d{2}$", fecha_dia):
        raise ValueError("La fecha debe tener formato YYYY-MM-DD.")

    return fecha_dia


def filtro_fecha(fecha_dia: str) -> str:
    if FECHA_DIA_TYPE == "date":
        return f"fecha_dia = DATE '{fecha_dia}'"

    return f"fecha_dia = '{fecha_dia}'"


def ejecutar_athena(sql: str) -> pd.DataFrame:
    if not ATHENA_OUTPUT:
        raise RuntimeError("Falta configurar ATHENA_OUTPUT.")

    return wr.athena.read_sql_query(
        sql=sql,
        database=ATHENA_DATABASE,
        workgroup=ATHENA_WORKGROUP,
        s3_output=ATHENA_OUTPUT,
        ctas_approach=False,
    )


def buscar_solicitud_por_id(id_solicitud: str, fecha_dia: str) -> pd.DataFrame:
    id_solicitud = validar_id_solicitud(id_solicitud)
    fecha_dia = validar_fecha_dia(fecha_dia)

    sql = f"""
    SELECT
        id_solicitud,
        fecha_solicitud,
        medio_emisor,
        valor_procedimiento,
        entidad_emisora,
        paciente_nombre,
        paciente_dno,
        paciente_seguro_social,
        edad,
        perfil_cobertura,
        servicio_solicitado,
        medicacion,
        decision_cobertura,
        porcentaje_cobertura,
        monto_cubierto,
        razon_decision,
        timestamp_procesamiento,
        fecha_dia
    FROM {ATHENA_DATABASE}.{GOLD_TABLE}
    WHERE {filtro_fecha(fecha_dia)}
      AND id_solicitud = '{id_solicitud}'
    LIMIT 1
    """

    return ejecutar_athena(sql)


def explorar_solicitudes(
    fecha_dia: str,
    entidad: str | None = None,
    medio: str | None = None,
    decision: str | None = None,
    limite: int = 20,
) -> pd.DataFrame:
    fecha_dia = validar_fecha_dia(fecha_dia)
    limite = max(5, min(int(limite), 100))

    filtros = [filtro_fecha(fecha_dia)]

    if entidad and entidad != "Todas":
        entidad_limpia = entidad.replace("'", "''")
        filtros.append(f"entidad_emisora = '{entidad_limpia}'")

    if medio and medio != "Todos":
        medio_limpio = medio.replace("'", "''")
        filtros.append(f"medio_emisor = '{medio_limpio}'")

    if decision and decision != "Todas":
        decision_limpia = decision.replace("'", "''")
        filtros.append(f"decision_cobertura = '{decision_limpia}'")

    where_sql = " AND ".join(filtros)

    sql = f"""
    SELECT
        id_solicitud,
        fecha_solicitud,
        medio_emisor,
        valor_procedimiento,
        entidad_emisora,
        servicio_solicitado,
        decision_cobertura,
        porcentaje_cobertura,
        monto_cubierto
    FROM {ATHENA_DATABASE}.{GOLD_TABLE}
    WHERE {where_sql}
    ORDER BY fecha_solicitud DESC
    LIMIT {limite}
    """

    return ejecutar_athena(sql)


def obtener_valores_filtro(fecha_dia: str, columna: str) -> list[str]:
    fecha_dia = validar_fecha_dia(fecha_dia)

    columnas_permitidas = {
        "entidad_emisora",
        "medio_emisor",
        "decision_cobertura",
        "perfil_cobertura",
    }

    if columna not in columnas_permitidas:
        raise ValueError("Columna de filtro no permitida.")

    sql = f"""
    SELECT DISTINCT {columna}
    FROM {ATHENA_DATABASE}.{GOLD_TABLE}
    WHERE {filtro_fecha(fecha_dia)}
      AND {columna} IS NOT NULL
    ORDER BY {columna}
    """

    df = ejecutar_athena(sql)
    return df[columna].dropna().tolist()
