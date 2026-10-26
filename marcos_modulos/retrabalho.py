
"""
Modulo de retrabalho - Gestao de Oficinas v3.

Pre-triagem de reincidencias de OS.
Nao grava dados no Supabase.
Nao altera MCI ou MD.
"""

import re
import unicodedata
import pandas as pd


JANELA_PADRAO = 90

COLUNAS_OBRIGATORIAS = [
    "Caso", "Protocolo", "Visita",
    "Placa", "Execução", "Tipo"
]


def normalizar(valor):
    if pd.isna(valor):
        return ""
    texto = unicodedata.normalize(
        "NFKD", str(valor)
    )
    texto = "".join(
        c for c in texto
        if not unicodedata.combining(c)
    )
    return re.sub(
        r"\s+", " ", texto.lower()
    ).strip()


def familia_servico(valor):
    texto = normalizar(valor)

    if "reinstal" in texto:
        return "reinstalacao"
    if "instal" in texto:
        return "instalacao"
    if "manut" in texto:
        return "manutencao"
    if "renov" in texto:
        return "renovacao"
    if "retir" in texto or "desinstal" in texto:
        return "retirada"
    if "upgrade" in texto or "atualiz" in texto:
        return "upgrade"
    if "autoteste" in texto or "auto teste" in texto:
        return "autoteste"

    return "outros"


def classificar_par(
    tipo_anterior,
    tipo_posterior,
    dias,
    cancelado_cliente=False,
    janela_dias=JANELA_PADRAO,
):
    """
    Retorna classificacao preliminar e motivo.
    Nao confirma automaticamente retrabalho.
    """

    primeiro = familia_servico(tipo_anterior)
    segundo = familia_servico(tipo_posterior)

    if cancelado_cliente:
        return "Descartado", "Cancelamento pelo cliente"

    if pd.isna(dias):
        return "Pendente", "Datas insuficientes"

    if dias < 0:
        return "Pendente", "Datas inconsistentes"

    if dias > janela_dias:
        return "Fora da janela", "Intervalo superior ao limite"

    if primeiro == segundo:
        return "Descartado", "Tipos de servico identicos"

    if segundo == "retirada":
        return "Descartado", "Retirada posterior"

    if primeiro == "manutencao" and segundo in (
        "upgrade", "renovacao", "instalacao"
    ):
        return "Descartado", "Mudanca de servico"

    if primeiro == "instalacao" and segundo == "manutencao":
        return (
            "Revisao manual",
            "Regra instalacao para manutencao pendente"
        )

    if primeiro == "retirada":
        return (
            "Revisao manual",
            "Verificar ciclo posterior a retirada"
        )

    return (
        "Possivel retrabalho",
        "Reincidencia dentro da janela"
    )


def montar_casos(base, janela_dias=JANELA_PADRAO):
    """
    Monta pares a partir da planilha de retrabalho.
    Espera primeira visita e retorno por Caso.
    """

    faltantes = [
        coluna for coluna in COLUNAS_OBRIGATORIAS
        if coluna not in base.columns
    ]

    if faltantes:
        raise ValueError(
            "Colunas ausentes: " + ", ".join(faltantes)
        )

    df = base.copy()

    df["Protocolo"] = (
        df["Protocolo"]
        .astype("string")
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )

    df["Execução"] = pd.to_datetime(
        df["Execução"],
        dayfirst=True,
        errors="coerce"
    )

    df["_visita"] = df["Visita"].map(normalizar)

    primeiras = (
        df[~df["_visita"].str.contains("retorno", na=False)]
        .drop_duplicates("Caso")
        .set_index("Caso")
    )

    retornos = (
        df[df["_visita"].str.contains("retorno", na=False)]
        .drop_duplicates("Caso")
        .set_index("Caso")
    )

    casos = []

    for identificador, retorno in retornos.iterrows():
        if identificador not in primeiras.index:
            continue

        anterior = primeiras.loc[identificador]

        os1 = str(anterior["Protocolo"])
        os2 = str(retorno["Protocolo"])

        if os1 == os2:
            continue

        data1 = anterior["Execução"]
        data2 = retorno["Execução"]

        dias = (
            (data2 - data1).days
            if pd.notna(data1) and pd.notna(data2)
            else None
        )

        situacao = normalizar(
            retorno.get("Situação", "")
        )
        explicacao = normalizar(
            retorno.get("Explicação", "")
        )

        cancelado = (
            "cancelad" in situacao
            and "cliente" in (situacao + " " + explicacao)
        )

        classificacao, motivo = classificar_par(
            anterior["Tipo"],
            retorno["Tipo"],
            dias,
            cancelado_cliente=cancelado,
            janela_dias=janela_dias,
        )

        casos.append({
            "caso": str(identificador),
            "placa": str(retorno["Placa"]),
            "os_anterior": os1,
            "os_posterior": os2,
            "data_anterior": data1,
            "data_posterior": data2,
            "tipo_anterior": anterior["Tipo"],
            "tipo_posterior": retorno["Tipo"],
            "oficina": retorno.get("Oficina", ""),
            "cliente": retorno.get("Cliente", ""),
            "dias": dias,
            "classificacao": classificacao,
            "motivo": motivo,
        })

    resultado = pd.DataFrame(casos)

    if not resultado.empty:
        resultado = resultado.drop_duplicates(
            ["os_anterior", "os_posterior"]
        )

    return resultado
