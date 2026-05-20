import os
import re
import zlib
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
LOOKUP_BASE_PATH = os.getenv(
    "LOOKUP_BASE_PATH", "s3://coil-arquitectura/gold/solicitudes_lookup_por_id/"
)
COBERTURA_PERFIL_PATH = os.getenv(
    "COBERTURA_PERFIL_PATH", "s3://coil-arquitectura/gold/cobertura_por_perfil/"
)
COSTOS_ENTIDAD_PATH = os.getenv(
    "COSTOS_ENTIDAD_PATH", "s3://coil-arquitectura/gold/costos_por_entidad/"
)
TOTAL_ORDENES_DIA_PATH = os.getenv(
    "TOTAL_ORDENES_DIA_PATH", "s3://coil-arquitectura/gold/total_ordenes_por_dia/"
)
TRAZABILIDAD_ENTIDAD_PATH = os.getenv(
    "TRAZABILIDAD_ENTIDAD_PATH",
    "s3://coil-arquitectura/gold/trazabilidad/trazabilidad_por_entidad/",
)
TOTAL_BUCKETS = int(os.getenv("LOOKUP_TOTAL_BUCKETS", "100"))

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


def calcular_id_bucket(id_solicitud: str) -> int:
    id_solicitud = validar_id_solicitud(id_solicitud)
    checksum = zlib.crc32(id_solicitud.encode("utf-8")) & 0xFFFFFFFF
    return checksum % TOTAL_BUCKETS


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


def leer_parquet_s3(path: str, dataset: bool = False) -> pd.DataFrame:
    try:
        return wr.s3.read_parquet(path=path, dataset=dataset)
    except Exception as error:
        if error.__class__.__name__ in {"NoFilesFound", "NoFilesFoundError"}:
            return pd.DataFrame()
        raise


def buscar_solicitud_por_id_s3(id_solicitud: str) -> pd.DataFrame:
    id_solicitud = validar_id_solicitud(id_solicitud)
    id_bucket = calcular_id_bucket(id_solicitud)
    path = f"{LOOKUP_BASE_PATH.rstrip('/')}/id_bucket={id_bucket}/"
    df = leer_parquet_s3(path=path, dataset=True)

    if df.empty or "id_solicitud" not in df.columns:
        return pd.DataFrame()

    resultado = df[df["id_solicitud"].astype(str) == id_solicitud].copy()
    return resultado.head(1)


def leer_cobertura_por_perfil_s3() -> pd.DataFrame:
    return leer_parquet_s3(COBERTURA_PERFIL_PATH)


def leer_total_ordenes_por_dia_s3() -> pd.DataFrame:
    return leer_parquet_s3(TOTAL_ORDENES_DIA_PATH)


def leer_trazabilidad_por_entidad_s3() -> pd.DataFrame:
    return leer_parquet_s3(TRAZABILIDAD_ENTIDAD_PATH)


def leer_costos_por_entidad_s3(fecha_dia: str | None = None) -> pd.DataFrame:
    df = leer_parquet_s3(COSTOS_ENTIDAD_PATH, dataset=True)

    if fecha_dia and not df.empty and "fecha_dia" in df.columns:
        fechas = pd.to_datetime(df["fecha_dia"], errors="coerce").dt.strftime("%Y-%m-%d")
        df = df[fechas == fecha_dia].copy()

    return df


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
    perfil: str | None = None,
    servicio: str | None = None,
    decision: str | None = None,
    limite: int = 20,
    offset: int = 0,
) -> pd.DataFrame:
    fecha_dia = validar_particion(fecha_dia)
    limite = max(1, min(int(limite), 21))
    offset = max(0, int(offset))

    filtros = [filtro_fecha(fecha_dia)]

    if perfil and perfil != "Todos":
        perfil_limpio = escapar_sql(perfil)
        filtros.append(f"perfil_cobertura = '{perfil_limpio}'")

    if servicio and servicio != "Todos":
        servicio_limpio = escapar_sql(servicio)
        filtros.append(f"servicio_solicitado = '{servicio_limpio}'")

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
        perfil_cobertura,
        servicio_solicitado,
        decision_cobertura,
        porcentaje_cobertura,
        monto_cubierto
    FROM {ATHENA_DATABASE}.{GOLD_TABLE}
    WHERE {where_sql}
    {order_sql}
    OFFSET {offset}
    LIMIT {limite}
    """

    return ejecutar_athena(sql)


def obtener_opciones_filtros(fecha_dia: str) -> dict[str, list[str]]:
    fecha_dia = validar_particion(fecha_dia)

    sql = f"""
    SELECT 'perfil_cobertura' AS filtro, CAST(perfil_cobertura AS VARCHAR) AS valor
    FROM {ATHENA_DATABASE}.{GOLD_TABLE}
    WHERE {filtro_fecha(fecha_dia)}
      AND perfil_cobertura IS NOT NULL
    GROUP BY CAST(perfil_cobertura AS VARCHAR)

    UNION ALL

    SELECT 'servicio_solicitado' AS filtro, CAST(servicio_solicitado AS VARCHAR) AS valor
    FROM {ATHENA_DATABASE}.{GOLD_TABLE}
    WHERE {filtro_fecha(fecha_dia)}
      AND servicio_solicitado IS NOT NULL
    GROUP BY CAST(servicio_solicitado AS VARCHAR)

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
        "perfil_cobertura": [],
        "servicio_solicitado": [],
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
        "perfil_cobertura",
        "servicio_solicitado",
        "decision_cobertura",
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
