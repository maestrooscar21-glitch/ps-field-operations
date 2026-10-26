
"""
Auditoria operacional e financeira - Gestao de Oficinas.

Analise de inconsistencias e despesas extraordinarias.
Somente leitura. Nao modifica o banco de dados.
"""

import re
import unicodedata

import pandas as pd


def normalizar_texto(valor):
    if pd.isna(valor):
        return ""

    texto = unicodedata.normalize(
        "NFKD", str(valor)
    )
    texto = "".join(
        letra for letra in texto
        if not unicodedata.combining(letra)
    )
    return re.sub(r"\s+", " ", texto.lower()).strip()


def preparar_auditoria(base):
    """
    Recebe dados preparados pelo modulo financeiro.
    Preserva todos os lancamentos individuais.
    """

    if base is None or base.empty:
        return pd.DataFrame()

    dados = base.copy()

    textos = [
        "os", "oficina", "motivo",
        "arquivo_origem", "id_lancamento"
    ]

    for coluna in textos:
        if coluna not in dados.columns:
            dados[coluna] = ""

        dados[coluna] = (
            dados[coluna].fillna("").astype(str).str.strip()
        )

    valores = [
        "total", "valor_servico",
        "valor_km", "extras_informados",
        "diferenca_conciliacao"
    ]

    for coluna in valores:
        if coluna not in dados.columns:
            dados[coluna] = 0.0

        dados[coluna] = pd.to_numeric(
            dados[coluna], errors="coerce"
        ).fillna(0.0)

    dados["motivo_normalizado"] = (
        dados["motivo"].map(normalizar_texto)
    )

    return dados


def classificar_alertas(base, limite_extra=1000.0):
    """
    Identifica alertas para revisao humana.

    Os alertas nao representam, por si so,
    irregularidades comprovadas.
    """

    dados = preparar_auditoria(base)

    if dados.empty:
        return pd.DataFrame()

    registros = []

    for _, linha in dados.iterrows():
        alertas = []

        os = linha["os"]
        oficina = linha["oficina"]
        motivo = linha["motivo_normalizado"]
        total = linha["total"]
        extras = linha["extras_informados"]
        diferenca = linha["diferenca_conciliacao"]

        if not os or os.lower() == "nan":
            alertas.append("OS nao informada")

        if not oficina or oficina.lower() == "nan":
            alertas.append("Oficina nao informada")

        if extras > 0 and not motivo:
            alertas.append(
                "Despesa extra sem descricao"
            )

        if extras >= limite_extra:
            alertas.append(
                "Despesa extra acima do limite de revisao"
            )

        if abs(diferenca) > 0.05:
            alertas.append(
                "Diferenca de conciliacao financeira"
            )

        if total < 0:
            alertas.append(
                "Lancamento com valor negativo"
            )

        if any(
            termo in motivo
            for termo in (
                "hospedagem",
                "hotel",
                "pedagio",
                "deslocamento",
                "viagem",
                "adicional noturno",
                "fim de semana",
                "minimo garantido",
            )
        ):
            alertas.append(
                "Despesa sujeita a validacao contratual"
            )

        for alerta in alertas:
            registros.append({
                "id_lancamento": linha["id_lancamento"],
                "os": os,
                "oficina": oficina,
                "arquivo_origem": linha["arquivo_origem"],
                "tipo_alerta": alerta,
                "valor_total": total,
                "valor_extra": extras,
                "motivo_original": linha["motivo"],
                "situacao_analise": "Pendente de revisao",
            })

    return pd.DataFrame(
        registros,
        columns=[
            "id_lancamento",
            "os",
            "oficina",
            "arquivo_origem",
            "tipo_alerta",
            "valor_total",
            "valor_extra",
            "motivo_original",
            "situacao_analise",
        ]
    )


def resumo_alertas(alertas):
    """Conta alertas e lancamentos distintos."""

    if alertas is None or alertas.empty:
        return pd.DataFrame()

    return alertas.groupby(
        "tipo_alerta", dropna=False
    ).agg(
        quantidade_alertas=("id_lancamento", "count"),
        lancamentos_afetados=("id_lancamento", "nunique"),
    ).reset_index().sort_values(
        "quantidade_alertas", ascending=False
    )


def auditoria_por_oficina(alertas):
    if alertas is None or alertas.empty:
        return pd.DataFrame()

    return alertas.groupby(
        "oficina", dropna=False
    ).agg(
        quantidade_alertas=("tipo_alerta", "count"),
        lancamentos_afetados=("id_lancamento", "nunique"),
    ).reset_index().sort_values(
        "quantidade_alertas", ascending=False
    )


def itens_para_revisao(alertas, tipo=None):
    if alertas is None or alertas.empty:
        return pd.DataFrame()

    dados = alertas.copy()

    if tipo:
        dados = dados[
            dados["tipo_alerta"] == tipo
        ]

    return dados.reset_index(drop=True)
