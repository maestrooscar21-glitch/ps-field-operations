import html
import io
import re
import unicodedata
import uuid
from datetime import date, datetime
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

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

FUSO_BRASIL = ZoneInfo("America/Sao_Paulo")
DATA_CORTE_NOVA_REGRA = "2026-08-08"


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
    """
    Regra híbrida:
    - datas anteriores a DATA_CORTE_NOVA_REGRA usam a lógica histórica;
    - a partir da data de corte, usa primeira aparição da OS para
      classificar Agendada x Extra/Encaixe.
    """
    planejado = filtrar_somente_manutencoes(planejado)
    resultado = filtrar_somente_manutencoes(resultado)

    planejado = criar_chaves(planejado)
    resultado = criar_chaves(resultado)

    if "Status da Atividade" not in resultado.columns:
        resultado["Status da Atividade"] = ""

    if "Status da Atividade" not in planejado.columns:
        planejado["Status da Atividade"] = ""

    if "__Ativa no Planejamento" not in planejado.columns:
        planejado["__Ativa no Planejamento"] = True

    if "__Primeira Aparição Data" not in planejado.columns:
        planejado["__Primeira Aparição Data"] = ""

    if "__Data Operacional" not in planejado.columns:
        planejado["__Data Operacional"] = ""

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

    resumo_planejado = (
        planejado
        .groupby("Chave Atendimento", dropna=False)
        .agg(
            Ticket_planejado=("Ticket Jira", "first"),
            Placa_planejada=("Placa", "first"),
            OS_planejada=("OS", juntar_unicos),
            Oficina_planejada=("Oficina", "first"),
            Status_planejado=("Status da Atividade", juntar_unicos),
            Primeira_aparicao_data=(
                "__Primeira Aparição Data",
                "first",
            ),
            Data_operacional_planejada=(
                "__Data Operacional",
                "first",
            ),
            Ativa_planejamento=(
                "__Ativa no Planejamento",
                "max",
            ),
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

    def data_referencia_linha(linha) -> str | None:
        data_operacional = converter_data_operacional(
            linha.get("Data_operacional_planejada", "")
        )
        return data_operacional

    def usar_regra_nova(linha) -> bool:
        data_operacional = data_referencia_linha(linha)

        if not data_operacional:
            return False

        return data_operacional >= DATA_CORTE_NOVA_REGRA

    def eh_agendada_nova(linha) -> bool:
        if linha.get("_merge") == "right_only":
            return False

        if not bool(linha.get("Ativa_planejamento", False)):
            return False

        primeira = converter_data_operacional(
            linha.get("Primeira_aparicao_data", "")
        )
        data_operacional = data_referencia_linha(linha)

        if not primeira or not data_operacional:
            return False

        return primeira < data_operacional

    def eh_agendada_historica(linha) -> bool:
        # Na regra antiga, toda manutenção válida presente no planejado
        # era considerada agendada, independentemente de primeira aparição.
        if linha.get("_merge") == "right_only":
            return False

        status_planejado = linha.get("Status_planejado", "")

        if status_cancelado(status_planejado):
            return False

        return True

    def eh_agendada(linha) -> bool:
        if usar_regra_nova(linha):
            return eh_agendada_nova(linha)

        return eh_agendada_historica(linha)

    conciliacao["Origem Agendamento"] = conciliacao.apply(
        lambda linha: (
            "Agendada"
            if eh_agendada(linha)
            else "Extra / encaixe"
        ),
        axis=1,
    )

    def classificar(linha) -> str:
        origem_merge = linha["_merge"]
        status_resultado = linha.get("Status_resultado", "")
        status_planejado = linha.get("Status_planejado", "")
        agendada = linha["Origem Agendamento"] == "Agendada"
        ativa = bool(linha.get("Ativa_planejamento", False))
        nova_regra = usar_regra_nova(linha)

        # Histórico antigo preserva a lógica anterior.
        if not nova_regra:
            if origem_merge == "left_only":
                if status_cancelado(status_planejado):
                    return "Cancelada no agendamento"
                return "No-show"

            if origem_merge == "right_only":
                if status_improdutivo(status_resultado):
                    return "Improdutiva extra"
                if status_cancelado(status_resultado):
                    return "Cancelada extra"
                if status_executado(status_resultado):
                    return "Executada extra"
                return "Evento extra"

            if status_cancelado(status_planejado):
                return "Cancelada no agendamento"

            if status_improdutivo(status_resultado):
                return "Improdutiva agendada"

            if status_cancelado(status_resultado):
                return "Cancelada"

            if status_executado(status_resultado):
                return "Executada agendada"

            return "Status intermediário agendado"

        # Nova regra, a partir da data de corte.
        if origem_merge == "left_only" and not ativa:
            return "Retirada do agendamento"

        if (
            origem_merge in {"left_only", "both"}
            and ativa
            and status_cancelado(status_planejado)
        ):
            return "Cancelada no agendamento"

        if origem_merge == "left_only":
            if agendada:
                return "No-show"
            return "Encaixe não realizado"

        if origem_merge == "right_only":
            if status_improdutivo(status_resultado):
                return "Improdutiva extra"
            if status_cancelado(status_resultado):
                return "Cancelada extra"
            if status_executado(status_resultado):
                return "Executada extra"
            return "Evento extra"

        if status_improdutivo(status_resultado):
            return (
                "Improdutiva agendada"
                if agendada
                else "Improdutiva extra"
            )

        if status_cancelado(status_resultado):
            return (
                "Cancelada"
                if agendada
                else "Cancelada extra"
            )

        if status_executado(status_resultado):
            return (
                "Executada agendada"
                if agendada
                else "Executada extra"
            )

        return (
            "Status intermediário agendado"
            if agendada
            else "Status intermediário extra"
        )

    conciliacao["Classificação"] = conciliacao.apply(
        classificar,
        axis=1,
    )

    def explicar_classificacao(linha) -> str:
        classificacao = linha.get("Classificação", "")
        status_planejado = texto_limpo(
            linha.get("Status_planejado", "")
        )
        status_resultado = texto_limpo(
            linha.get("Status_resultado", "")
        )
        primeira = texto_limpo(
            linha.get("Primeira_aparicao_data", "")
        )
        data_operacional = texto_limpo(
            linha.get("Data_operacional_planejada", "")
        )
        nova_regra = usar_regra_nova(linha)

        if not nova_regra:
            return (
                "Histórico anterior à data de corte: classificação "
                "preservada pela lógica antiga do painel."
            )

        if classificacao == "Executada agendada":
            return (
                f"Manutenção já estava agendada antes de {data_operacional} "
                f"(primeira aparição: {primeira}) e foi executada."
            )
        if classificacao == "Executada extra":
            return (
                "Manutenção não tinha prova de agendamento para essa data "
                "antes do início do dia e foi executada como extra/encaixe."
            )
        if classificacao == "Improdutiva agendada":
            return (
                "Manutenção já estava agendada antes do dia e terminou "
                f"improdutiva/não concluída: {status_resultado}"
            )
        if classificacao == "Improdutiva extra":
            return (
                "Manutenção extra/encaixe terminou improdutiva/não concluída: "
                f"{status_resultado}"
            )
        if classificacao == "Cancelada":
            return (
                "Manutenção estava agendada válida e apareceu cancelada "
                f"posteriormente no resultado: {status_resultado}"
            )
        if classificacao == "Cancelada extra":
            return (
                "Cancelamento de manutenção sem prova de agendamento "
                "anterior para essa mesma data."
            )
        if classificacao == "Cancelada no agendamento":
            return (
                "A manutenção já estava cancelada na fotografia vigente "
                f"do agendamento: {status_planejado}"
            )
        if classificacao == "No-show":
            return (
                "Manutenção estava agendada antes do dia e não apareceu "
                "no arquivo de resultado."
            )
        if classificacao == "Encaixe não realizado":
            return (
                "A manutenção surgiu no próprio dia como extra/encaixe "
                "e não apareceu no resultado; não conta como no-show."
            )
        if classificacao == "Retirada do agendamento":
            return (
                "A OS apareceu em fotografia anterior, mas não está mais "
                "no agendamento vigente dessa data."
            )

        return (
            "Status não reconhecido pelas regras principais. "
            f"Planejado: {status_planejado}; resultado: {status_resultado}."
        )

    conciliacao["Motivo da Classificação"] = conciliacao.apply(
        explicar_classificacao,
        axis=1,
    )

    conciliacao["Regra Aplicada"] = conciliacao.apply(
        lambda linha: (
            "Nova regra"
            if usar_regra_nova(linha)
            else "Regra histórica"
        ),
        axis=1,
    )

    conciliacao["Troca de OS"] = conciliacao.apply(
        lambda linha: (
            "Sim"
            if (
                linha["_merge"] == "both"
                and texto_limpo(
                    linha.get("OS_planejada", "")
                )
                != texto_limpo(
                    linha.get("OS_resultado", "")
                )
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
    agendadas_validas = {
        "Executada agendada",
        "Improdutiva agendada",
        "Cancelada",
        "No-show",
        "Status intermediário agendado",
    }

    manutencoes_agendadas = int(
        conciliacao["Classificação"].isin(
            agendadas_validas
        ).sum()
    )

    agendadas_executadas = int(
        (
            conciliacao["Classificação"]
            == "Executada agendada"
        ).sum()
    )

    executadas_extras = int(
        (
            conciliacao["Classificação"]
            == "Executada extra"
        ).sum()
    )

    improdutivas_agendadas = int(
        (
            conciliacao["Classificação"]
            == "Improdutiva agendada"
        ).sum()
    )

    improdutivas_extras = int(
        (
            conciliacao["Classificação"]
            == "Improdutiva extra"
        ).sum()
    )

    improdutivas = (
        improdutivas_agendadas
        + improdutivas_extras
    )

    canceladas = int(
        (conciliacao["Classificação"] == "Cancelada").sum()
    )

    no_show = int(
        (conciliacao["Classificação"] == "No-show").sum()
    )

    mci = (
        agendadas_executadas
        / manutencoes_agendadas
        * 100
        if manutencoes_agendadas
        else 0.0
    )

    base_md = (
        agendadas_executadas
        + executadas_extras
        + improdutivas
    )

    md = (
        improdutivas / base_md * 100
        if base_md
        else 0.0
    )

    return {
        "Planejadas": manutencoes_agendadas,
        "Executadas planejadas": agendadas_executadas,
        "Improdutivas": improdutivas,
        "Improdutivas agendadas": improdutivas_agendadas,
        "Improdutivas extras": improdutivas_extras,
        "Canceladas": canceladas,
        "No-show": no_show,
        "Executadas extras": executadas_extras,
        "MCI": mci,
        "MD": md,
        "Índice no-show": (
            no_show / manutencoes_agendadas * 100
            if manutencoes_agendadas
            else 0.0
        ),
        "Índice cancelamento": (
            canceladas / manutencoes_agendadas * 100
            if manutencoes_agendadas
            else 0.0
        ),
        "Execução total": (
            (
                agendadas_executadas
                + executadas_extras
            )
            / manutencoes_agendadas
            * 100
            if manutencoes_agendadas
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
    primeira_aparicao: str | None = None,
    primeira_aparicao_data: str | None = None,
    ultima_aparicao: str | None = None,
    ativa_no_planejamento: bool | None = None,
    nome_arquivo_primeira_aparicao: str | None = None,
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

    if incluir_status:
        registro["status_atividade"] = texto_limpo(
            linha.get("Status da Atividade", "")
        )

    if primeira_aparicao is not None:
        registro["primeira_aparicao"] = primeira_aparicao

    if primeira_aparicao_data is not None:
        registro["primeira_aparicao_data"] = primeira_aparicao_data

    if ultima_aparicao is not None:
        registro["ultima_aparicao"] = ultima_aparicao

    if ativa_no_planejamento is not None:
        registro["ativa_no_planejamento"] = ativa_no_planejamento

    if nome_arquivo_primeira_aparicao is not None:
        registro["nome_arquivo_primeira_aparicao"] = (
            nome_arquivo_primeira_aparicao
        )

    return registro


def preparar_atividades_para_banco(
    df: pd.DataFrame,
    data_operacional: str,
    incluir_status: bool,
) -> list[dict]:
    base = criar_chaves(df)

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


def converter_data_operacional(valor) -> str | None:
    texto = texto_limpo(valor)

    if not texto:
        return None

    for dayfirst in (True, False):
        try:
            data_convertida = pd.to_datetime(
                texto,
                dayfirst=dayfirst,
                errors="raise",
            )
            return data_convertida.date().isoformat()
        except Exception:
            pass

    return None


def separar_planejamento_por_data(
    df: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """
    Recebe o CSV de janela móvel do OFS e separa automaticamente
    as manutenções pela coluna Data.
    """
    base = filtrar_somente_manutencoes(df)

    if "Data" not in base.columns:
        raise ValueError(
            "A base não possui a coluna 'Data'. "
            "Não é possível separar a janela por dia."
        )

    base = base.copy()
    base["__Data Operacional"] = base["Data"].apply(
        converter_data_operacional
    )

    invalidas = base["__Data Operacional"].isna().sum()

    if invalidas:
        raise ValueError(
            f"{invalidas} linha(s) de manutenção possuem Data inválida."
        )

    return {
        str(data_operacional): grupo.drop(
            columns=["__Data Operacional"]
        ).reset_index(drop=True)
        for data_operacional, grupo in base.groupby(
            "__Data Operacional"
        )
    }


def salvar_planejamento_janela(
    nome_arquivo: str,
    df: pd.DataFrame,
) -> dict[str, int]:
    """
    Salva uma fotografia de 1, 3 ou mais dias do planejamento.

    A OS é identificada por OS (+ placa quando disponível).
    Para cada OS/data, preserva a primeira vez em que ela apareceu.
    Registros que existiam em uma fotografia anterior daquela data,
    mas desapareceram na fotografia atual, ficam inativos em vez de
    serem apagados. Isso preserva o histórico sem tratá-los como
    agendamento vigente.
    """
    cliente = exigir_supabase()
    grupos = separar_planejamento_por_data(df)
    agora = datetime.now(FUSO_BRASIL)
    agora_iso = agora.isoformat()
    hoje_iso = agora.date().isoformat()
    resumo: dict[str, int] = {}

    for data_operacional, grupo in grupos.items():
        base = criar_chaves(grupo).drop_duplicates(
            subset=["Chave Atendimento"],
            keep="last",
        )

        existentes = buscar_todos(
            "atividades_planejadas",
            filtros={"data_operacional": data_operacional},
        )

        mapa_existentes = {
            texto_limpo(registro.get("chave_atendimento", "")): registro
            for registro in existentes
        }

        # Tudo que não reaparecer nesta fotografia deixa de ser
        # agendamento vigente, mas continua salvo para auditoria.
        if existentes:
            cliente.table("atividades_planejadas").update(
                {
                    "ativa_no_planejamento": False,
                    "ultima_aparicao": agora_iso,
                }
            ).eq(
                "data_operacional",
                data_operacional,
            ).execute()

        registros = []

        for _, linha in base.iterrows():
            chave = texto_limpo(linha["Chave Atendimento"])
            anterior = mapa_existentes.get(chave)

            primeira_aparicao = (
                anterior.get("primeira_aparicao")
                if anterior
                else agora_iso
            )
            primeira_aparicao_data = (
                anterior.get("primeira_aparicao_data")
                if anterior
                else hoje_iso
            )
            arquivo_primeira = (
                anterior.get("nome_arquivo_primeira_aparicao")
                if anterior
                else nome_arquivo
            )

            registro = registro_atividade(
                linha,
                data_operacional,
                incluir_status=True,
                primeira_aparicao=primeira_aparicao,
                primeira_aparicao_data=primeira_aparicao_data,
                ultima_aparicao=agora_iso,
                ativa_no_planejamento=True,
                nome_arquivo_primeira_aparicao=arquivo_primeira,
            )
            registros.append(registro)

        for inicio in range(0, len(registros), 300):
            cliente.table("atividades_planejadas").upsert(
                registros[inicio : inicio + 300],
                on_conflict="data_operacional,chave_atendimento",
            ).execute()

        cliente.table("bases_importadas").delete().eq(
            "tipo",
            "planejado",
        ).eq(
            "data_operacional",
            data_operacional,
        ).execute()

        cliente.table("bases_importadas").insert(
            {
                "tipo": "planejado",
                "data_operacional": data_operacional,
                "nome_arquivo": nome_arquivo,
                "quantidade_registros": len(registros),
                "atualizado_em": agora_iso,
            }
        ).execute()

        resumo[data_operacional] = len(registros)

    return resumo


def salvar_base(
    tipo: str,
    data_operacional: date,
    nome_arquivo: str,
    df: pd.DataFrame,
) -> None:
    """
    Mantido para Resultado. Planejamento usa salvar_planejamento_janela().
    """
    if tipo == "planejado":
        salvar_planejamento_janela(nome_arquivo, df)
        return

    cliente = exigir_supabase()
    data_texto = data_operacional.isoformat()
    tabela = TABELA_POR_TIPO[tipo]

    base = filtrar_somente_manutencoes(df)
    registros = preparar_atividades_para_banco(
        base,
        data_texto,
        incluir_status=True,
    )

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
            "atualizado_em": datetime.now(FUSO_BRASIL).isoformat(),
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


def carregar_base(
    tipo: str,
    data_operacional: str,
) -> pd.DataFrame:
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
            "Status da Atividade": registro.get(
                "status_atividade",
                "",
            ),
            "Recurso": registro.get("recurso", ""),
            "__Data Operacional": registro.get(
                "data_operacional",
                data_operacional,
            ),
        }

        if tipo == "planejado":
            padrao.update(
                {
                    "__Primeira Aparição": registro.get(
                        "primeira_aparicao",
                        "",
                    ),
                    "__Primeira Aparição Data": registro.get(
                        "primeira_aparicao_data",
                        "",
                    ),
                    "__Última Aparição": registro.get(
                        "ultima_aparicao",
                        "",
                    ),
                    "__Ativa no Planejamento": bool(
                        registro.get(
                            "ativa_no_planejamento",
                            True,
                        )
                    ),
                    "__Arquivo Primeira Aparição": registro.get(
                        "nome_arquivo_primeira_aparicao",
                        "",
                    ),
                }
            )

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
        (
            "Manutenções agendadas",
            "Planejadas",
            "Manutenções agendadas",
        ),
        (
            "Agendadas executadas",
            "Executadas planejadas",
            "Executada agendada",
        ),
        (
            "Improdutivas",
            "Improdutivas",
            "Improdutivas",
        ),
        (
            "Canceladas",
            "Canceladas",
            "Cancelada",
        ),
        (
            "No-show",
            "No-show",
            "No-show",
        ),
        (
            "Executadas extras",
            "Executadas extras",
            "Executada extra",
        ),
    ]

    for coluna, (rotulo, chave_indicador, filtro) in zip(
        colunas,
        configuracoes,
    ):
        exibir_card_clicavel(
            coluna,
            rotulo,
            indicadores[chave_indicador],
            filtro,
            prefixo,
        )

    st.markdown("#### Indicadores de desempenho")
    i1, i2, i3, i4, i5 = st.columns(5)

    i1.metric(
        "MCI — Execução",
        f'{indicadores["MCI"]:.1f}%',
        help="Agendadas executadas ÷ Manutenções agendadas. Meta: 90%.",
    )
    i2.metric(
        "MD — Improdutividade",
        f'{indicadores["MD"]:.1f}%',
        help=(
            "Improdutivas totais ÷ "
            "(Agendadas executadas + Executadas extras + "
            "Improdutivas totais). Inclui improdutivas extras. "
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
    if filtro in {"Planejadas", "Manutenções agendadas"}:
        classes = [
            "Executada agendada",
            "Improdutiva agendada",
            "Cancelada",
            "No-show",
            "Status intermediário agendado",
        ]
        return conciliacao[
            conciliacao["Classificação"].isin(classes)
        ].copy()

    if filtro == "Improdutivas":
        return conciliacao[
            conciliacao["Classificação"].isin(
                [
                    "Improdutiva agendada",
                    "Improdutiva extra",
                ]
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
        "Regra Aplicada",
        "Origem Agendamento",
        "Primeira_aparicao_data",
        "Data_operacional_planejada",
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
# FOLLOW — WHATSAPP, FORMULÁRIO E MÉTRICAS
# =========================================================

MOTIVOS_IMPEDIMENTO = [
    "Veículo indisponível",
    "Cliente solicitou alteração da data",
    "Falta de equipamento ou ferramenta",
    "Falta de peça ou insumo",
    "Problema técnico sem solução",
    "Técnico/equipe indisponível",
    "Oficina sem capacidade para a data",
    "Dificuldade de acesso ou deslocamento",
    "Dados/OS insuficientes para executar",
    "Outro",
]


def obter_url_publica_app() -> str:
    """
    Usa a URL atual do Streamlit para montar o link público do formulário.
    Se APP_PUBLIC_URL estiver configurada nos Secrets, ela tem prioridade.
    """
    configurada = texto_limpo(
        st.secrets.get("APP_PUBLIC_URL", "")
    )

    if configurada:
        return configurada.rstrip("/")

    try:
        atual = str(st.context.url)
        partes = urlsplit(atual)
        return urlunsplit(
            (
                partes.scheme,
                partes.netloc,
                partes.path,
                "",
                "",
            )
        ).rstrip("/")
    except Exception:
        return ""


def montar_url_formulario_follow(token: str) -> str:
    base = obter_url_publica_app()

    if not base:
        return ""

    return f"{base}?follow_token={quote(token)}"


def buscar_follow_por_token(token: str) -> dict | None:
    cliente = exigir_supabase()
    resposta = (
        cliente.table("follow_contatos")
        .select("*")
        .eq("token", token)
        .limit(1)
        .execute()
    )

    if not resposta.data:
        return None

    return resposta.data[0]


def obter_ou_criar_follow(
    data_manutencao: str,
    chave_oficina: str,
    oficina: str,
    consultor: str,
    telefone: str,
    qtd_agendadas: int,
    os_agendadas: list[str],
) -> dict:
    cliente = exigir_supabase()

    resposta = (
        cliente.table("follow_contatos")
        .select("*")
        .eq("data_manutencao", data_manutencao)
        .eq("chave_oficina", chave_oficina)
        .eq("consultor", consultor)
        .limit(1)
        .execute()
    )

    token = (
        texto_limpo(resposta.data[0].get("token"))
        if resposta.data
        else str(uuid.uuid4())
    )

    url_formulario = montar_url_formulario_follow(token)

    mensagem = (
        f"Olá! Sua oficina possui {qtd_agendadas} "
        f"manutenção(ões) agendada(s) para "
        f"{pd.to_datetime(data_manutencao).strftime('%d/%m/%Y')}. "
        f"Precisamos confirmar se existe algum impedimento para a execução. "
        f"Por favor, responda o formulário: {url_formulario}"
    )

    registro = {
        "token": token,
        "data_follow": datetime.now(
            FUSO_BRASIL
        ).date().isoformat(),
        "data_manutencao": data_manutencao,
        "chave_oficina": chave_oficina,
        "oficina": oficina,
        "consultor": consultor or "Não definido",
        "telefone": telefone,
        "qtd_agendadas": int(qtd_agendadas),
        "os_agendadas": os_agendadas,
        "mensagem": mensagem,
        "ultima_atualizacao": datetime.now(
            FUSO_BRASIL
        ).isoformat(),
    }

    if resposta.data:
        cliente.table("follow_contatos").update(
            registro
        ).eq(
            "id",
            resposta.data[0]["id"],
        ).execute()
    else:
        registro["status"] = "Preparado"
        registro["preparado_em"] = datetime.now(
            FUSO_BRASIL
        ).isoformat()
        cliente.table("follow_contatos").insert(
            registro
        ).execute()

    atualizado = (
        cliente.table("follow_contatos")
        .select("*")
        .eq("token", token)
        .limit(1)
        .execute()
    )

    return atualizado.data[0]


def registrar_envio_follow(follow_id: int) -> None:
    cliente = exigir_supabase()
    agora = datetime.now(FUSO_BRASIL).isoformat()

    cliente.table("follow_contatos").update(
        {
            "status": "Enviado",
            "enviado_em": agora,
            "ultima_atualizacao": agora,
        }
    ).eq("id", follow_id).execute()


def botao_whatsapp_web(
    telefone: str,
    mensagem: str,
    identificador: str,
) -> None:
    """
    Abre exclusivamente o WhatsApp Web.
    Usa o componente nativo do Streamlit para evitar exibição de HTML bruto.
    Não chama whatsapp:// nem WhatsApp.exe.
    """
    numero = limpar_telefone(telefone)

    if not numero:
        st.warning("Sem WhatsApp cadastrado.")
        return

    texto_url = quote(mensagem)
    link_web = (
        f"https://web.whatsapp.com/send"
        f"?phone={numero}&text={texto_url}"
    )

    st.link_button(
        "📱 Abrir no WhatsApp Web",
        link_web,
        use_container_width=True,
    )


def exibir_formulario_publico_follow() -> bool:
    """
    Se houver ?follow_token=..., a página vira somente o formulário
    público da oficina. O técnico não precisa acessar o restante do painel.
    """
    token = texto_limpo(
        st.query_params.get("follow_token", "")
    )

    if not token:
        return False

    exigir_supabase()
    follow = buscar_follow_por_token(token)

    st.title("✅ Confirmação de Manutenção")
    st.caption(
        "Formulário de confirmação preventiva da oficina."
    )

    if follow is None:
        st.error(
            "Este formulário não foi encontrado ou o link é inválido."
        )
        return True

    data_formatada = pd.to_datetime(
        follow["data_manutencao"]
    ).strftime("%d/%m/%Y")

    st.info(
        f"Oficina: **{texto_limpo(follow.get('oficina'))}** · "
        f"Data: **{data_formatada}** · "
        f"Manutenções: **{int(follow.get('qtd_agendadas') or 0)}**"
    )

    os_disponiveis = [
        texto_limpo(valor)
        for valor in (follow.get("os_agendadas") or [])
        if texto_limpo(valor)
    ]

    with st.form("form_follow_publico"):
        nome_respondente = st.text_input(
            "Seu nome"
        )

        equipamentos = st.radio(
            "Você possui todos os equipamentos/ferramentas necessários?",
            ["Sim", "Não"],
            horizontal=True,
        )

        veiculo = st.radio(
            "O(s) veículo(s) estará(ão) disponível(is) para atendimento?",
            ["Sim", "Não", "Não sei"],
            horizontal=True,
        )

        capacidade = st.radio(
            "A oficina possui técnico/capacidade para atender na data?",
            ["Sim", "Não"],
            horizontal=True,
        )

        impedimento = st.radio(
            "Existe algum impedimento que possa impedir a execução?",
            ["Não, está tudo OK", "Sim, existe impedimento"],
        )

        tem_impedimento = (
            impedimento == "Sim, existe impedimento"
        )

        motivos = []
        os_afetadas = []
        observacao = ""
        previsao = ""

        if tem_impedimento:
            motivos = st.multiselect(
                "Qual(is) o(s) impedimento(s)?",
                MOTIVOS_IMPEDIMENTO,
            )

            if os_disponiveis:
                os_afetadas = st.multiselect(
                    "Quais OS podem ser afetadas?",
                    os_disponiveis,
                )

            observacao = st.text_area(
                "Explique o impedimento",
                placeholder=(
                    "Descreva o que pode impedir a execução e "
                    "qual apoio seria necessário."
                ),
            )

            previsao = st.text_input(
                "Previsão para solução/regularização (opcional)"
            )
        else:
            observacao = st.text_area(
                "Observação (opcional)"
            )

        enviar = st.form_submit_button(
            "Enviar confirmação",
            type="primary",
            use_container_width=True,
        )

    if enviar:
        if not texto_limpo(nome_respondente):
            st.error("Informe seu nome antes de enviar.")
            return True

        if tem_impedimento and not motivos:
            st.error(
                "Selecione ao menos um motivo do impedimento."
            )
            return True

        cliente = exigir_supabase()
        agora = datetime.now(FUSO_BRASIL).isoformat()

        cliente.table("follow_respostas").insert(
            {
                "follow_id": follow["id"],
                "token": token,
                "nome_respondente": nome_respondente,
                "equipamentos_ok": equipamentos == "Sim",
                "veiculo_disponivel": veiculo,
                "capacidade_ok": capacidade == "Sim",
                "tem_impedimento": tem_impedimento,
                "motivos": motivos,
                "os_afetadas": os_afetadas,
                "observacao": observacao,
                "previsao_solucao": previsao,
                "respondido_em": agora,
            }
        ).execute()

        status_resposta = (
            "Com impedimento"
            if tem_impedimento
            else "Sem impedimento"
        )

        cliente.table("follow_contatos").update(
            {
                "status": "Respondido",
                "respondido_em": agora,
                "tem_impedimento": tem_impedimento,
                "status_resposta": status_resposta,
                "ultima_atualizacao": agora,
            }
        ).eq(
            "id",
            follow["id"],
        ).execute()

        st.success(
            "Resposta registrada. Obrigado pela confirmação."
        )

        if tem_impedimento:
            st.warning(
                "O impedimento foi registrado para acompanhamento."
            )
        else:
            st.success(
                "Atendimento confirmado sem impedimento informado."
            )

    return True


def carregar_metricas_follow(
    consultor: str,
    data_manutencao: str,
) -> pd.DataFrame:
    registros = buscar_todos(
        "follow_contatos",
        filtros={
            "consultor": consultor,
            "data_manutencao": data_manutencao,
        },
        ordem="id",
    )

    return pd.DataFrame(registros)


def exibir_metricas_follow(
    consultor: str,
    data_manutencao: str,
    total_oficinas: int,
) -> None:
    contatos = carregar_metricas_follow(
        consultor,
        data_manutencao,
    )

    if contatos.empty:
        preparados = enviados = respondidos = 0
        com_impedimento = sem_impedimento = 0
    else:
        preparados = len(contatos)
        enviados = int(
            contatos["enviado_em"].notna().sum()
            if "enviado_em" in contatos.columns
            else 0
        )
        respondidos = int(
            contatos["respondido_em"].notna().sum()
            if "respondido_em" in contatos.columns
            else 0
        )
        com_impedimento = int(
            (
                contatos.get(
                    "tem_impedimento",
                    pd.Series(dtype=bool),
                )
                == True
            ).sum()
        )
        sem_impedimento = int(
            (
                contatos.get(
                    "tem_impedimento",
                    pd.Series(dtype=bool),
                )
                == False
            ).sum()
        )

    sem_resposta = max(enviados - respondidos, 0)

    st.markdown("#### Métricas do Follow")
    c1, c2, c3, c4, c5, c6 = st.columns(6)

    c1.metric("Oficinas no follow", total_oficinas)
    c2.metric("Preparadas", preparados)
    c3.metric("Enviadas", enviados)
    c4.metric("Respondidas", respondidos)
    c5.metric("Com impedimento", com_impedimento)
    c6.metric("Sem resposta", sem_resposta)

    if respondidos:
        taxa = respondidos / enviados * 100 if enviados else 0
        st.caption(
            f"Taxa de resposta: **{taxa:.1f}%** · "
            f"Sem impedimento: **{sem_impedimento}**."
        )


def exibir_respostas_follow(
    consultor: str,
    data_manutencao: str,
) -> None:
    contatos = carregar_metricas_follow(
        consultor,
        data_manutencao,
    )

    if contatos.empty:
        return

    respondidos = contatos[
        contatos["respondido_em"].notna()
    ].copy()

    if respondidos.empty:
        return

    st.markdown("#### Respostas recebidas")

    colunas = [
        "oficina",
        "qtd_agendadas",
        "status_resposta",
        "respondido_em",
    ]
    colunas = [
        coluna
        for coluna in colunas
        if coluna in respondidos.columns
    ]

    st.dataframe(
        respondidos[colunas],
        use_container_width=True,
        hide_index=True,
    )


# Se o link recebido no WhatsApp tiver um token, mostramos somente
# o formulário público e encerramos a execução do painel normal.
if exibir_formulario_publico_follow():
    st.stop()


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
        "Versão 2.2.3 — Follow exclui manutenções canceladas"
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
        st.markdown("### Janela móvel de agendamentos")
        st.caption(
            "Baixe no OFS a janela de 3 dias (ou outra janela desejada). "
            "O sistema separa automaticamente as manutenções pela coluna Data "
            "e preserva a primeira aparição de cada OS para cada data."
        )

        arquivo = st.file_uploader(
            "Arquivo CSV do agendamento",
            type=["csv"],
            key="planejado_upload",
        )

        if arquivo is not None:
            try:
                df = ler_csv_ofs(arquivo)
                grupos_preview = separar_planejamento_por_data(df)

                st.write(
                    f"Manutenções identificadas no arquivo: "
                    f"**{sum(len(g) for g in grupos_preview.values())}**"
                )

                resumo_preview = pd.DataFrame(
                    [
                        {
                            "Data": pd.to_datetime(data).strftime(
                                "%d/%m/%Y"
                            ),
                            "Manutenções": len(grupo),
                        }
                        for data, grupo in sorted(
                            grupos_preview.items()
                        )
                    ]
                )

                st.dataframe(
                    resumo_preview,
                    use_container_width=True,
                    hide_index=True,
                )

                if st.button(
                    "💾 Salvar janela de agendamentos no Supabase",
                    type="primary",
                ):
                    resumo_salvo = salvar_planejamento_janela(
                        arquivo.name,
                        df,
                    )

                    st.success(
                        "Janela salva. Primeira aparição das OS preservada."
                    )

                    st.dataframe(
                        pd.DataFrame(
                            [
                                {
                                    "Data": pd.to_datetime(data).strftime(
                                        "%d/%m/%Y"
                                    ),
                                    "Manutenções salvas": quantidade,
                                }
                                for data, quantidade in sorted(
                                    resumo_salvo.items()
                                )
                            ]
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )

            except Exception as erro:
                st.error(f"Erro no agendamento: {erro}")

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

    st.subheader("Visão consolidada geral de manutenções")
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
        contexto="Consolidado geral de manutenções de todas as datas completas",
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
                            "Executada agendada",
                            "Improdutiva agendada",
                            "Cancelada",
                            "No-show",
                            "Status intermediário agendado",
                        ]
                    ).sum()
                ),
            ),
            Executadas=(
                "Classificação",
                lambda serie: int(
                    (serie == "Executada agendada").sum()
                ),
            ),
            Improdutivas=(
                "Classificação",
                lambda serie: int(
                    serie.isin(
                        ["Improdutiva agendada", "Improdutiva extra"]
                    ).sum()
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
                    (serie == "Executada extra").sum()
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
        st.warning("Não existe agendamento salvo.")
        st.stop()

    st.subheader("Follow preventivo das oficinas")
    st.caption(
        "Confirme antecipadamente as manutenções agendadas, "
        "registre os contatos e acompanhe impedimentos."
    )

    data_selecionada = st.selectbox(
        "Data das manutenções",
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

    # Mantemos somente a fotografia vigente do planejamento.
    if "__Ativa no Planejamento" in planejado.columns:
        planejado = planejado[
            planejado["__Ativa no Planejamento"] == True
        ].copy()

    if planejado.empty:
        st.info("Não há manutenções vigentes para esta data.")
        st.stop()

    # Classifica canceladas para excluir do follow acionável,
    # sem apagar do histórico.
    planejado["__Cancelada"] = planejado[
        "Status da Atividade"
    ].apply(status_cancelado)

    base_todas = enriquecer_com_cadastro(
        planejado,
        cadastro,
    )

    consultores = sorted(
        {
            texto_limpo(valor)
            for valor in base_todas["Consultor"]
            if texto_limpo(valor)
        }
    )

    if not consultores:
        st.warning(
            "Nenhum consultor foi relacionado às oficinas desta data."
        )
        st.stop()

    consultor = st.selectbox(
        "Consultor",
        consultores,
    )

    base_consultor_todas = base_todas[
        base_todas["Consultor"] == consultor
    ].copy()

    if base_consultor_todas.empty:
        st.info(
            "Não há manutenções para este consultor."
        )
        st.stop()

    # Follow acionável: somente manutenção vigente e não cancelada.
    base_consultor = base_consultor_todas[
        base_consultor_todas["__Cancelada"] == False
    ].copy()

    # Resumo por oficina considerando total encontrado, canceladas e acionáveis.
    resumo_oficinas = (
        base_consultor_todas
        .groupby(
            [
                "Chave Oficina",
                "Oficina",
                "WhatsApp",
                "Prioridade",
            ],
            dropna=False,
        )
        .agg(
            Encontradas=("Oficina", "size"),
            Canceladas=("__Cancelada", "sum"),
            OS_Todas=(
                "OS",
                lambda serie: sorted(
                    {
                        texto_limpo(valor)
                        for valor in serie
                        if texto_limpo(valor)
                    }
                ),
            ),
        )
        .reset_index()
    )

    acionaveis = (
        base_consultor
        .groupby(
            [
                "Chave Oficina",
                "Oficina",
                "WhatsApp",
                "Prioridade",
            ],
            dropna=False,
        )
        .agg(
            Para_Follow=("Oficina", "size"),
            OS_Follow=(
                "OS",
                lambda serie: sorted(
                    {
                        texto_limpo(valor)
                        for valor in serie
                        if texto_limpo(valor)
                    }
                ),
            ),
        )
        .reset_index()
    )

    agrupado = resumo_oficinas.merge(
        acionaveis,
        on=[
            "Chave Oficina",
            "Oficina",
            "WhatsApp",
            "Prioridade",
        ],
        how="left",
    )

    agrupado["Para_Follow"] = (
        agrupado["Para_Follow"]
        .fillna(0)
        .astype(int)
    )
    agrupado["Canceladas"] = (
        agrupado["Canceladas"]
        .fillna(0)
        .astype(int)
    )
    agrupado["OS_Follow"] = agrupado["OS_Follow"].apply(
        lambda valor: valor if isinstance(valor, list) else []
    )

    # Só exibimos oficinas que ainda têm pelo menos uma manutenção acionável.
    agrupado = agrupado[
        agrupado["Para_Follow"] > 0
    ].copy()

    agrupado = agrupado.sort_values(
        ["Para_Follow", "Oficina"],
        ascending=[False, True],
    )

    if agrupado.empty:
        st.info(
            "Não há manutenções acionáveis para Follow "
            "neste consultor/data. As encontradas podem estar canceladas."
        )
        st.stop()

    exibir_metricas_follow(
        consultor,
        data_selecionada,
        len(agrupado),
    )

    st.divider()
    st.markdown("### Oficinas para contato")
    st.caption(
        "O Follow considera somente manutenções vigentes e não canceladas. "
        "As canceladas continuam armazenadas para histórico e auditoria."
    )

    quantidade_maxima = len(agrupado)

    if quantidade_maxima == 1:
        quantidade = 1
        st.caption(
            "1 oficina disponível para o consultor selecionado."
        )
    else:
        quantidade = st.slider(
            "Quantidade de oficinas exibidas",
            min_value=1,
            max_value=quantidade_maxima,
            value=min(3, quantidade_maxima),
        )

    for _, linha in agrupado.head(
        quantidade
    ).iterrows():
        chave_oficina = texto_limpo(
            linha["Chave Oficina"]
        )
        oficina = texto_limpo(
            linha["Oficina"]
        )
        telefone = limpar_telefone(
            linha["WhatsApp"]
        )
        prioridade = (
            texto_limpo(linha["Prioridade"])
            or "Normal"
        )

        qtd_encontradas = int(
            linha["Encontradas"]
        )
        qtd_canceladas = int(
            linha["Canceladas"]
        )
        qtd_agendadas = int(
            linha["Para_Follow"]
        )
        os_agendadas = list(
            linha["OS_Follow"]
            if isinstance(linha["OS_Follow"], list)
            else []
        )

        follow = obter_ou_criar_follow(
            data_manutencao=data_selecionada,
            chave_oficina=chave_oficina,
            oficina=oficina,
            consultor=consultor,
            telefone=telefone,
            qtd_agendadas=qtd_agendadas,
            os_agendadas=os_agendadas,
        )

        with st.container(border=True):
            topo1, topo2, topo3, topo4 = st.columns(
                [4, 1.5, 1.5, 2]
            )

            topo1.subheader(oficina)
            topo1.caption(
                f"Prioridade: {prioridade}"
            )
            topo2.metric(
                "Encontradas",
                qtd_encontradas,
            )
            topo3.metric(
                "Para Follow",
                qtd_agendadas,
            )
            topo4.metric(
                "Canceladas",
                qtd_canceladas,
            )

            status = texto_limpo(
                follow.get("status", "Preparado")
            )
            resposta = texto_limpo(
                follow.get("status_resposta", "")
            )

            status_exibir = (
                f"{status} · {resposta}"
                if resposta
                else status
            )

            st.caption(
                f"Status do Follow: **{status_exibir}**"
            )

            if os_agendadas:
                st.caption(
                    "OS para Follow: "
                    + ", ".join(
                        os_agendadas[:12]
                    )
                    + (
                        "..."
                        if len(os_agendadas) > 12
                        else ""
                    )
                )

            formulario = montar_url_formulario_follow(
                texto_limpo(follow["token"])
            )

            st.text_area(
                "Mensagem preparada",
                texto_limpo(follow["mensagem"]),
                height=120,
                key=f"msg_{follow['id']}",
            )

            col_whats, col_envio, col_form = st.columns(
                [2, 2, 2]
            )

            with col_whats:
                botao_whatsapp_web(
                    telefone,
                    texto_limpo(follow["mensagem"]),
                    str(follow["id"]),
                )

            with col_envio:
                if st.button(
                    "✅ Registrar envio",
                    key=f"envio_{follow['id']}",
                    use_container_width=True,
                    help=(
                        "Use depois de enviar a mensagem para "
                        "registrar o contato no histórico."
                    ),
                ):
                    registrar_envio_follow(
                        int(follow["id"])
                    )
                    st.success(
                        "Envio registrado."
                    )
                    st.rerun()

            with col_form:
                if formulario:
                    st.markdown(
                        f"[🔗 Abrir formulário de teste]"
                        f"({formulario})"
                    )
                else:
                    st.warning(
                        "Não foi possível gerar a URL pública."
                    )

            if follow.get("respondido_em"):
                if bool(
                    follow.get("tem_impedimento")
                ):
                    st.warning(
                        "⚠️ A oficina informou impedimento."
                    )
                else:
                    st.success(
                        "✅ Oficina confirmou sem impedimento."
                    )

    st.divider()
    exibir_respostas_follow(
        consultor,
        data_selecionada,
    )
