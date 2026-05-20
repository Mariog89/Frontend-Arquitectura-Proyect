import os
import re
from functools import lru_cache

import awswrangler as wr
import pandas as pd

AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
ATHENA_DATABASE = os.getenv("ATHENA_DATABASE", "coil_gold")
ATHENA_WORKGROUP = os.getenv("ATHENA_WORKGROUP", "primary")
ATHENA_OUTPUT = os.getenv("ATHENA_OUTPUT")
GOLD_TABLE = os.getenv("GOLD_TABLE", "ordenes_clasificadas")
AVAILABLE_PARTITIONS = os.getenv(
    "AVAILABLE_PARTITIONS", "2026-05-04,2026-05-05,2026-05-06"
)
EXPLORER_ORDER_BY_ENABLED = os.getenv("EXPLORER_ORDER_BY_ENABLED", "true").lower() in {
    "1",
    "true",
    "yes",
}

# Cambia esto a "date" si Athena muestra fecha_dia como date.
FECHA_DIA_TYPE = os.getenv("FECHA_DIA_TYPE", "date")


@lru_cache(maxsize=1)
def obtener_particiones_validas() -> list[str]:
    particiones = [
        particion.strip()
        for particion in AVAILABLE_PARTITIONS.split(",")
        if particion.strip()
    ]

    if not particiones:
        raise RuntimeError("Falta configurar AVAILABLE_PARTITIONS.")

    for particion in particiones:
        validar_formato_fecha(particion)

    return particiones


def validar_id_solicitud(id_solicitud: str) -> str:
    id_solicitud = id_solicitud.strip()

    if not re.match(r"^[A-Za-z0-9_\-]+$", id_solicitud):
        raise ValueError("ID de solicitud inválido.")

    return id_solicitud


def validar_formato_fecha(fecha_dia: str) -> str:
    fecha_dia = fecha_dia.strip()

    if not re.match(r"^\d{4}-\d{2}-\d{2}$", fecha_dia):
        raise ValueError("La fecha debe tener formato YYYY-MM-DD.")

    return fecha_dia


def validar_particion(fecha_dia: str) -> str:
    fecha_dia = validar_formato_fecha(fecha_dia)
    particiones_validas = obtener_particiones_validas()

    if fecha_dia not in particiones_validas:
        raise ValueError(
            "La fecha no existe como partición disponible. "
            f"Usa una de estas fechas: {', '.join(particiones_validas)}."
        )

    return fecha_dia


def validar_fecha_dia(fecha_dia: str) -> str:
    return validar_particion(fecha_dia)


def filtro_fecha(fecha_dia: str) -> str:
    if FECHA_DIA_TYPE == "date":
        return f"fecha_dia = DATE '{fecha_dia}'"

    return f"fecha_dia = '{fecha_dia}'"


def filtro_fechas(fecha_dias: list[str]) -> str:
    if not fecha_dias:
        raise ValueError("Debes indicar al menos una partición.")

    fechas_validadas = [validar_particion(fecha_dia) for fecha_dia in fecha_dias]

    if FECHA_DIA_TYPE == "date":
        fechas_sql = ", ".join(f"DATE '{fecha_dia}'" for fecha_dia in fechas_validadas)
    else:
        fechas_sql = ", ".join(f"'{fecha_dia}'" for fecha_dia in fechas_validadas)

    return f"fecha_dia IN ({fechas_sql})"


def escapar_sql(valor: str) -> str:
    return valor.replace("'", "''")


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


def buscar_solicitud_por_id(
    id_solicitud: str,
    fecha_dia: str | None = None,
    fecha_dias: list[str] | None = None,
) -> pd.DataFrame:
    id_solicitud = validar_id_solicitud(id_solicitud)
    filtro_particion = (
        filtro_fechas(fecha_dias)
        if fecha_dias is not None
        else filtro_fecha(validar_fecha_dia(fecha_dia or ""))
    )

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
    WHERE {filtro_particion}
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
    fecha_dia = validar_particion(fecha_dia)
    limite = max(5, min(int(limite), 100))

    filtros = [filtro_fecha(fecha_dia)]

    if entidad and entidad != "Todas":
        entidad_limpia = escapar_sql(entidad)
        filtros.append(f"entidad_emisora = '{entidad_limpia}'")

    if medio and medio != "Todos":
        medio_limpio = escapar_sql(medio)
        filtros.append(f"medio_emisor = '{medio_limpio}'")

    if decision and decision != "Todas":
        decision_limpia = escapar_sql(decision)
        filtros.append(f"decision_cobertura = '{decision_limpia}'")

    where_sql = " AND ".join(filtros)
    order_sql = "ORDER BY fecha_solicitud DESC" if EXPLORER_ORDER_BY_ENABLED else ""

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
    {order_sql}
    LIMIT {limite}
    """

    return ejecutar_athena(sql)


def obtener_opciones_filtros(fecha_dia: str) -> dict[str, list[str]]:
    fecha_dia = validar_particion(fecha_dia)

    sql = f"""
    SELECT 'entidad_emisora' AS filtro, CAST(entidad_emisora AS VARCHAR) AS valor
    FROM {ATHENA_DATABASE}.{GOLD_TABLE}
    WHERE {filtro_fecha(fecha_dia)}
      AND entidad_emisora IS NOT NULL
    GROUP BY CAST(entidad_emisora AS VARCHAR)

    UNION ALL

    SELECT 'medio_emisor' AS filtro, CAST(medio_emisor AS VARCHAR) AS valor
    FROM {ATHENA_DATABASE}.{GOLD_TABLE}
    WHERE {filtro_fecha(fecha_dia)}
      AND medio_emisor IS NOT NULL
    GROUP BY CAST(medio_emisor AS VARCHAR)

    UNION ALL

    SELECT 'decision_cobertura' AS filtro, CAST(decision_cobertura AS VARCHAR) AS valor
    FROM {ATHENA_DATABASE}.{GOLD_TABLE}
    WHERE {filtro_fecha(fecha_dia)}
      AND decision_cobertura IS NOT NULL
    GROUP BY CAST(decision_cobertura AS VARCHAR)

    ORDER BY filtro, valor
    """

    df = ejecutar_athena(sql)
    opciones = {
        "entidad_emisora": [],
        "medio_emisor": [],
        "decision_cobertura": [],
    }

    if df.empty:
        return opciones

    for filtro, valores in df.groupby("filtro")["valor"]:
        opciones[filtro] = valores.dropna().astype(str).tolist()

    return opciones


def obtener_valores_filtro(fecha_dia: str, columna: str) -> list[str]:
    fecha_dia = validar_particion(fecha_dia)

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
