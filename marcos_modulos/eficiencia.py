
"""
Eficiencia operacional - Gestao de Oficinas v3.

Indicadores complementares de agendamento e execucao.
Nao altera MCI, MD ou dados do Supabase.
"""

import pandas as pd


def calcular_indicadores(
    programadas,
    concluidas_programadas,
    improdutivas_programadas,
    canceladas_programadas,
    perdidas_programadas,
    concluidas_extras=0,
    improdutivas_extras=0,
):
    """
    Calcula indicadores a partir de contagens
    previamente conciliadas por OS e atendimento.
    """

    valores = [
        programadas,
        concluidas_programadas,
        improdutivas_programadas,
        canceladas_programadas,
        perdidas_programadas,
        concluidas_extras,
        improdutivas_extras,
    ]

    if any(pd.isna(v) or float(v) < 0 for v in valores):
        raise ValueError(
            "Os valores devem ser numeros nao negativos."
        )

    (
        programadas,
        concluidas_programadas,
        improdutivas_programadas,
        canceladas_programadas,
        perdidas_programadas,
        concluidas_extras,
        improdutivas_extras,
    ) = [float(v) for v in valores]

    def percentual(numerador, denominador):
        if denominador <= 0:
            return 0.0
        return round(numerador / denominador * 100, 2)

    desfechos_programados = (
        concluidas_programadas
        + improdutivas_programadas
        + canceladas_programadas
        + perdidas_programadas
    )

    total_concluidas = (
        concluidas_programadas + concluidas_extras
    )

    total_improdutivas = (
        improdutivas_programadas + improdutivas_extras
    )

    total_atendimentos = (
        total_concluidas + total_improdutivas
    )

    return {
        "programadas": programadas,
        "concluidas_programadas": concluidas_programadas,
        "improdutivas_programadas": improdutivas_programadas,
        "canceladas_programadas": canceladas_programadas,
        "perdidas_programadas": perdidas_programadas,
        "concluidas_extras": concluidas_extras,
        "improdutivas_extras": improdutivas_extras,
        "total_concluidas": total_concluidas,
        "total_atendimentos": total_atendimentos,
        "taxa_conclusao_programadas": percentual(
            concluidas_programadas, programadas
        ),
        "taxa_improdutividade_programadas": percentual(
            improdutivas_programadas, programadas
        ),
        "taxa_cancelamento": percentual(
            canceladas_programadas, programadas
        ),
        "taxa_perda": percentual(
            perdidas_programadas, programadas
        ),
        "taxa_conclusao_atendimentos": percentual(
            total_concluidas, total_atendimentos
        ),
        "participacao_extras": percentual(
            concluidas_extras + improdutivas_extras,
            total_atendimentos
        ),
        "diferenca_conciliacao": (
            programadas - desfechos_programados
        ),
    }


def semaforo(percentual, meta=85, atencao=70):
    """
    Classifica indicadores em que maior e melhor.
    Metas configuraveis e nao oficiais.
    """
    if pd.isna(percentual):
        return "Sem dados"

    if percentual >= meta:
        return "Dentro da meta"

    if percentual >= atencao:
        return "Atencao"

    return "Critico"


def nota_eficiencia(
    taxa_conclusao,
    taxa_cancelamento,
    taxa_perda,
    peso_conclusao=0.6,
    peso_cancelamento=0.2,
    peso_perda=0.2,
):
    """
    Nota exploratoria de 0 a 100.
    Nao equivale ao MCI ou ao MD.
    """

    soma_pesos = (
        peso_conclusao
        + peso_cancelamento
        + peso_perda
    )

    if soma_pesos <= 0:
        raise ValueError("Pesos invalidos.")

    conclusao = max(
        0, min(100, float(taxa_conclusao))
    )
    cancelamento = max(
        0, min(100, float(taxa_cancelamento))
    )
    perda = max(
        0, min(100, float(taxa_perda))
    )

    nota = (
        conclusao * peso_conclusao
        + (100 - cancelamento) * peso_cancelamento
        + (100 - perda) * peso_perda
    ) / soma_pesos

    return round(nota, 2)


def resumo_por_oficina(base):
    """
    Recebe dados ja classificados e agregados.
    Uma linha por oficina, com contagens operacionais.
    """

    colunas = [
        "oficina",
        "programadas",
        "concluidas_programadas",
        "improdutivas_programadas",
        "canceladas_programadas",
        "perdidas_programadas",
        "concluidas_extras",
        "improdutivas_extras",
    ]

    faltantes = [
        c for c in colunas
        if c not in base.columns
    ]

    if faltantes:
        raise ValueError(
            "Colunas ausentes: " + ", ".join(faltantes)
        )

    resultados = []

    for oficina, grupo in base.groupby("oficina"):
        totais = grupo[
            [c for c in colunas if c != "oficina"]
        ].sum()

        indicadores = calcular_indicadores(
            **totais.to_dict()
        )

        indicadores["oficina"] = oficina
        indicadores["semaforo"] = semaforo(
            indicadores["taxa_conclusao_programadas"]
        )

        resultados.append(indicadores)

    return pd.DataFrame(resultados)
