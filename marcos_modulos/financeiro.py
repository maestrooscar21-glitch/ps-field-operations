
"""
Modulo financeiro - Gestao de Oficinas v3.
Preparacao e analise dos consolidados financeiros.

Somente processamento em memoria.
Nao grava no Supabase.
"""

import hashlib
import json
import re
import unicodedata

import pandas as pd


COLUNAS = {
    "Protocolo": "os",
    "OS": "os",
    "Oficina": "oficina",
    "Instalador": "tecnico",
    "Tipo": "tipo",
    "Tipo_Servico": "tipo",
    "Tipo Servico": "tipo",
    "Data Execução": "data",
    "Data_Execucao": "data",
    "Execução Serviço": "data",
    "Placa": "placa",
    "Valor_Servico": "valor_servico",
    "Serviço Oficina": "valor_servico",
    "R$ Serviço": "valor_servico",
    "Valor_KM": "valor_km",
    "Valor KM": "valor_km",
    "R$ KM": "valor_km",
    "Valor_Despesas": "despesas",
    "R$ Despesas": "despesas",
    "Pedágio": "pedagio",
    "Hotel": "hotel",
    "Materiais": "materiais",
    "Outras": "outras",
    "Valor_Total": "total",
    "Total a Pagar": "total",
    "R$ Total": "total",
    "Motivo": "motivo",
    "Despesas de Viagem": "motivo",
    "Arquivo_Origem": "arquivo_origem",
}

VALORES = [
    "valor_servico", "valor_km", "despesas",
    "pedagio", "hotel", "materiais",
    "outras", "total"
]


def normalizar_nome(valor):
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


def converter_valor(valor):
    if pd.isna(valor):
        return 0.0

    if isinstance(valor, (int, float)):
        return float(valor)

    texto = str(valor).strip()
    texto = texto.replace("R$", "").replace(" ", "")

    if not texto:
        return 0.0

    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")

    try:
        return float(texto)
    except ValueError:
        return 0.0


def preparar(base, nome_arquivo=""):
    """
    Normaliza planilha financeira sem eliminar
    lancamentos diferentes da mesma OS.
    """

    if base is None or base.empty:
        return pd.DataFrame()

    bruto = base.copy().reset_index(drop=True)
    dados = pd.DataFrame(index=bruto.index)

    for origem, destino in COLUNAS.items():
        if origem not in bruto.columns:
            continue

        if destino not in dados.columns:
            dados[destino] = bruto[origem]
        else:
            dados[destino] = dados[destino].combine_first(
                bruto[origem]
            )

    for coluna in (
        "os", "oficina", "tecnico", "tipo",
        "placa", "motivo", "arquivo_origem"
    ):
        if coluna not in dados.columns:
            dados[coluna] = ""

        dados[coluna] = dados[coluna].fillna("").astype(str)

    dados["os"] = (
        dados["os"].str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )

    if "data" not in dados.columns:
        dados["data"] = pd.NaT

    dados["data"] = pd.to_datetime(
        dados["data"],
        dayfirst=True,
        errors="coerce"
    )

    for coluna in VALORES:
        if coluna not in dados.columns:
            dados[coluna] = 0.0

        dados[coluna] = dados[coluna].map(converter_valor)

    dados["arquivo_origem"] = (
        dados["arquivo_origem"]
        .replace("", pd.NA)
        .fillna(nome_arquivo)
    )

    dados["linha_origem"] = bruto.index + 2

    dados["competencia"] = (
        dados["data"].dt.strftime("%Y-%m")
    )

    dados["despesas_identificadas"] = dados[
        ["pedagio", "hotel", "materiais", "outras"]
    ].sum(axis=1)

    dados["extras_informados"] = dados["despesas"]

    dados["diferenca_conciliacao"] = (
        dados["total"]
        - dados["valor_servico"]
        - dados["valor_km"]
        - dados["extras_informados"]
    )

    def gerar_hash(linha):
        campos = {
            "arquivo": linha["arquivo_origem"],
            "linha": int(linha["linha_origem"]),
            "os": linha["os"],
            "oficina": linha["oficina"],
            "total": linha["total"],
        }
        texto = json.dumps(
            campos, sort_keys=True, ensure_ascii=False
        )
        return hashlib.sha256(
            texto.encode("utf-8")
        ).hexdigest()

    dados["id_lancamento"] = dados.apply(
        gerar_hash, axis=1
    )

    return dados.reset_index(drop=True)


def resumo_por_oficina(dados):
    if dados is None or dados.empty:
        return pd.DataFrame()

    resumo = dados.groupby(
        "oficina", dropna=False
    ).agg(
        lancamentos=("id_lancamento", "count"),
        os_distintas=("os", "nunique"),
        total_pago=("total", "sum"),
        servicos=("valor_servico", "sum"),
        deslocamento=("valor_km", "sum"),
        despesas=("extras_informados", "sum"),
    ).reset_index()

    resumo["custo_por_os"] = (
        resumo["total_pago"]
        / resumo["os_distintas"].replace(0, float("nan"))
    )

    return resumo.sort_values(
        "total_pago", ascending=False
    )


def resumo_mensal(dados):
    if dados is None or dados.empty:
        return pd.DataFrame()

    return dados.groupby(
        ["competencia", "oficina"],
        dropna=False
    ).agg(
        lancamentos=("id_lancamento", "count"),
        os_distintas=("os", "nunique"),
        total_pago=("total", "sum"),
        servicos=("valor_servico", "sum"),
        deslocamento=("valor_km", "sum"),
        despesas=("extras_informados", "sum"),
    ).reset_index()


def localizar_alertas(dados, tolerancia=0.05):
    if dados is None or dados.empty:
        return pd.DataFrame()

    alertas = dados.copy()

    alertas["alerta_sem_os"] = (
        alertas["os"].str.strip().eq("")
    )

    alertas["alerta_sem_oficina"] = (
        alertas["oficina"].str.strip().eq("")
    )

    alertas["alerta_conciliacao"] = (
        alertas["diferenca_conciliacao"].abs()
        > tolerancia
    )

    return alertas[
        alertas["alerta_sem_os"]
        | alertas["alerta_sem_oficina"]
        | alertas["alerta_conciliacao"]
    ].copy()
