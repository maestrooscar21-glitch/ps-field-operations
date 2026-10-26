
"""
Capacidade operacional - Gestao de Oficinas v3.

Analise por oficina, tecnico e dia.
Somente leitura e calculos em memoria.
Nao altera o Supabase ou os indicadores MCI/MD.
"""

import pandas as pd


def preparar_atividades(base):
    """Normaliza atividades operacionais."""
    if base is None or base.empty:
        return pd.DataFrame()

    df = base.copy()

    if "dados" in df.columns:
        extras = pd.json_normalize(
            df["dados"].apply(
                lambda x: x if isinstance(x, dict) else {}
            )
        )
        for coluna in extras.columns:
            if coluna not in df.columns:
                df[coluna] = extras[coluna].values

    aliases = {
        "data_operacional": ["data_operacional", "Data"],
        "oficina": ["oficina", "Oficina"],
        "tecnico": ["tecnico", "Técnico", "recurso"],
        "os": ["os", "OS", "Protocolo"],
        "status": ["status_atividade", "Situação", "Status"],
    }

    for destino, candidatos in aliases.items():
        if destino not in df.columns:
            for origem in candidatos:
                if origem in df.columns:
                    df[destino] = df[origem]
                    break

    for coluna in ("oficina", "tecnico", "os", "status"):
        if coluna not in df.columns:
            df[coluna] = ""
        df[coluna] = df[coluna].fillna("").astype(str).str.strip()

    if "data_operacional" not in df.columns:
        df["data_operacional"] = pd.NaT

    df["data_operacional"] = pd.to_datetime(
        df["data_operacional"], errors="coerce"
    ).dt.date

    df = df.drop_duplicates(
        ["data_operacional", "oficina", "os"],
        keep="last"
    )

    return df


def tecnicos_por_oficina(atividades):
    """Tecnicos distintos observados na base."""
    df = preparar_atividades(atividades)

    if df.empty:
        return pd.DataFrame(
            columns=["oficina", "tecnicos_observados"]
        )

    df = df[
        df["tecnico"].ne("")
        & df["tecnico"].str.lower().ne("nan")
    ]

    return df.groupby("oficina").agg(
        tecnicos_observados=("tecnico", "nunique")
    ).reset_index()


def diario(atividades, capacidade_por_tecnico=3):
    """
    Estima a capacidade diaria com base nos tecnicos
    observados, nao no quadro oficial cadastrado.
    """
    if capacidade_por_tecnico <= 0:
        raise ValueError(
            "Capacidade por tecnico deve ser positiva."
        )

    df = preparar_atividades(atividades)

    if df.empty:
        return pd.DataFrame()

    df = df[
        df["data_operacional"].notna()
        & df["os"].ne("")
    ].copy()

    if df.empty:
        return pd.DataFrame()

    resultado = df.groupby(
        ["data_operacional", "oficina"],
        dropna=False
    ).agg(
        os_distintas=("os", "nunique"),
        tecnicos_observados=(
            "tecnico",
            lambda s: s[
                s.ne("") & s.str.lower().ne("nan")
            ].nunique()
        ),
    ).reset_index()

    resultado["capacidade_estimada"] = (
        resultado["tecnicos_observados"]
        * capacidade_por_tecnico
    )

    resultado["ocupacao_percentual"] = (
        resultado["os_distintas"]
        / resultado["capacidade_estimada"].replace(
            0, float("nan")
        )
        * 100
    )

    return resultado


def status_ocupacao(percentual):
    """Semaforo indicativo de ocupacao."""
    if pd.isna(percentual):
        return "Sem capacidade informada"

    if percentual < 50:
        return "Baixa ocupacao"

    if percentual <= 85:
        return "Ocupacao moderada"

    if percentual <= 100:
        return "Alta ocupacao"

    return "Acima da capacidade estimada"


def resumo_capacidade(atividades, capacidade_por_tecnico=3):
    dados = diario(
        atividades,
        capacidade_por_tecnico=capacidade_por_tecnico
    )

    if dados.empty:
        return dados

    dados["situacao_capacidade"] = (
        dados["ocupacao_percentual"].map(status_ocupacao)
    )

    return dados
