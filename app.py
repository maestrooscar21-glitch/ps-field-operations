import io
import re
import unicodedata
from datetime import date, datetime
from typing import Any
from urllib.parse import quote

import pandas as pd
import plotly.express as px
import streamlit as st
from supabase import Client, create_client


# =========================================================
# CONFIGURAÇÃO
# =========================================================

st.set_page_config(
    page_title="Operações de Campo PS",
    page_icon="🚛",
    layout="wide",
)

CONSULTORES = [
    "Não definido",
    "Oscar Barbosa",
    "Paulo Castro",
    "Fábio Silva",
    "Fábio Silva*",
    "Marcos Bispo",
    "Roberto Rugel",
    "Gleci Nunes",
]

MAPA_CONSULTORES_UF = {
    "AL": "Oscar Barbosa",
    "BA": "Oscar Barbosa",
    "CE": "Oscar Barbosa",
    "MA": "Oscar Barbosa",
    "PB": "Oscar Barbosa",
    "PE": "Oscar Barbosa",
    "PI": "Oscar Barbosa",
    "RN": "Oscar Barbosa",
    "SE": "Oscar Barbosa",
    "SP": "Paulo Castro",
    "RJ": "Paulo Castro",
    "ES": "Paulo Castro",
    "MG": "Fábio Silva",
    "AC": "Fábio Silva*",
    "AM": "Fábio Silva*",
    "AP": "Fábio Silva*",
    "PA": "Fábio Silva*",
    "RO": "Fábio Silva*",
    "RR": "Fábio Silva*",
    "TO": "Fábio Silva*",
    "PR": "Roberto Rugel",
    "RS": "Marcos Bispo",
    "SC": "Marcos Bispo",
    "DF": "Gleci Nunes",
    "GO": "Gleci Nunes",
    "MT": "Gleci Nunes",
    "MS": "Gleci Nunes",
}

REGIOES_CONSULTORES = {
    "Oscar Barbosa": "Nordeste",
    "Paulo Castro": "Sudeste",
    "Fábio Silva": "Minas Gerais",
    "Fábio Silva*": "Norte",
    "Marcos Bispo": "Rio Grande do Sul / Santa Catarina",
    "Roberto Rugel": "Paraná",
    "Gleci Nunes": "Centro-Oeste",
    "Não definido": "Não definida",
}

TABELA_POR_TIPO = {
    "planejado": "atividades_planejadas",
    "resultado": "atividades_resultado",
}


# =========================================================
# SUPABASE
# =========================================================

def obter_supabase() -> tuple[Client | None, str | None]:
    """Cria a conexão e devolve também uma mensagem de erro legível."""
    try:
        url = str(st.secrets.get("SUPABASE_URL", "")).strip()
        chave = str(
            st.secrets.get(
                "SUPABASE_SERVICE_KEY",
                st.secrets.get("SUPABASE_KEY", ""),
            )
        ).strip()

        url = url.replace("/rest/v1/", "").replace("/rest/v1", "").rstrip("/")

        if not url or not chave:
            return None, (
                "Configure SUPABASE_URL e SUPABASE_SERVICE_KEY "
                "nos Secrets do Streamlit."
            )

        cliente = create_client(url, chave)

        # Teste simples da conexão.
        cliente.table("bases_importadas").select("id").limit(1).execute()
        return cliente, None

    except Exception as erro:
        return None, f"Falha na conexão com o Supabase: {erro}"


SUPABASE, ERRO_SUPABASE = obter_supabase()


def exigir_supabase() -> Client:
    if SUPABASE is None:
        st.error(ERRO_SUPABASE or "Supabase não conectado.")
        st.stop()

    return SUPABASE


def buscar_todos(
    tabela: str,
    colunas: str = "*",
    filtros: dict[str, Any] | None = None,
    ordem: str | None = None,
    desc: bool = False,
    tamanho_pagina: int = 1000,
) -> list[dict]:
    """Busca todos os registros, inclusive quando houver mais de 1.000 linhas."""
    cliente = exigir_supabase()
    registros: list[dict] = []
    inicio = 0

    while True:
        consulta = cliente.table(tabela).select(colunas)

        for coluna, valor in (filtros or {}).items():
            consulta = consulta.eq(coluna, valor)

        if ordem:
            consulta = consulta.order(ordem, desc=desc)

        resposta = consulta.range(
            inicio,
            inicio + tamanho_pagina - 1,
        ).execute()

        lote = resposta.data or []
        registros.extend(lote)

        if len(lote) < tamanho_pagina:
            break

        inicio += tamanho_pagina

    return registros


def inserir_em_lotes(
    tabela: str,
    registros: list[dict],
    tamanho_lote: int = 300,
) -> None:
    cliente = exigir_supabase()

    for inicio in range(0, len(registros), tamanho_lote):
        lote = registros[inicio : inicio + tamanho_lote]
        cliente.table(tabela).insert(lote).execute()


# =========================================================
# LIMPEZA E LEITURA
# =========================================================

def texto_limpo(valor) -> str:
    if valor is None:
        return ""

    try:
        if pd.isna(valor):
            return ""
    except (TypeError, ValueError):
        pass

    texto = str(valor).strip()

    if texto.lower() in {"nan", "none", "null", "nat"}:
        return ""

    return texto


def normalizar_texto(valor) -> str:
    texto = texto_limpo(valor).upper()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    )
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def padronizar_uf(valor) -> str:
    return re.sub(r"[^A-Z]", "", normalizar_texto(valor))[:2]


def limpar_telefone(valor) -> str:
    numeros = re.sub(r"\D", "", texto_limpo(valor))

    if numeros.startswith("0") and len(numeros) > 10:
        numeros = numeros[1:]

    if numeros and not numeros.startswith("55"):
        numeros = f"55{numeros}"

    return numeros


def extrair_primeiro_celular(valor) -> str:
    texto = texto_limpo(valor)

    candidatos = re.findall(
        r"(?:\+?55[\s.-]*)?"
        r"(?:\(?\d{2}\)?[\s.-]*)?"
        r"9\d{4}[\s.-]?\d{4}",
        texto,
    )

    for candidato in candidatos:
        telefone = limpar_telefone(candidato)

        if len(telefone) in {12, 13}:
            return telefone

    return ""


def padronizar_colunas(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.astype(str).str.strip()
    return df


def limpar_colunas_texto(
    df: pd.DataFrame,
    colunas: list[str],
) -> pd.DataFrame:
    df = df.copy()

    for coluna in colunas:
        if coluna in df.columns:
            df[coluna] = df[coluna].apply(texto_limpo)

    return df


def contar_unicos(df: pd.DataFrame, coluna: str) -> int:
    if df is None or coluna not in df.columns:
        return 0

    serie = df[coluna].apply(texto_limpo)
    return int(serie[serie != ""].nunique())


def ler_csv_ofs(arquivo) -> pd.DataFrame:
    conteudo = arquivo.getvalue()

    tentativas = [
        ("utf-8-sig", ","),
        ("utf-8", ","),
        ("latin-1", ","),
        ("utf-8-sig", ";"),
        ("utf-8", ";"),
        ("latin-1", ";"),
    ]

    ultimo_erro = None

    for encoding, separador in tentativas:
        try:
            df = pd.read_csv(
                io.BytesIO(conteudo),
                encoding=encoding,
                sep=separador,
                dtype=str,
                low_memory=False,
            )

            if len(df.columns) > 1:
                return limpar_colunas_texto(
                    padronizar_colunas(df),
                    [
                        "ID da Atividade",
                        "Ticket Jira",
                        "OS",
                        "Placa",
                        "Oficina",
                        "Cliente",
                        "Estado",
                        "Cidade",
                        "Tipo de Atividade",
                        "Status da Atividade",
                        "Data",
                        "Recurso",
                    ],
                )

        except Exception as erro:
            ultimo_erro = erro

    raise ValueError(
        f"Não foi possível ler o CSV. Último erro: {ultimo_erro}"
    )


def ler_cadastro_oficinas(arquivo) -> pd.DataFrame:
    nome = arquivo.name.lower()
    conteudo = arquivo.getvalue()

    if nome.endswith(".ods"):
        df = pd.read_excel(
            io.BytesIO(conteudo),
            engine="odf",
            dtype=str,
        )
    elif nome.endswith(".xlsx"):
        df = pd.read_excel(
            io.BytesIO(conteudo),
            engine="openpyxl",
            dtype=str,
        )
    elif nome.endswith(".csv"):
        return ler_csv_ofs(arquivo)
    else:
        raise ValueError("Formato não permitido. Use ODS, XLSX ou CSV.")

    return padronizar_colunas(df)


def localizar_coluna(
    df: pd.DataFrame,
    possibilidades: list[str],
):
    mapa = {
        normalizar_texto(coluna): coluna
        for coluna in df.columns
    }

    for possibilidade in possibilidades:
        chave = normalizar_texto(possibilidade)

        if chave in mapa:
            return mapa[chave]

    return None


def serie_coluna(
    df: pd.DataFrame,
    coluna,
    valor_padrao="",
) -> pd.Series:
    if coluna is None:
        return pd.Series(
            [valor_padrao] * len(df),
            index=df.index,
        )

    return df[coluna].apply(texto_limpo)


def preparar_cadastro(df_original: pd.DataFrame) -> pd.DataFrame:
    df = df_original.copy()

    coluna_id = localizar_coluna(
        df,
        ["ID", "ID Oficina", "Código", "Codigo"],
    )
    coluna_nome = localizar_coluna(
        df,
        ["Nome Fantasia", "Oficina", "Nome da Oficina", "Nome"],
    )
    coluna_cidade = localizar_coluna(
        df,
        ["Cidade-base", "Cidade Base", "Cidade", "Município", "Municipio"],
    )
    coluna_uf = localizar_coluna(
        df,
        ["UF-base", "UF Base", "UF", "Estado"],
    )
    coluna_contatos = localizar_coluna(
        df,
        [
            "Contatos originais",
            "Contatos",
            "Contato",
            "Telefones",
            "Telefone",
            "Celular",
        ],
    )
    coluna_whatsapp = localizar_coluna(
        df,
        ["WhatsApp", "Whatsapp", "Whats App"],
    )
    coluna_consultor = localizar_coluna(
        df,
        ["Consultor", "Consultor responsável", "Consultor Responsavel"],
    )
    coluna_prioridade = localizar_coluna(df, ["Prioridade"])
    coluna_status = localizar_coluna(df, ["Ativa", "Ativa?", "Status"])
    coluna_observacoes = localizar_coluna(
        df,
        ["Observações", "Observacoes", "Observação", "Observacao"],
    )

    if coluna_nome is None:
        raise ValueError("Não encontrei a coluna com o nome da oficina.")

    cadastro = pd.DataFrame(index=df.index)
    cadastro["ID"] = serie_coluna(df, coluna_id)
    cadastro["Oficina"] = serie_coluna(df, coluna_nome)
    cadastro["Cidade-base"] = serie_coluna(df, coluna_cidade)
    cadastro["UF-base"] = serie_coluna(df, coluna_uf).apply(padronizar_uf)

    cadastro["Consultor automático"] = (
        cadastro["UF-base"]
        .map(MAPA_CONSULTORES_UF)
        .fillna("Não definido")
    )

    cadastro["Consultor"] = serie_coluna(df, coluna_consultor)
    cadastro.loc[
        ~cadastro["Consultor"].isin(CONSULTORES),
        "Consultor",
    ] = ""
    cadastro.loc[
        cadastro["Consultor"] == "",
        "Consultor",
    ] = cadastro["Consultor automático"]

    cadastro["Contatos originais"] = serie_coluna(df, coluna_contatos)
    cadastro["WhatsApp"] = (
        serie_coluna(df, coluna_whatsapp)
        .apply(limpar_telefone)
    )
    whatsapp_extraido = cadastro["Contatos originais"].apply(
        extrair_primeiro_celular
    )
    cadastro.loc[
        cadastro["WhatsApp"] == "",
        "WhatsApp",
    ] = whatsapp_extraido

    cadastro["Prioridade"] = serie_coluna(
        df,
        coluna_prioridade,
        "Normal",
    )
    cadastro.loc[
        ~cadastro["Prioridade"].isin(["Alta", "Normal", "Baixa"]),
        "Prioridade",
    ] = "Normal"

    cadastro["Ativa"] = serie_coluna(df, coluna_status, "Sim")
    cadastro["Observações"] = serie_coluna(df, coluna_observacoes)
    cadastro["Chave Oficina"] = cadastro["Oficina"].apply(normalizar_texto)

    cadastro = cadastro[
        cadastro["Chave Oficina"] != ""
    ].drop_duplicates(
        subset=["Chave Oficina"],
        keep="first",
    )

    return cadastro.sort_values("Oficina").reset_index(drop=True)


def filtrar_somente_manutencoes(df: pd.DataFrame) -> pd.DataFrame:
    """
    Mantém somente atividades cujo Tipo de Atividade contenha
    a palavra MANUTEN, cobrindo manutenção, manutenções,
    manutenção corretiva, preventiva e demais variações.
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=df.columns if df is not None else [])

    if "Tipo de Atividade" not in df.columns:
        raise ValueError(
            "A base não possui a coluna 'Tipo de Atividade'. "
            "Não foi possível filtrar somente manutenções."
        )

    base = df.copy()

    mascara = base["Tipo de Atividade"].apply(
        lambda valor: "MANUTEN" in normalizar_texto(valor)
    )

    return base[mascara].copy().reset_index(drop=True)


# =========================================================
# CHAVES, CONCILIAÇÃO E INDICADORES
# =========================================================

def criar_chaves(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    for coluna in ["Ticket Jira", "Placa", "OS"]:
        if coluna not in df.columns:
            df[coluna] = ""

        df[coluna] = df[coluna].apply(texto_limpo)

    df["Chave Ticket"] = df["Ticket Jira"].apply(normalizar_texto)
    df["Chave Placa"] = df["Placa"].apply(normalizar_texto)
    df["Chave OS"] = df["OS"].apply(normalizar_texto)

    # Os indicadores do painel são baseados em OS.
    # Quando houver OS, ela será a chave principal. A regra anterior
    # usava Ticket + Placa e podia agrupar OS diferentes.
    possui_os = df["Chave OS"] != ""

    df["Chave Atendimento"] = ""

    df.loc[possui_os, "Chave Atendimento"] = (
        "OS|"
        + df.loc[possui_os, "Chave OS"]
        + "|"
        + df.loc[possui_os, "Chave Placa"]
    )

    sem_os = ~possui_os

    df.loc[sem_os, "Chave Atendimento"] = (
        "TICKET|"
        + df.loc[sem_os, "Chave Ticket"]
        + "|"
        + df.loc[sem_os, "Chave Placa"]
    )

    sem_identificador = (
        (df["Chave Ticket"] == "")
        & (df["Chave OS"] == "")
        & (df["Chave Placa"] == "")
    )

    df.loc[sem_identificador, "Chave Atendimento"] = (
        "LINHA|" + df.index[sem_identificador].astype(str)
    )

    return df


def status_normalizado(valor) -> str:
    return normalizar_texto(valor)


def status_executado(valor) -> bool:
    status = status_normalizado(valor)
    return any(
        termo in status
        for termo in [
            "CONCLUID",
            "EXECUTAD",
            "FINALIZAD",
            "COMPLET",
            "REALIZAD",
        ]
    )


def status_improdutivo(valor) -> bool:
    status = status_normalizado(valor)
    return any(
        termo in status
        for termo in [
            "NAO CONCLUIDO",
            "NAO CONCLUIDA",
            "IMPRODUTIVO",
            "IMPRODUTIVA",
            "SEM SUCESSO",
        ]
    )


def status_cancelado(valor) -> bool:
    return "CANCEL" in status_normalizado(valor)


def juntar_unicos(valores) -> str:
    itens = sorted(
        {
            texto_limpo(valor)
            for valor in valores
            if texto_limpo(valor)
        }
    )
    return " | ".join(itens)


def conciliar_bases(
    planejado: pd.DataFrame,
    resultado: pd.DataFrame,
) -> pd.DataFrame:
    # O painel considera exclusivamente manutenções de qualquer tipo.
    planejado = filtrar_somente_manutencoes(planejado)
    resultado = filtrar_somente_manutencoes(resultado)

    planejado = criar_chaves(planejado)
    resultado = criar_chaves(resultado)

    if "Status da Atividade" not in resultado.columns:
        resultado["Status da Atividade"] = ""

    resumo_resultado = (
        resultado
        .groupby("Chave Atendimento", dropna=False)
        .agg(
            Ticket_resultado=("Ticket Jira", "first"),
            Placa_resultado=("Placa", "first"),
            OS_resultado=("OS", juntar_unicos),
            Oficina_resultado=("Oficina", "first"),
            Status_resultado=("Status da Atividade", juntar_unicos),
            Qtd_resultado=("Chave Atendimento", "size"),
        )
        .reset_index()
    )

    if "Status da Atividade" not in planejado.columns:
        planejado["Status da Atividade"] = ""

    resumo_planejado = (
        planejado
        .groupby("Chave Atendimento", dropna=False)
        .agg(
            Ticket_planejado=("Ticket Jira", "first"),
            Placa_planejada=("Placa", "first"),
            OS_planejada=("OS", juntar_unicos),
            Oficina_planejada=("Oficina", "first"),
            Status_planejado=("Status da Atividade", juntar_unicos),
            Qtd_planejada=("Chave Atendimento", "size"),
        )
        .reset_index()
    )

    conciliacao = resumo_planejado.merge(
        resumo_resultado,
        on="Chave Atendimento",
        how="outer",
        indicator=True,
    )

    def classificar(linha) -> str:
        origem = linha["_merge"]
        status_resultado = linha.get("Status_resultado", "")
        status_planejado = linha.get("Status_planejado", "")

        # Se a manutenção já estava cancelada no arquivo planejado,
        # ela não entra como cancelamento do dia, no-show ou planejada válida.
        if (
            origem in {"left_only", "both"}
            and status_cancelado(status_planejado)
        ):
            return "Cancelada no planejamento"

        if origem == "left_only":
            return "No-show"

        if origem == "right_only":
            if status_improdutivo(status_resultado):
                return "Improdutiva extra"
            if status_cancelado(status_resultado):
                return "Cancelada extra"
            if status_executado(status_resultado):
                return "Execução extra"
            return "Evento extra"

        # Só conta como cancelada quando estava válida no planejado
        # e apareceu cancelada posteriormente no relatório de resultado.
        if status_improdutivo(status_resultado):
            return "Improdutiva"
        if status_cancelado(status_resultado):
            return "Cancelada"
        if status_executado(status_resultado):
            return "Executada planejada"

        return "Status intermediário"

    conciliacao["Classificação"] = conciliacao.apply(classificar, axis=1)

    def explicar_classificacao(linha) -> str:
        classificacao = linha.get("Classificação", "")
        origem = linha.get("_merge", "")
        status_planejado = texto_limpo(
            linha.get("Status_planejado", "")
        )
        status_resultado = texto_limpo(
            linha.get("Status_resultado", "")
        )

        if classificacao == "Executada planejada":
            return (
                "OS de manutenção presente no planejado e com status "
                f"executado no resultado: {status_resultado}"
            )
        if classificacao == "Execução extra":
            return (
                "OS de manutenção não encontrada no planejado e com "
                f"status executado no resultado: {status_resultado}"
            )
        if classificacao == "Improdutiva":
            return (
                "OS de manutenção presente no planejado e com status "
                f"improdutivo/não concluído no resultado: {status_resultado}"
            )
        if classificacao == "Improdutiva extra":
            return (
                "OS de manutenção não encontrada no planejado e com "
                f"status improdutivo no resultado: {status_resultado}"
            )
        if classificacao == "Cancelada":
            return (
                "OS estava válida no planejado e apareceu cancelada "
                f"posteriormente no resultado: {status_resultado}"
            )
        if classificacao == "Cancelada no planejamento":
            return (
                "OS já estava cancelada no arquivo planejado e foi "
                f"retirada dos indicadores: {status_planejado}"
            )
        if classificacao == "Cancelada extra":
            return (
                "OS cancelada apareceu somente no resultado e não entra "
                "como cancelamento de uma OS planejada."
            )
        if classificacao == "No-show":
            return (
                "OS de manutenção estava válida no planejado, mas não "
                "foi encontrada no arquivo de resultado."
            )
        if classificacao == "Status intermediário":
            return (
                "OS encontrada nas duas bases, mas o status do resultado "
                f"não foi reconhecido como executado, improdutivo ou cancelado: "
                f"{status_resultado}"
            )
        if origem == "right_only":
            return (
                "OS apareceu somente no resultado, mas o status não foi "
                f"reconhecido: {status_resultado}"
            )

        return "Classificação gerada pelas regras de conciliação."

    conciliacao["Motivo da Classificação"] = conciliacao.apply(
        explicar_classificacao,
        axis=1,
    )

    conciliacao["Troca de OS"] = conciliacao.apply(
        lambda linha: (
            "Sim"
            if (
                linha["_merge"] == "both"
                and texto_limpo(linha.get("OS_planejada", ""))
                != texto_limpo(linha.get("OS_resultado", ""))
            )
            else "Não"
        ),
        axis=1,
    )

    conciliacao["Oficina"] = conciliacao[
        "Oficina_planejada"
    ].fillna(conciliacao["Oficina_resultado"])

    conciliacao["Ticket"] = conciliacao[
        "Ticket_planejado"
    ].fillna(conciliacao["Ticket_resultado"])

    conciliacao["Placa"] = conciliacao[
        "Placa_planejada"
    ].fillna(conciliacao["Placa_resultado"])

    return conciliacao


def calcular_indicadores(conciliacao: pd.DataFrame) -> dict:
    planejadas = int(
        conciliacao[
            (conciliacao["_merge"] != "right_only")
            & (
                conciliacao["Classificação"]
                != "Cancelada no planejamento"
            )
        ].shape[0]
    )
    executadas_planejadas = int(
        (conciliacao["Classificação"] == "Executada planejada").sum()
    )
    improdutivas = int(
        (conciliacao["Classificação"] == "Improdutiva").sum()
    )
    canceladas = int(
        (conciliacao["Classificação"] == "Cancelada").sum()
    )
    no_show = int(
        (conciliacao["Classificação"] == "No-show").sum()
    )
    executadas_extras = int(
        (conciliacao["Classificação"] == "Execução extra").sum()
    )

    mci = (
        executadas_planejadas / planejadas * 100
        if planejadas
        else 0.0
    )

    base_md = executadas_planejadas + improdutivas
    md = improdutivas / base_md * 100 if base_md else 0.0

    return {
        "Planejadas": planejadas,
        "Executadas planejadas": executadas_planejadas,
        "Improdutivas": improdutivas,
        "Canceladas": canceladas,
        "No-show": no_show,
        "Executadas extras": executadas_extras,
        "MCI": mci,
        "MD": md,
        "Índice no-show": (
            no_show / planejadas * 100 if planejadas else 0.0
        ),
        "Índice cancelamento": (
            canceladas / planejadas * 100 if planejadas else 0.0
        ),
        "Execução total": (
            (executadas_planejadas + executadas_extras)
            / planejadas
            * 100
            if planejadas
            else 0.0
        ),
    }


def enriquecer_com_cadastro(
    base: pd.DataFrame,
    cadastro: pd.DataFrame,
) -> pd.DataFrame:
    resultado = base.copy()

    if "Oficina" not in resultado.columns:
        resultado["Oficina"] = ""

    resultado["Chave Oficina"] = resultado["Oficina"].apply(
        normalizar_texto
    )

    colunas = [
        "Chave Oficina",
        "Cidade-base",
        "UF-base",
        "Consultor",
        "WhatsApp",
        "Prioridade",
    ]

    resultado = resultado.merge(
        cadastro[colunas].drop_duplicates(
            subset=["Chave Oficina"]
        ),
        on="Chave Oficina",
        how="left",
    )

    resultado["Consultor"] = resultado["Consultor"].fillna(
        "Não definido"
    )
    resultado["Cidade-base"] = resultado["Cidade-base"].fillna("")
    resultado["UF-base"] = resultado["UF-base"].fillna("")
    resultado["WhatsApp"] = resultado["WhatsApp"].fillna("")
    resultado["Prioridade"] = resultado["Prioridade"].fillna("Normal")

    return resultado


# =========================================================
# PERSISTÊNCIA
# =========================================================

def registro_atividade(
    linha: pd.Series,
    data_operacional: str,
    incluir_status: bool,
) -> dict:
    dados = {
        str(coluna): texto_limpo(valor)
        for coluna, valor in linha.items()
        if coluna not in {
            "Chave Ticket",
            "Chave Placa",
            "Chave OS",
            "Chave Atendimento",
        }
    }

    registro = {
        "data_operacional": data_operacional,
        "chave_atendimento": texto_limpo(linha["Chave Atendimento"]),
        "ticket_jira": texto_limpo(linha.get("Ticket Jira", "")),
        "os": texto_limpo(linha.get("OS", "")),
        "placa": texto_limpo(linha.get("Placa", "")),
        "oficina": texto_limpo(linha.get("Oficina", "")),
        "cliente": texto_limpo(linha.get("Cliente", "")),
        "estado": texto_limpo(linha.get("Estado", "")),
        "cidade": texto_limpo(linha.get("Cidade", "")),
        "tipo_atividade": texto_limpo(
            linha.get("Tipo de Atividade", "")
        ),
        "recurso": texto_limpo(linha.get("Recurso", "")),
        "dados": dados,
    }

    # A tabela de resultado possui status_atividade.
    # A tabela de planejado pode não possuir essa coluna.
    if incluir_status:
        registro["status_atividade"] = texto_limpo(
            linha.get("Status da Atividade", "")
        )

    return registro


def preparar_atividades_para_banco(
    df: pd.DataFrame,
    data_operacional: str,
    incluir_status: bool,
) -> list[dict]:
    base = criar_chaves(df)

    # A tabela possui chave única por data e atendimento.
    # Mantemos uma linha lógica por atendimento.
    base = base.drop_duplicates(
        subset=["Chave Atendimento"],
        keep="last",
    )

    return [
        registro_atividade(
            linha,
            data_operacional,
            incluir_status,
        )
        for _, linha in base.iterrows()
    ]


def salvar_base(
    tipo: str,
    data_operacional: date,
    nome_arquivo: str,
    df: pd.DataFrame,
) -> None:
    cliente = exigir_supabase()
    data_texto = data_operacional.isoformat()
    tabela = TABELA_POR_TIPO[tipo]

    registros = preparar_atividades_para_banco(
        df,
        data_texto,
        incluir_status=(tipo == "resultado"),
    )

    # Substituição segura da base da mesma data.
    cliente.table(tabela).delete().eq(
        "data_operacional",
        data_texto,
    ).execute()

    cliente.table("bases_importadas").delete().eq(
        "tipo",
        tipo,
    ).eq(
        "data_operacional",
        data_texto,
    ).execute()

    inserir_em_lotes(tabela, registros)

    cliente.table("bases_importadas").insert(
        {
            "tipo": tipo,
            "data_operacional": data_texto,
            "nome_arquivo": nome_arquivo,
            "quantidade_registros": len(registros),
            "atualizado_em": datetime.now().isoformat(),
        }
    ).execute()


def salvar_oficinas(cadastro: pd.DataFrame) -> None:
    cliente = exigir_supabase()

    registros = []

    for _, linha in cadastro.iterrows():
        ativa_texto = normalizar_texto(linha.get("Ativa", "SIM"))
        ativa = ativa_texto not in {"NAO", "N", "INATIVA", "INATIVO", "0"}

        registros.append(
            {
                "chave_oficina": texto_limpo(linha["Chave Oficina"]),
                "codigo_oficina": texto_limpo(linha.get("ID", "")),
                "nome_oficina": texto_limpo(linha.get("Oficina", "")),
                "cidade": texto_limpo(linha.get("Cidade-base", "")),
                "uf": texto_limpo(linha.get("UF-base", "")),
                "consultor": texto_limpo(
                    linha.get("Consultor", "Não definido")
                ) or "Não definido",
                "whatsapp": limpar_telefone(linha.get("WhatsApp", "")),
                "prioridade": texto_limpo(
                    linha.get("Prioridade", "Normal")
                ) or "Normal",
                "ativa": ativa,
                "observacoes": texto_limpo(
                    linha.get("Observações", "")
                ),
                "atualizado_em": datetime.now().isoformat(),
            }
        )

    for inicio in range(0, len(registros), 300):
        cliente.table("oficinas").upsert(
            registros[inicio : inicio + 300],
            on_conflict="chave_oficina",
        ).execute()


def carregar_oficinas() -> pd.DataFrame:
    registros = buscar_todos(
        "oficinas",
        ordem="nome_oficina",
    )

    if not registros:
        return pd.DataFrame()

    return pd.DataFrame(
        {
            "ID": [r.get("codigo_oficina", "") for r in registros],
            "Oficina": [r.get("nome_oficina", "") for r in registros],
            "Cidade-base": [r.get("cidade", "") for r in registros],
            "UF-base": [r.get("uf", "") for r in registros],
            "Consultor": [r.get("consultor", "Não definido") for r in registros],
            "WhatsApp": [r.get("whatsapp", "") for r in registros],
            "Prioridade": [r.get("prioridade", "Normal") for r in registros],
            "Ativa": ["Sim" if r.get("ativa", True) else "Não" for r in registros],
            "Observações": [r.get("observacoes", "") for r in registros],
            "Chave Oficina": [r.get("chave_oficina", "") for r in registros],
        }
    )


def carregar_base(tipo: str, data_operacional: str) -> pd.DataFrame:
    tabela = TABELA_POR_TIPO[tipo]
    registros = buscar_todos(
        tabela,
        filtros={"data_operacional": data_operacional},
        ordem="id",
    )

    linhas = []

    for registro in registros:
        dados = dict(registro.get("dados") or {})

        padrao = {
            "Ticket Jira": registro.get("ticket_jira", ""),
            "OS": registro.get("os", ""),
            "Placa": registro.get("placa", ""),
            "Oficina": registro.get("oficina", ""),
            "Cliente": registro.get("cliente", ""),
            "Estado": registro.get("estado", ""),
            "Cidade": registro.get("cidade", ""),
            "Tipo de Atividade": registro.get("tipo_atividade", ""),
            "Status da Atividade": registro.get("status_atividade", ""),
            "Recurso": registro.get("recurso", ""),
        }

        dados.update(padrao)
        linhas.append(dados)

    return pd.DataFrame(linhas)


def listar_bases() -> pd.DataFrame:
    registros = buscar_todos(
        "bases_importadas",
        ordem="data_operacional",
        desc=True,
    )
    return pd.DataFrame(registros)


def excluir_base(tipo: str, data_operacional: str) -> None:
    cliente = exigir_supabase()
    tabela = TABELA_POR_TIPO[tipo]

    cliente.table(tabela).delete().eq(
        "data_operacional",
        data_operacional,
    ).execute()

    cliente.table("bases_importadas").delete().eq(
        "tipo",
        tipo,
    ).eq(
        "data_operacional",
        data_operacional,
    ).execute()


def carregar_consolidado(datas: list[str]) -> pd.DataFrame:
    """Concilia todas as datas completas e cria a visão histórica geral."""
    partes = []

    for data_operacional in datas:
        planejado = carregar_base("planejado", data_operacional)
        resultado = carregar_base("resultado", data_operacional)

        if planejado.empty and resultado.empty:
            continue

        conciliacao_data = conciliar_bases(
            planejado,
            resultado,
        )
        conciliacao_data.insert(
            0,
            "Data Operacional",
            data_operacional,
        )
        partes.append(conciliacao_data)

    if not partes:
        return pd.DataFrame()

    return pd.concat(
        partes,
        ignore_index=True,
        sort=False,
    )


# =========================================================
# APRESENTAÇÃO E DETALHAMENTO CLICÁVEL
# =========================================================

def definir_filtro_detalhe(
    escopo: str,
    classificacao: str,
) -> None:
    st.session_state["detalhe_ativo"] = {
        "escopo": escopo,
        "filtro": classificacao,
    }


def exibir_card_clicavel(
    coluna,
    titulo: str,
    valor: int,
    filtro: str,
    prefixo: str,
) -> None:
    coluna.metric(titulo, valor)

    coluna.button(
        "🔎 Ver OS",
        key=f"{prefixo}_{normalizar_texto(filtro)}",
        on_click=definir_filtro_detalhe,
        args=(prefixo, filtro),
        use_container_width=True,
    )


def exibir_cards_indicadores(
    indicadores: dict,
    prefixo: str,
) -> None:
    colunas = st.columns(6)

    configuracoes = [
        ("Planejadas", "Planejadas"),
        ("Executadas planejadas", "Executada planejada"),
        ("Improdutivas", "Improdutiva"),
        ("Canceladas", "Cancelada"),
        ("No-show", "No-show"),
        ("Executadas extras", "Execução extra"),
    ]

    for coluna, (titulo, filtro) in zip(colunas, configuracoes):
        exibir_card_clicavel(
            coluna,
            titulo,
            indicadores[titulo],
            filtro,
            prefixo,
        )

    st.markdown("#### Indicadores de desempenho")
    i1, i2, i3, i4, i5 = st.columns(5)

    i1.metric(
        "MCI — Execução",
        f'{indicadores["MCI"]:.1f}%',
        help="Executadas planejadas ÷ Planejadas. Meta: 90%.",
    )
    i2.metric(
        "MD — Improdutividade",
        f'{indicadores["MD"]:.1f}%',
        help=(
            "Improdutivas ÷ "
            "(Executadas planejadas + Improdutivas). "
            "Meta: abaixo de 10%."
        ),
    )
    i3.metric(
        "Índice de no-show",
        f'{indicadores["Índice no-show"]:.1f}%',
    )
    i4.metric(
        "Índice de cancelamento",
        f'{indicadores["Índice cancelamento"]:.1f}%',
    )
    i5.metric(
        "Execução total",
        f'{indicadores["Execução total"]:.1f}%',
    )


def filtrar_detalhes(
    conciliacao: pd.DataFrame,
    filtro: str,
) -> pd.DataFrame:
    if filtro == "Planejadas":
        return conciliacao[
            (conciliacao["_merge"] != "right_only")
            & (
                conciliacao["Classificação"]
                != "Cancelada no planejamento"
            )
        ].copy()

    return conciliacao[
        conciliacao["Classificação"] == filtro
    ].copy()


def exibir_detalhamento(
    conciliacao: pd.DataFrame,
    escopo: str,
    contexto: str,
) -> None:
    detalhe_ativo = st.session_state.get("detalhe_ativo")

    if not detalhe_ativo:
        return

    if detalhe_ativo.get("escopo") != escopo:
        return

    filtro = detalhe_ativo.get("filtro")

    if not filtro:
        return

    detalhe = filtrar_detalhes(
        conciliacao,
        filtro,
    )

    st.markdown("---")
    st.subheader(f"🔎 Conferência das OS — {filtro}")
    st.caption(
        f"Contexto: {contexto}. Foram encontrados "
        f"{len(detalhe)} atendimento(s)."
    )

    colunas = [
        "Data Operacional",
        "Classificação",
        "Ticket",
        "Placa",
        "Oficina",
        "Consultor",
        "UF-base",
        "OS_planejada",
        "OS_resultado",
        "Troca de OS",
        "Status_planejado",
        "Status_resultado",
        "Motivo da Classificação",
        "Qtd_planejada",
        "Qtd_resultado",
    ]
    colunas = [
        coluna
        for coluna in colunas
        if coluna in detalhe.columns
    ]

    st.dataframe(
        detalhe[colunas],
        use_container_width=True,
        hide_index=True,
        height=480,
    )

    a, b = st.columns([1, 4])

    if a.button(
        "✖ Fechar",
        key=f"fechar_{escopo}",
        use_container_width=True,
    ):
        st.session_state["detalhe_ativo"] = None
        st.rerun()

    nome_filtro = (
        normalizar_texto(filtro)
        .lower()
        .replace(" ", "_")
    )

    b.download_button(
        "⬇️ Baixar OS filtradas em Excel",
        data=dataframe_para_excel(
            detalhe,
            "OS_filtradas",
        ),
        file_name=f"os_{nome_filtro}.xlsx",
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        key=f"download_{escopo}_{nome_filtro}",
        use_container_width=True,
    )


def dataframe_para_excel(
    df: pd.DataFrame,
    aba: str = "Dados",
) -> bytes:
    buffer = io.BytesIO()

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(
            writer,
            index=False,
            sheet_name=aba[:31],
        )

    buffer.seek(0)
    return buffer.getvalue()


# =========================================================
# CABEÇALHO E MENU
# =========================================================

st.title("🚛 Operações de Campo PS")
st.caption("Sistema de Gestão Operacional de Campo")

if SUPABASE is None:
    st.warning(ERRO_SUPABASE or "Supabase não conectado.")
else:
    st.success("🟢 Supabase conectado e persistência ativa.")

st.divider()

with st.sidebar:
    st.header("Navegação")

    pagina = st.radio(
        "Escolha uma tela",
        [
            "📊 Dashboard Executivo",
            "👤 Painel do Consultor",
            "📥 Importações",
            "🗂 Bases Salvas",
            "🏢 Cadastro de Oficinas",
            "🏆 Ranking por Consultor",
            "📞 Follow",
        ],
    )

    st.divider()
    st.caption(
        "Versão 1.8 — Contagem por OS e auditoria da classificação"
    )


# =========================================================
# IMPORTAÇÕES
# =========================================================

if pagina == "📥 Importações":
    exigir_supabase()

    st.subheader("Importações permanentes")
    st.info(
        "Escolha a data operacional. Se já existir uma base do mesmo "
        "tipo e data, ela será substituída."
    )

    aba_oficinas, aba_planejado, aba_resultado = st.tabs(
        ["🏢 Oficinas", "📅 Planejado", "📈 Resultado"]
    )

    with aba_oficinas:
        arquivo = st.file_uploader(
            "Cadastro oficial das oficinas",
            type=["ods", "xlsx", "csv"],
            key="cadastro_upload",
        )

        if arquivo is not None:
            try:
                cadastro = preparar_cadastro(
                    ler_cadastro_oficinas(arquivo)
                )

                st.write(f"Oficinas identificadas: **{len(cadastro)}**")
                st.dataframe(
                    cadastro.head(20),
                    use_container_width=True,
                    hide_index=True,
                )

                if st.button(
                    "💾 Salvar cadastro no Supabase",
                    type="primary",
                ):
                    salvar_oficinas(cadastro)
                    st.success(
                        f"{len(cadastro)} oficinas salvas/atualizadas."
                    )

            except Exception as erro:
                st.error(f"Erro no cadastro: {erro}")

    with aba_planejado:
        data_planejado = st.date_input(
            "Data operacional do planejado",
            value=date.today(),
            key="data_planejado",
        )
        arquivo = st.file_uploader(
            "Arquivo CSV do planejado",
            type=["csv"],
            key="planejado_upload",
        )

        if arquivo is not None:
            try:
                df = ler_csv_ofs(arquivo)
                st.write(f"Registros lidos: **{len(df)}**")

                if st.button(
                    "💾 Salvar planejado no Supabase",
                    type="primary",
                ):
                    salvar_base(
                        "planejado",
                        data_planejado,
                        arquivo.name,
                        df,
                    )
                    st.success("Planejado salvo permanentemente.")

            except Exception as erro:
                st.error(f"Erro no planejado: {erro}")

    with aba_resultado:
        data_resultado = st.date_input(
            "Data operacional do resultado",
            value=date.today(),
            key="data_resultado",
        )
        arquivo = st.file_uploader(
            "Arquivo CSV do resultado",
            type=["csv"],
            key="resultado_upload",
        )

        if arquivo is not None:
            try:
                df = ler_csv_ofs(arquivo)
                st.write(f"Registros lidos: **{len(df)}**")

                if st.button(
                    "💾 Salvar resultado no Supabase",
                    type="primary",
                ):
                    salvar_base(
                        "resultado",
                        data_resultado,
                        arquivo.name,
                        df,
                    )
                    st.success("Resultado salvo permanentemente.")

            except Exception as erro:
                st.error(f"Erro no resultado: {erro}")


# =========================================================
# BASES SALVAS
# =========================================================

elif pagina == "🗂 Bases Salvas":
    exigir_supabase()

    st.subheader("Bases armazenadas no Supabase")
    bases = listar_bases()

    if bases.empty:
        st.info("Ainda não há bases salvas.")
        st.stop()

    bases_exibir = bases.copy()
    bases_exibir["data_operacional"] = pd.to_datetime(
        bases_exibir["data_operacional"]
    ).dt.strftime("%d/%m/%Y")

    colunas = [
        "tipo",
        "data_operacional",
        "nome_arquivo",
        "quantidade_registros",
        "criado_em",
        "atualizado_em",
    ]
    colunas = [c for c in colunas if c in bases_exibir.columns]

    st.dataframe(
        bases_exibir[colunas],
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("### Excluir uma base")
    opcoes = [
        f"{linha['tipo']} | {linha['data_operacional']} | "
        f"{linha.get('nome_arquivo', '')}"
        for _, linha in bases.iterrows()
    ]

    selecionada = st.selectbox(
        "Base",
        opcoes,
    )
    indice = opcoes.index(selecionada)
    linha = bases.iloc[indice]

    confirmar = st.checkbox(
        "Confirmo que desejo excluir esta base."
    )

    if st.button(
        "🗑 Excluir base",
        disabled=not confirmar,
        type="primary",
    ):
        excluir_base(
            str(linha["tipo"]),
            str(linha["data_operacional"]),
        )
        st.success("Base excluída.")
        st.rerun()


# =========================================================
# PAINEL
# =========================================================

elif pagina == "📊 Dashboard Executivo":
    exigir_supabase()

    bases = listar_bases()

    if bases.empty:
        st.warning("Importe ao menos um planejado e um resultado.")
        st.stop()

    datas_planejado = set(
        bases.loc[
            bases["tipo"] == "planejado",
            "data_operacional",
        ].astype(str)
    )
    datas_resultado = set(
        bases.loc[
            bases["tipo"] == "resultado",
            "data_operacional",
        ].astype(str)
    )

    datas_completas = sorted(
        datas_planejado & datas_resultado,
        reverse=True,
    )

    if not datas_completas:
        st.warning(
            "Não existe uma data com planejado e resultado "
            "salvos juntos."
        )
        st.stop()

    cadastro = carregar_oficinas()
    consolidado = carregar_consolidado(datas_completas)

    if consolidado.empty:
        st.warning("Não foi possível montar o consolidado geral.")
        st.stop()

    if not cadastro.empty:
        consolidado_enriquecido = enriquecer_com_cadastro(
            consolidado,
            cadastro,
        )
    else:
        consolidado_enriquecido = consolidado.copy()

    # =====================================================
    # CONSOLIDADO GERAL — SEMPRE FIXO
    # =====================================================

    st.subheader("Visão consolidada geral")
    st.caption(
        f"Acumulado de {len(datas_completas)} data(s) operacional(is), "
        f"de {pd.to_datetime(min(datas_completas)).strftime('%d/%m/%Y')} "
        f"até {pd.to_datetime(max(datas_completas)).strftime('%d/%m/%Y')}."
    )

    indicadores_consolidados = calcular_indicadores(
        consolidado_enriquecido
    )
    exibir_cards_indicadores(
        indicadores_consolidados,
        prefixo="consolidado_geral",
    )
    exibir_detalhamento(
        consolidado_enriquecido,
        escopo="consolidado_geral",
        contexto="Consolidado geral de todas as datas completas",
    )

    # =====================================================
    # VISÃO DA DATA SELECIONADA
    # =====================================================

    st.divider()
    st.subheader("Visão por dia")

    data_selecionada = st.selectbox(
        "Data analisada",
        datas_completas,
        format_func=lambda valor: pd.to_datetime(valor).strftime(
            "%d/%m/%Y"
        ),
    )

    conciliacao_dia = consolidado_enriquecido[
        consolidado_enriquecido["Data Operacional"].astype(str)
        == str(data_selecionada)
    ].copy()

    indicadores_dia = calcular_indicadores(conciliacao_dia)
    escopo_dia = f"dia_{data_selecionada}"

    exibir_cards_indicadores(
        indicadores_dia,
        prefixo=escopo_dia,
    )
    exibir_detalhamento(
        conciliacao_dia,
        escopo=escopo_dia,
        contexto=(
            "Data "
            f"{pd.to_datetime(data_selecionada).strftime('%d/%m/%Y')}"
        ),
    )

    st.divider()
    esquerda, direita = st.columns(2)

    with esquerda:
        st.subheader("Classificação da data selecionada")

        resumo = (
            conciliacao_dia["Classificação"]
            .value_counts()
            .reset_index()
        )
        resumo.columns = ["Classificação", "Quantidade"]

        grafico = px.bar(
            resumo,
            x="Quantidade",
            y="Classificação",
            orientation="h",
            text="Quantidade",
        )
        grafico.update_layout(
            showlegend=False,
            height=480,
        )
        st.plotly_chart(
            grafico,
            use_container_width=True,
        )

    with direita:
        st.subheader("Resumo da data selecionada")

        st.metric(
            "Atendimentos conciliados",
            len(conciliacao_dia),
        )
        st.metric(
            "Tickets",
            contar_unicos(conciliacao_dia, "Ticket"),
        )
        st.metric(
            "Oficinas",
            contar_unicos(conciliacao_dia, "Oficina"),
        )
        st.metric(
            "Consultores com atendimento",
            contar_unicos(conciliacao_dia, "Consultor"),
        )


# =========================================================
# PAINEL DO CONSULTOR
# =========================================================

elif pagina == "👤 Painel do Consultor":
    exigir_supabase()

    bases = listar_bases()

    if bases.empty:
        st.warning("Importe ao menos um planejado e um resultado.")
        st.stop()

    datas_planejado = set(
        bases.loc[
            bases["tipo"] == "planejado",
            "data_operacional",
        ].astype(str)
    )
    datas_resultado = set(
        bases.loc[
            bases["tipo"] == "resultado",
            "data_operacional",
        ].astype(str)
    )

    datas_completas = sorted(
        datas_planejado & datas_resultado,
        reverse=True,
    )

    if not datas_completas:
        st.warning(
            "Não existe uma data com planejado e resultado "
            "salvos juntos."
        )
        st.stop()

    cadastro = carregar_oficinas()

    if cadastro.empty:
        st.warning(
            "Cadastre as oficinas para habilitar o painel do consultor."
        )
        st.stop()

    # Monta o consolidado de todas as datas completas.
    consolidado = carregar_consolidado(datas_completas)

    if consolidado.empty:
        st.warning(
            "Não foi possível montar o consolidado dos consultores."
        )
        st.stop()

    consolidado_enriquecido = enriquecer_com_cadastro(
        consolidado,
        cadastro,
    )

    consultores_disponiveis = sorted(
        {
            texto_limpo(valor)
            for valor in consolidado_enriquecido["Consultor"]
            if texto_limpo(valor)
        }
    )

    if not consultores_disponiveis:
        st.warning(
            "Nenhum consultor foi identificado nas oficinas "
            "relacionadas às manutenções."
        )
        st.stop()

    st.subheader("Painel do Consultor")

    consultor_selecionado = st.selectbox(
        "Consultor",
        consultores_disponiveis,
        key="consultor_painel_dedicado",
    )

    regiao = REGIOES_CONSULTORES.get(
        consultor_selecionado,
        "Não definida",
    )

    # =====================================================
    # CONSOLIDADO DO CONSULTOR — SEMPRE FIXO
    # =====================================================

    base_consolidada_consultor = consolidado_enriquecido[
        consolidado_enriquecido["Consultor"]
        == consultor_selecionado
    ].copy()

    st.info(
        f"Consultor: **{consultor_selecionado}** · "
        f"Região: **{regiao}**"
    )

    st.subheader("Consolidado do consultor")
    st.caption(
        f"Acumulado de {len(datas_completas)} data(s) operacional(is), "
        f"de {pd.to_datetime(min(datas_completas)).strftime('%d/%m/%Y')} "
        f"até {pd.to_datetime(max(datas_completas)).strftime('%d/%m/%Y')}."
    )

    indicadores_consolidados_consultor = calcular_indicadores(
        base_consolidada_consultor
    )

    escopo_consolidado_consultor = (
        "consolidado_consultor_"
        f"{normalizar_texto(consultor_selecionado)}"
    )

    exibir_cards_indicadores(
        indicadores_consolidados_consultor,
        prefixo=escopo_consolidado_consultor,
    )

    exibir_detalhamento(
        base_consolidada_consultor,
        escopo=escopo_consolidado_consultor,
        contexto=(
            f"Consolidado de {consultor_selecionado} — {regiao}"
        ),
    )

    # =====================================================
    # VISÃO DIÁRIA DO CONSULTOR
    # =====================================================

    st.divider()
    st.subheader("Visão diária do consultor")

    data_selecionada = st.selectbox(
        "Data analisada",
        datas_completas,
        format_func=lambda valor: pd.to_datetime(valor).strftime(
            "%d/%m/%Y"
        ),
        key="data_painel_consultor",
    )

    base_dia_consultor = base_consolidada_consultor[
        base_consolidada_consultor["Data Operacional"].astype(str)
        == str(data_selecionada)
    ].copy()

    st.caption(
        f"{consultor_selecionado} · {regiao} · "
        f"{pd.to_datetime(data_selecionada).strftime('%d/%m/%Y')} · "
        f"{len(base_dia_consultor)} atendimento(s)"
    )

    indicadores_dia_consultor = calcular_indicadores(
        base_dia_consultor
    )

    escopo_dia_consultor = (
        f"dia_consultor_{data_selecionada}_"
        f"{normalizar_texto(consultor_selecionado)}"
    )

    exibir_cards_indicadores(
        indicadores_dia_consultor,
        prefixo=escopo_dia_consultor,
    )

    exibir_detalhamento(
        base_dia_consultor,
        escopo=escopo_dia_consultor,
        contexto=(
            f"{consultor_selecionado} — {regiao} — "
            f"{pd.to_datetime(data_selecionada).strftime('%d/%m/%Y')}"
        ),
    )

    st.divider()
    esquerda, direita = st.columns(2)

    with esquerda:
        st.subheader("Classificação do dia")

        resumo = (
            base_dia_consultor["Classificação"]
            .value_counts()
            .reset_index()
        )
        resumo.columns = ["Classificação", "Quantidade"]

        grafico = px.bar(
            resumo,
            x="Quantidade",
            y="Classificação",
            orientation="h",
            text="Quantidade",
        )
        grafico.update_layout(
            showlegend=False,
            height=480,
        )
        st.plotly_chart(
            grafico,
            use_container_width=True,
        )

    with direita:
        st.subheader("Resumo operacional do dia")

        st.metric(
            "Tickets",
            contar_unicos(base_dia_consultor, "Ticket"),
        )
        st.metric(
            "Oficinas",
            contar_unicos(base_dia_consultor, "Oficina"),
        )
        st.metric(
            "Placas",
            contar_unicos(base_dia_consultor, "Placa"),
        )

    # =====================================================
    # RANKING CONSOLIDADO DAS OFICINAS DO CONSULTOR
    # =====================================================

    st.divider()
    st.subheader("Ranking consolidado das oficinas")

    ranking = (
        base_consolidada_consultor
        .groupby("Oficina", dropna=False)
        .agg(
            Planejadas=(
                "Classificação",
                lambda serie: int(
                    serie.isin(
                        [
                            "Executada planejada",
                            "Improdutiva",
                            "Cancelada",
                            "No-show",
                            "Status intermediário",
                        ]
                    ).sum()
                ),
            ),
            Executadas=(
                "Classificação",
                lambda serie: int(
                    (serie == "Executada planejada").sum()
                ),
            ),
            Improdutivas=(
                "Classificação",
                lambda serie: int(
                    (serie == "Improdutiva").sum()
                ),
            ),
            No_show=(
                "Classificação",
                lambda serie: int(
                    (serie == "No-show").sum()
                ),
            ),
            Canceladas=(
                "Classificação",
                lambda serie: int(
                    (serie == "Cancelada").sum()
                ),
            ),
            Extras=(
                "Classificação",
                lambda serie: int(
                    (serie == "Execução extra").sum()
                ),
            ),
        )
        .reset_index()
    )

    if not ranking.empty:
        ranking["MCI (%)"] = ranking.apply(
            lambda linha: (
                linha["Executadas"] / linha["Planejadas"] * 100
                if linha["Planejadas"]
                else 0.0
            ),
            axis=1,
        )

        ranking["MD (%)"] = ranking.apply(
            lambda linha: (
                linha["Improdutivas"]
                / (
                    linha["Executadas"]
                    + linha["Improdutivas"]
                )
                * 100
                if (
                    linha["Executadas"]
                    + linha["Improdutivas"]
                )
                else 0.0
            ),
            axis=1,
        )

        ranking = ranking.sort_values(
            ["Planejadas", "Oficina"],
            ascending=[False, True],
        )

        ranking.insert(
            0,
            "Posição",
            range(1, len(ranking) + 1),
        )

    st.dataframe(
        ranking,
        use_container_width=True,
        hide_index=True,
    )


# =========================================================
# CADASTRO DE OFICINAS
# =========================================================

elif pagina == "🏢 Cadastro de Oficinas":
    exigir_supabase()

    cadastro = carregar_oficinas()

    if cadastro.empty:
        st.warning("Importe o cadastro das oficinas.")
        st.stop()

    st.subheader("Cadastro mestre de oficinas")

    pesquisa = st.text_input("Pesquisar oficina")
    cadastro_filtrado = cadastro.copy()

    if pesquisa:
        cadastro_filtrado = cadastro_filtrado[
            cadastro_filtrado["Oficina"].str.contains(
                pesquisa,
                case=False,
                na=False,
            )
        ]

    cadastro_editado = st.data_editor(
        cadastro_filtrado,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_config={
            "Consultor": st.column_config.SelectboxColumn(
                "Consultor",
                options=CONSULTORES,
            ),
            "Prioridade": st.column_config.SelectboxColumn(
                "Prioridade",
                options=["Alta", "Normal", "Baixa"],
            ),
            "Ativa": st.column_config.SelectboxColumn(
                "Ativa",
                options=["Sim", "Não"],
            ),
        },
    )

    if st.button(
        "💾 Salvar alterações no Supabase",
        type="primary",
    ):
        cadastro_editado = cadastro_editado.copy()
        cadastro_editado["Chave Oficina"] = cadastro_editado[
            "Oficina"
        ].apply(normalizar_texto)
        salvar_oficinas(cadastro_editado)
        st.success("Cadastro atualizado permanentemente.")


# =========================================================
# RANKING
# =========================================================

elif pagina == "🏆 Ranking por Consultor":
    exigir_supabase()

    bases = listar_bases()
    datas = sorted(
        bases.loc[
            bases["tipo"] == "planejado",
            "data_operacional",
        ].astype(str).unique(),
        reverse=True,
    )

    if not datas:
        st.warning("Não existe planejado salvo.")
        st.stop()

    data_selecionada = st.selectbox(
        "Data do planejado",
        datas,
        format_func=lambda valor: pd.to_datetime(valor).strftime(
            "%d/%m/%Y"
        ),
    )

    cadastro = carregar_oficinas()
    planejado = filtrar_somente_manutencoes(
        carregar_base("planejado", data_selecionada)
    )

    if cadastro.empty:
        st.warning("Cadastre as oficinas.")
        st.stop()

    base = enriquecer_com_cadastro(planejado, cadastro)
    consultores = sorted(base["Consultor"].dropna().unique().tolist())

    consultor = st.selectbox("Consultor", consultores)
    base_consultor = base[base["Consultor"] == consultor]

    ranking = (
        base_consultor
        .groupby("Oficina")
        .agg(
            Planejadas=("Oficina", "size"),
            Tickets=("Ticket Jira", "nunique"),
            Placas=("Placa", "nunique"),
        )
        .reset_index()
        .sort_values(
            ["Planejadas", "Oficina"],
            ascending=[False, True],
        )
    )

    ranking.insert(0, "Posição", range(1, len(ranking) + 1))

    st.dataframe(
        ranking,
        use_container_width=True,
        hide_index=True,
    )


# =========================================================
# FOLLOW
# =========================================================

elif pagina == "📞 Follow":
    exigir_supabase()

    bases = listar_bases()
    datas = sorted(
        bases.loc[
            bases["tipo"] == "planejado",
            "data_operacional",
        ].astype(str).unique(),
        reverse=True,
    )

    if not datas:
        st.warning("Não existe planejado salvo.")
        st.stop()

    data_selecionada = st.selectbox(
        "Data do follow",
        datas,
        format_func=lambda valor: pd.to_datetime(valor).strftime(
            "%d/%m/%Y"
        ),
    )

    cadastro = carregar_oficinas()
    planejado = filtrar_somente_manutencoes(
        carregar_base("planejado", data_selecionada)
    )

    if cadastro.empty:
        st.warning("Cadastre as oficinas.")
        st.stop()

    base = enriquecer_com_cadastro(planejado, cadastro)
    consultores = sorted(base["Consultor"].dropna().unique().tolist())
    consultor = st.selectbox("Consultor", consultores)
    base_consultor = base[base["Consultor"] == consultor]

    ranking = (
        base_consultor
        .groupby(
            ["Oficina", "WhatsApp", "Prioridade"],
            dropna=False,
        )
        .size()
        .reset_index(name="Planejadas")
        .sort_values("Planejadas", ascending=False)
    )

    if ranking.empty:
        st.info("Não há oficinas para o consultor selecionado.")
        st.stop()

    quantidade = st.slider(
        "Quantidade de oficinas",
        min_value=1,
        max_value=len(ranking),
        value=min(3, len(ranking)),
    )

    for _, linha in ranking.head(quantidade).iterrows():
        with st.container(border=True):
            col1, col2, col3 = st.columns([5, 2, 2])

            oficina = texto_limpo(linha["Oficina"])
            col1.subheader(oficina)
            col1.caption(
                f"Prioridade: "
                f"{texto_limpo(linha['Prioridade']) or 'Normal'}"
            )
            col2.metric("Planejadas", int(linha["Planejadas"]))

            telefone = limpar_telefone(linha["WhatsApp"])
            mensagem = (
                f"Bom dia! Sua oficina possui "
                f"{int(linha['Planejadas'])} serviço(s) "
                f"programado(s) para {pd.to_datetime(data_selecionada).strftime('%d/%m/%Y')}. "
                f"Existe algum impedimento para a execução? "
                f"Caso exista, informe para que possamos atuar preventivamente."
            )

            if telefone:
                link = (
                    f"https://wa.me/{telefone}"
                    f"?text={quote(mensagem)}"
                )
                col3.link_button(
                    "📱 Abrir WhatsApp",
                    link,
                    use_container_width=True,
                )
            else:
                col3.warning("Sem WhatsApp")
