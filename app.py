p_mci_md_consultores.py


import io
import re
import unicodedata
from urllib.parse import quote

import pandas as pd
import plotly.express as px
import streamlit as st


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


def calcular_indicadores(conciliacao: pd.DataFrame) -> dict:
    planejadas = int(
        conciliacao[
            conciliacao["_merge"] != "right_only"
        ].shape[0]
    )

    executadas_planejadas = int(
        (
            conciliacao["Classificação"]
            == "Executada planejada"
        ).sum()
    )

    improdutivas = int(
        (
            conciliacao["Classificação"]
            == "Improdutiva"
        ).sum()
    )

    canceladas = int(
        (
            conciliacao["Classificação"]
            == "Cancelada"
        ).sum()
    )

    no_show = int(
        (
            conciliacao["Classificação"]
            == "No-show"
        ).sum()
    )

    executadas_extras = int(
        (
            conciliacao["Classificação"]
            == "Execução extra"
        ).sum()
    )

    # MCI: percentual das atividades planejadas efetivamente executadas.
    mci = (
        executadas_planejadas / planejadas * 100
        if planejadas
        else 0.0
    )

    # MD: improdutivas em relação aos atendimentos com presença do técnico
    # que terminaram executados ou improdutivos.
    base_md = executadas_planejadas + improdutivas
    md = (
        improdutivas / base_md * 100
        if base_md
        else 0.0
    )

    indice_no_show = (
        no_show / planejadas * 100
        if planejadas
        else 0.0
    )

    indice_cancelamento = (
        canceladas / planejadas * 100
        if planejadas
        else 0.0
    )

    indice_execucao_total = (
        (executadas_planejadas + executadas_extras)
        / planejadas
        * 100
        if planejadas
        else 0.0
    )

    return {
        "Planejadas": planejadas,
        "Executadas planejadas": executadas_planejadas,
        "Improdutivas": improdutivas,
        "Canceladas": canceladas,
        "No-show": no_show,
        "Executadas extras": executadas_extras,
        "MCI": mci,
        "MD": md,
        "Índice no-show": indice_no_show,
        "Índice cancelamento": indice_cancelamento,
        "Execução total": indice_execucao_total,
    }


def exibir_cards_indicadores(indicadores: dict) -> None:
    col1, col2, col3, col4, col5, col6 = st.columns(6)

    col1.metric("Planejadas", indicadores["Planejadas"])
    col2.metric(
        "Executadas planejadas",
        indicadores["Executadas planejadas"],
    )
    col3.metric("Improdutivas", indicadores["Improdutivas"])
    col4.metric("Canceladas", indicadores["Canceladas"])
    col5.metric("No-show", indicadores["No-show"])
    col6.metric(
        "Executadas extras",
        indicadores["Executadas extras"],
    )

    st.markdown("#### Indicadores de desempenho")

    i1, i2, i3, i4, i5 = st.columns(5)

    i1.metric(
        "MCI — Execução",
        f'{indicadores["MCI"]:.1f}%',
        help=(
            "Executadas planejadas ÷ Planejadas. "
            "Meta operacional: 90%."
        ),
    )

    i2.metric(
        "MD — Improdutividade",
        f'{indicadores["MD"]:.1f}%',
        help=(
            "Improdutivas ÷ (Executadas planejadas + Improdutivas). "
            "Meta: abaixo de 10%."
        ),
    )

    i3.metric(
        "Índice de no-show",
        f'{indicadores["Índice no-show"]:.1f}%',
        help="No-show ÷ Planejadas.",
    )

    i4.metric(
        "Índice de cancelamento",
        f'{indicadores["Índice cancelamento"]:.1f}%',
        help="Canceladas ÷ Planejadas.",
    )

    i5.metric(
        "Execução total",
        f'{indicadores["Execução total"]:.1f}%',
        help=(
            "(Executadas planejadas + Executadas extras) "
            "÷ Planejadas."
        ),
    )



# =========================================================
# FUNÇÕES DE LIMPEZA
# =========================================================

def texto_limpo(valor) -> str:
    if pd.isna(valor):
        return ""

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
    uf = normalizar_texto(valor)
    uf = re.sub(r"[^A-Z]", "", uf)

    return uf[:2]


def limpar_telefone(valor) -> str:
    texto = texto_limpo(valor)

    if not texto:
        return ""

    numeros = re.sub(r"\D", "", texto)

    if numeros.startswith("0") and len(numeros) > 10:
        numeros = numeros[1:]

    if numeros and not numeros.startswith("55"):
        numeros = f"55{numeros}"

    return numeros


def extrair_primeiro_celular(valor) -> str:
    texto = texto_limpo(valor)

    if not texto:
        return ""

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


def contar_unicos(
    df: pd.DataFrame,
    coluna: str,
) -> int:
    if df is None or coluna not in df.columns:
        return 0

    serie = df[coluna].apply(texto_limpo)
    serie = serie[serie != ""]

    return int(serie.nunique())


# =========================================================
# LEITURA DOS ARQUIVOS
# =========================================================

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
                df = padronizar_colunas(df)

                df = limpar_colunas_texto(
                    df,
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

                return df

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
        raise ValueError(
            "Formato não permitido. Use ODS, XLSX ou CSV."
        )

    return padronizar_colunas(df)


# =========================================================
# CADASTRO DE OFICINAS
# =========================================================

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


def preparar_cadastro(
    df_original: pd.DataFrame,
) -> pd.DataFrame:
    df = df_original.copy()

    coluna_id = localizar_coluna(
        df,
        ["ID", "ID Oficina", "Código", "Codigo"],
    )

    coluna_nome = localizar_coluna(
        df,
        [
            "Nome Fantasia",
            "Oficina",
            "Nome da Oficina",
            "Nome",
        ],
    )

    coluna_cidade = localizar_coluna(
        df,
        [
            "Cidade-base",
            "Cidade Base",
            "Cidade",
            "Município",
            "Municipio",
        ],
    )

    coluna_uf = localizar_coluna(
        df,
        [
            "UF-base",
            "UF Base",
            "UF",
            "Estado",
        ],
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
        [
            "Consultor",
            "Consultor responsável",
            "Consultor Responsavel",
        ],
    )

    coluna_prioridade = localizar_coluna(
        df,
        ["Prioridade"],
    )

    coluna_status = localizar_coluna(
        df,
        ["Ativa", "Ativa?", "Status"],
    )

    coluna_observacoes = localizar_coluna(
        df,
        [
            "Observações",
            "Observacoes",
            "Observação",
            "Observacao",
        ],
    )

    if coluna_nome is None:
        raise ValueError(
            "Não encontrei a coluna com o nome da oficina."
        )

    cadastro = pd.DataFrame(index=df.index)

    cadastro["ID"] = serie_coluna(
        df,
        coluna_id,
    )

    cadastro["Oficina"] = serie_coluna(
        df,
        coluna_nome,
    )

    cadastro["Cidade-base"] = serie_coluna(
        df,
        coluna_cidade,
    )

    cadastro["UF-base"] = serie_coluna(
        df,
        coluna_uf,
    ).apply(padronizar_uf)

    cadastro["Consultor automático"] = (
        cadastro["UF-base"]
        .map(MAPA_CONSULTORES_UF)
        .fillna("Não definido")
    )

    consultor_importado = serie_coluna(
        df,
        coluna_consultor,
    )

    cadastro["Consultor"] = consultor_importado

    cadastro.loc[
        ~cadastro["Consultor"].isin(CONSULTORES),
        "Consultor",
    ] = ""

    cadastro.loc[
        cadastro["Consultor"] == "",
        "Consultor",
    ] = cadastro["Consultor automático"]

    cadastro["Contatos originais"] = serie_coluna(
        df,
        coluna_contatos,
    )

    whatsapp_importado = serie_coluna(
        df,
        coluna_whatsapp,
    ).apply(limpar_telefone)

    whatsapp_extraido = cadastro[
        "Contatos originais"
    ].apply(extrair_primeiro_celular)

    cadastro["WhatsApp"] = whatsapp_importado

    cadastro.loc[
        cadastro["WhatsApp"] == "",
        "WhatsApp",
    ] = whatsapp_extraido

    prioridade = serie_coluna(
        df,
        coluna_prioridade,
        "Normal",
    )

    cadastro["Prioridade"] = prioridade

    cadastro.loc[
        ~cadastro["Prioridade"].isin(
            ["Alta", "Normal", "Baixa"]
        ),
        "Prioridade",
    ] = "Normal"

    cadastro["Ativa"] = serie_coluna(
        df,
        coluna_status,
        "Sim",
    )

    cadastro["Observações"] = serie_coluna(
        df,
        coluna_observacoes,
    )

    cadastro["Chave Oficina"] = cadastro[
        "Oficina"
    ].apply(normalizar_texto)

    cadastro = cadastro[
        cadastro["Chave Oficina"] != ""
    ].copy()

    cadastro = cadastro.drop_duplicates(
        subset=["Chave Oficina"],
        keep="first",
    )

    return cadastro.sort_values(
        "Oficina"
    ).reset_index(drop=True)


# =========================================================
# CRUZAMENTO COM CADASTRO
# =========================================================

def enriquecer_com_cadastro(
    base: pd.DataFrame,
    cadastro: pd.DataFrame,
) -> pd.DataFrame:
    resultado = base.copy()

    if "Oficina" not in resultado.columns:
        resultado["Oficina"] = ""

    resultado["Chave Oficina"] = resultado[
        "Oficina"
    ].apply(normalizar_texto)

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

    resultado["Consultor"] = resultado[
        "Consultor"
    ].fillna("Não definido")

    resultado["Cidade-base"] = resultado[
        "Cidade-base"
    ].fillna("")

    resultado["UF-base"] = resultado[
        "UF-base"
    ].fillna("")

    resultado["WhatsApp"] = resultado[
        "WhatsApp"
    ].fillna("")

    resultado["Prioridade"] = resultado[
        "Prioridade"
    ].fillna("Normal")

    return resultado


# =========================================================
# CONCILIAÇÃO
# =========================================================

def criar_chaves(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    for coluna in ["Ticket Jira", "Placa", "OS"]:
        if coluna not in df.columns:
            df[coluna] = ""

        df[coluna] = df[coluna].apply(texto_limpo)

    df["Chave Ticket"] = df[
        "Ticket Jira"
    ].apply(normalizar_texto)

    df["Chave Placa"] = df[
        "Placa"
    ].apply(normalizar_texto)

    df["Chave OS"] = df[
        "OS"
    ].apply(normalizar_texto)

    df["Chave Atendimento"] = (
        df["Chave Ticket"]
        + "|"
        + df["Chave Placa"]
    )

    sem_ticket = df["Chave Ticket"] == ""

    df.loc[
        sem_ticket,
        "Chave Atendimento",
    ] = (
        "OS|"
        + df.loc[sem_ticket, "Chave OS"]
        + "|"
        + df.loc[sem_ticket, "Chave Placa"]
    )

    return df


def status_normalizado(valor) -> str:
    return normalizar_texto(valor)


def status_executado(valor) -> bool:
    status = status_normalizado(valor)

    termos = [
        "CONCLUID",
        "EXECUTAD",
        "FINALIZAD",
        "COMPLET",
        "REALIZAD",
    ]

    return any(termo in status for termo in termos)


def status_improdutivo(valor) -> bool:
    status = status_normalizado(valor)

    termos = [
        "NAO CONCLUIDO",
        "NAO CONCLUIDA",
        "IMPRODUTIVO",
        "IMPRODUTIVA",
        "SEM SUCESSO",
    ]

    return any(termo in status for termo in termos)


def status_cancelado(valor) -> bool:
    status = status_normalizado(valor)

    return "CANCEL" in status


def conciliar_bases(
    planejado: pd.DataFrame,
    resultado: pd.DataFrame,
) -> pd.DataFrame:
    planejado = criar_chaves(planejado)
    resultado = criar_chaves(resultado)

    col_status = "Status da Atividade"

    if col_status not in resultado.columns:
        resultado[col_status] = ""

    resumo_resultado = (
        resultado
        .groupby("Chave Atendimento", dropna=False)
        .agg(
            Ticket_resultado=("Ticket Jira", "first"),
            Placa_resultado=("Placa", "first"),
            OS_resultado=("OS", lambda x: " | ".join(
                sorted(set(
                    valor
                    for valor in x
                    if texto_limpo(valor)
                ))
            )),
            Oficina_resultado=("Oficina", "first"),
            Status_resultado=(
                col_status,
                lambda x: " | ".join(
                    sorted(set(
                        texto_limpo(valor)
                        for valor in x
                        if texto_limpo(valor)
                    ))
                ),
            ),
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
            OS_planejada=("OS", lambda x: " | ".join(
                sorted(set(
                    valor
                    for valor in x
                    if texto_limpo(valor)
                ))
            )),
            Oficina_planejada=("Oficina", "first"),
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
        status = linha.get("Status_resultado", "")

        # Estava planejada, mas não apareceu no resultado:
        # ausência do técnico/oficina.
        if origem == "left_only":
            return "No-show"

        # Apareceu apenas no resultado.
        if origem == "right_only":
            if status_improdutivo(status):
                return "Improdutiva extra"

            if status_cancelado(status):
                return "Cancelada extra"

            if status_executado(status):
                return "Execução extra"

            return "Evento extra"

        # A ordem é importante: "Não concluído" também contém
        # a palavra "concluído", então improdutiva vem primeiro.
        if status_improdutivo(status):
            return "Improdutiva"

        if status_cancelado(status):
            return "Cancelada"

        if status_executado(status):
            return "Executada planejada"

        return "Status intermediário"

    conciliacao["Classificação"] = conciliacao.apply(
        classificar,
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
    ].fillna(
        conciliacao["Oficina_resultado"]
    )

    conciliacao["Ticket"] = conciliacao[
        "Ticket_planejado"
    ].fillna(
        conciliacao["Ticket_resultado"]
    )

    conciliacao["Placa"] = conciliacao[
        "Placa_planejada"
    ].fillna(
        conciliacao["Placa_resultado"]
    )

    return conciliacao


# =========================================================
# DOWNLOAD
# =========================================================

def dataframe_para_excel(
    df: pd.DataFrame,
    aba="Dados",
) -> bytes:
    buffer = io.BytesIO()

    with pd.ExcelWriter(
        buffer,
        engine="openpyxl",
    ) as writer:
        df.to_excel(
            writer,
            index=False,
            sheet_name=aba,
        )

    buffer.seek(0)

    return buffer.getvalue()


# =========================================================
# ESTADO DA SESSÃO
# =========================================================

estados_iniciais = {
    "cadastro_oficinas": None,
    "planejado_ontem": None,
    "resultado_ontem": None,
    "planejado_hoje": None,
}

for chave, valor in estados_iniciais.items():
    if chave not in st.session_state:
        st.session_state[chave] = valor


# =========================================================
# CABEÇALHO E MENU
# =========================================================

st.title("🚛 Operações de Campo PS")
st.caption("Sistema de Gestão Operacional de Campo")

st.divider()

with st.sidebar:
    st.header("Navegação")

    pagina = st.radio(
        "Escolha uma tela",
        [
            "📊 Painel de Controle",
            "📥 Importações",
            "🔄 Conciliação",
            "🏢 Cadastro de Oficinas",
            "🏆 Ranking por Consultor",
            "📞 Follow de Hoje",
            "📋 Bases Importadas",
        ],
    )

    st.divider()
    st.caption("Versão 0.6.0 — MCI, MD e painel por consultor")


# =========================================================
# TELA DE IMPORTAÇÕES
# =========================================================

if pagina == "📥 Importações":
    st.subheader("Importação dos arquivos")

    st.info(
        "Planejado de ontem e Resultado de ontem devem representar "
        "o mesmo dia operacional."
    )

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 🏢 Cadastro das oficinas")

        arquivo_cadastro = st.file_uploader(
            "Cadastro oficial ou consolidado",
            type=["ods", "xlsx", "csv"],
            key="arquivo_cadastro",
        )

        if arquivo_cadastro is not None:
            try:
                cadastro_bruto = ler_cadastro_oficinas(
                    arquivo_cadastro
                )

                st.session_state.cadastro_oficinas = (
                    preparar_cadastro(cadastro_bruto)
                )

                st.success(
                    f"{len(st.session_state.cadastro_oficinas)} "
                    "oficinas importadas."
                )

            except Exception as erro:
                st.error(f"Erro no cadastro: {erro}")

    with col2:
        st.markdown("### 📅 Planejado de hoje")

        arquivo_planejado_hoje = st.file_uploader(
            "Planejamento usado no ranking e follow",
            type=["csv"],
            key="arquivo_planejado_hoje",
        )

        if arquivo_planejado_hoje is not None:
            try:
                st.session_state.planejado_hoje = ler_csv_ofs(
                    arquivo_planejado_hoje
                )

                st.success(
                    f"{len(st.session_state.planejado_hoje)} "
                    "atividades planejadas para hoje."
                )

            except Exception as erro:
                st.error(f"Erro no planejado de hoje: {erro}")

    st.divider()

    col3, col4 = st.columns(2)

    with col3:
        st.markdown("### 📋 Planejado de ontem")

        arquivo_planejado_ontem = st.file_uploader(
            "Fotografia inicial de ontem",
            type=["csv"],
            key="arquivo_planejado_ontem",
        )

        if arquivo_planejado_ontem is not None:
            try:
                st.session_state.planejado_ontem = ler_csv_ofs(
                    arquivo_planejado_ontem
                )

                st.success(
                    f"{len(st.session_state.planejado_ontem)} "
                    "atividades no planejado de ontem."
                )

            except Exception as erro:
                st.error(f"Erro no planejado de ontem: {erro}")

    with col4:
        st.markdown("### 📈 Resultado de ontem")

        arquivo_resultado_ontem = st.file_uploader(
            "Arquivo consolidado após o encerramento do dia",
            type=["csv"],
            key="arquivo_resultado_ontem",
        )

        if arquivo_resultado_ontem is not None:
            try:
                st.session_state.resultado_ontem = ler_csv_ofs(
                    arquivo_resultado_ontem
                )

                st.success(
                    f"{len(st.session_state.resultado_ontem)} "
                    "atividades no resultado de ontem."
                )

            except Exception as erro:
                st.error(f"Erro no resultado de ontem: {erro}")

    st.divider()

    cadastro = st.session_state.cadastro_oficinas
    planejado_ontem = st.session_state.planejado_ontem
    resultado_ontem = st.session_state.resultado_ontem
    planejado_hoje = st.session_state.planejado_hoje

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "Oficinas cadastradas",
        0 if cadastro is None else len(cadastro),
    )

    c2.metric(
        "Planejado ontem",
        0 if planejado_ontem is None else len(planejado_ontem),
    )

    c3.metric(
        "Resultado ontem",
        0 if resultado_ontem is None else len(resultado_ontem),
    )

    c4.metric(
        "Planejado hoje",
        0 if planejado_hoje is None else len(planejado_hoje),
    )


# =========================================================
# PAINEL DE CONTROLE
# =========================================================

elif pagina == "📊 Painel de Controle":
    planejado_ontem = st.session_state.planejado_ontem
    resultado_ontem = st.session_state.resultado_ontem
    planejado_hoje = st.session_state.planejado_hoje
    cadastro = st.session_state.cadastro_oficinas

    if planejado_ontem is None or resultado_ontem is None:
        st.warning(
            "Importe o planejado e o resultado de ontem "
            "na tela Importações."
        )
        st.stop()

    conciliacao = conciliar_bases(
        planejado_ontem,
        resultado_ontem,
    )

    # =====================================================
    # VISÃO GERAL — SEMPRE FIXA
    # =====================================================

    st.subheader("Visão geral da operação")

    indicadores_gerais = calcular_indicadores(conciliacao)
    exibir_cards_indicadores(indicadores_gerais)

    st.caption(
        "MCI = executadas planejadas ÷ planejadas. "
        "MD = improdutivas ÷ (executadas planejadas + improdutivas)."
    )

    st.divider()

    # =====================================================
    # VISÃO POR CONSULTOR / REGIÃO
    # =====================================================

    st.subheader("Visão por consultor e região")

    if cadastro is None:
        st.info(
            "Importe o cadastro das oficinas para habilitar "
            "a visão por consultor e região."
        )
        conciliacao_filtrada = conciliacao.copy()
        consultor_selecionado = "Todos"

    else:
        conciliacao_enriquecida = enriquecer_com_cadastro(
            conciliacao,
            cadastro,
        )

        consultores_disponiveis = sorted(
            consultor
            for consultor in conciliacao_enriquecida[
                "Consultor"
            ].dropna().unique().tolist()
            if texto_limpo(consultor)
        )

        consultor_selecionado = st.selectbox(
            "Selecione o consultor",
            ["Todos"] + consultores_disponiveis,
        )

        if consultor_selecionado == "Todos":
            conciliacao_filtrada = conciliacao_enriquecida.copy()
            st.caption(
                "Exibindo todas as regiões. "
                "O painel geral acima permanece fixo."
            )
        else:
            conciliacao_filtrada = conciliacao_enriquecida[
                conciliacao_enriquecida["Consultor"]
                == consultor_selecionado
            ].copy()

            regiao = REGIOES_CONSULTORES.get(
                consultor_selecionado,
                "Não definida",
            )

            st.info(
                f"Consultor: **{consultor_selecionado}** · "
                f"Região: **{regiao}** · "
                f"{len(conciliacao_filtrada)} atendimento(s)"
            )

        indicadores_consultor = calcular_indicadores(
            conciliacao_filtrada
        )

        exibir_cards_indicadores(indicadores_consultor)

    st.divider()

    esquerda, direita = st.columns(2)

    with esquerda:
        titulo_grafico = "Classificação dos atendimentos"

        if consultor_selecionado != "Todos":
            titulo_grafico += f" — {consultor_selecionado}"

        st.subheader(titulo_grafico)

        resumo = (
            conciliacao_filtrada["Classificação"]
            .value_counts()
            .reset_index()
        )

        resumo.columns = [
            "Classificação",
            "Quantidade",
        ]

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
        st.subheader("Planejado de hoje")

        if planejado_hoje is None:
            st.info(
                "Importe o planejado de hoje para ver "
                "ranking e follow."
            )

        else:
            planejado_exibir = planejado_hoje.copy()

            if (
                cadastro is not None
                and consultor_selecionado != "Todos"
            ):
                planejado_exibir = enriquecer_com_cadastro(
                    planejado_hoje,
                    cadastro,
                )

                planejado_exibir = planejado_exibir[
                    planejado_exibir["Consultor"]
                    == consultor_selecionado
                ]

            st.metric(
                "Atividades de hoje",
                len(planejado_exibir),
            )

            st.metric(
                "Tickets de hoje",
                contar_unicos(
                    planejado_exibir,
                    "Ticket Jira",
                ),
            )

            st.metric(
                "Oficinas de hoje",
                contar_unicos(
                    planejado_exibir,
                    "Oficina",
                ),
            )


# =========================================================
# CONCILIAÇÃO
# =========================================================

elif pagina == "🔄 Conciliação":
    planejado_ontem = st.session_state.planejado_ontem
    resultado_ontem = st.session_state.resultado_ontem

    if planejado_ontem is None or resultado_ontem is None:
        st.warning(
            "Importe o planejado e o resultado de ontem."
        )
        st.stop()

    conciliacao = conciliar_bases(
        planejado_ontem,
        resultado_ontem,
    )

    st.subheader("Conciliação Planejado × Resultado")

    classificacoes = sorted(
        conciliacao["Classificação"]
        .unique()
        .tolist()
    )

    filtro = st.multiselect(
        "Filtrar classificação",
        classificacoes,
        default=classificacoes,
    )

    somente_troca = st.checkbox(
        "Mostrar somente atendimentos com troca de OS"
    )

    tabela = conciliacao[
        conciliacao["Classificação"].isin(filtro)
    ].copy()

    if somente_troca:
        tabela = tabela[
            tabela["Troca de OS"] == "Sim"
        ]

    colunas_exibir = [
        "Classificação",
        "Ticket",
        "Placa",
        "Oficina",
        "OS_planejada",
        "OS_resultado",
        "Troca de OS",
        "Status_resultado",
        "Qtd_planejada",
        "Qtd_resultado",
    ]

    colunas_exibir = [
        coluna
        for coluna in colunas_exibir
        if coluna in tabela.columns
    ]

    st.write(
        f"Registros encontrados: **{len(tabela)}**"
    )

    st.dataframe(
        tabela[colunas_exibir],
        use_container_width=True,
        hide_index=True,
        height=600,
    )

    st.download_button(
        "⬇️ Baixar conciliação em Excel",
        data=dataframe_para_excel(
            conciliacao,
            "Conciliacao",
        ),
        file_name="conciliacao_planejado_resultado.xlsx",
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        use_container_width=True,
    )


# =========================================================
# CADASTRO DE OFICINAS
# =========================================================

elif pagina == "🏢 Cadastro de Oficinas":
    cadastro = st.session_state.cadastro_oficinas

    if cadastro is None:
        st.warning(
            "Importe o cadastro das oficinas."
        )
        st.stop()

    st.subheader("Cadastro mestre de oficinas")

    pesquisa = st.text_input(
        "Pesquisar oficina"
    )

    cadastro_filtrado = cadastro.copy()

    if pesquisa:
        cadastro_filtrado = cadastro_filtrado[
            cadastro_filtrado["Oficina"]
            .str.contains(
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
                options=[
                    "Alta",
                    "Normal",
                    "Baixa",
                ],
            ),
        },
    )

    st.caption(
        "As alterações permanecem apenas durante a sessão atual."
    )


# =========================================================
# RANKING POR CONSULTOR
# =========================================================

elif pagina == "🏆 Ranking por Consultor":
    cadastro = st.session_state.cadastro_oficinas
    planejado_hoje = st.session_state.planejado_hoje

    if cadastro is None or planejado_hoje is None:
        st.warning(
            "Importe o cadastro e o planejado de hoje."
        )
        st.stop()

    base = enriquecer_com_cadastro(
        planejado_hoje,
        cadastro,
    )

    base = base[
        base["Oficina"].apply(texto_limpo) != ""
    ]

    consultores = sorted(
        base["Consultor"]
        .unique()
        .tolist()
    )

    consultor = st.selectbox(
        "Consultor",
        consultores,
    )

    base_consultor = base[
        base["Consultor"] == consultor
    ]

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
# FOLLOW DE HOJE
# =========================================================

elif pagina == "📞 Follow de Hoje":
    cadastro = st.session_state.cadastro_oficinas
    planejado_hoje = st.session_state.planejado_hoje

    if cadastro is None or planejado_hoje is None:
        st.warning(
            "Importe o cadastro e o planejado de hoje."
        )
        st.stop()

    base = enriquecer_com_cadastro(
        planejado_hoje,
        cadastro,
    )

    base = base[
        base["Oficina"].apply(texto_limpo) != ""
    ]

    consultores = sorted(
        base["Consultor"]
        .unique()
        .tolist()
    )

    consultor = st.selectbox(
        "Consultor",
        consultores,
    )

    base_consultor = base[
        base["Consultor"] == consultor
    ]

    ranking = (
        base_consultor
        .groupby(
            [
                "Oficina",
                "WhatsApp",
                "Prioridade",
            ],
            dropna=False,
        )
        .size()
        .reset_index(name="Planejadas")
        .sort_values(
            "Planejadas",
            ascending=False,
        )
    )

    if ranking.empty:
        st.info(
            "Não há oficinas para o consultor selecionado."
        )
        st.stop()

    quantidade = st.slider(
        "Quantidade de oficinas",
        min_value=1,
        max_value=len(ranking),
        value=min(3, len(ranking)),
    )

    for _, linha in ranking.head(
        quantidade
    ).iterrows():
        with st.container(border=True):
            col1, col2, col3 = st.columns(
                [5, 2, 2]
            )

            oficina = texto_limpo(
                linha["Oficina"]
            )

            col1.subheader(oficina)

            col1.caption(
                f"Prioridade: "
                f"{texto_limpo(linha['Prioridade']) or 'Normal'}"
            )

            col2.metric(
                "Planejadas",
                int(linha["Planejadas"]),
            )

            telefone = limpar_telefone(
                linha["WhatsApp"]
            )

            mensagem = (
                f"Bom dia! Sua oficina possui "
                f"{int(linha['Planejadas'])} serviço(s) "
                f"programado(s). Existe algum impedimento "
                f"para a execução? Caso exista, informe "
                f"para que possamos atuar preventivamente."
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


# =========================================================
# BASES IMPORTADAS
# =========================================================

elif pagina == "📋 Bases Importadas":
    opcao = st.selectbox(
        "Escolha a base",
        [
            "Planejado de ontem",
            "Resultado de ontem",
            "Planejado de hoje",
            "Cadastro de oficinas",
        ],
    )

    mapa_bases = {
        "Planejado de ontem": st.session_state.planejado_ontem,
        "Resultado de ontem": st.session_state.resultado_ontem,
        "Planejado de hoje": st.session_state.planejado_hoje,
        "Cadastro de oficinas": st.session_state.cadastro_oficinas,
    }

    base = mapa_bases[opcao]

    if base is None:
        st.warning(
            "Essa base ainda não foi importada."
        )
        st.stop()

    pesquisa = st.text_input(
        "Pesquisar na base"
    )

    base_exibida = base.copy()

    if pesquisa:
        texto = pesquisa.lower().strip()

        mascara = (
            base_exibida
            .astype(str)
            .apply(
                lambda coluna: (
                    coluna
                    .str.lower()
                    .str.contains(
                        texto,
                        na=False,
                    )
                )
            )
            .any(axis=1)
        )

        base_exibida = base_exibida[
            mascara
        ]

    st.write(
        f"Registros encontrados: **{len(base_exibida)}**"
    )

    st.dataframe(
        base_exibida,
        use_container_width=True,
        hide_index=True,
        height=650,
    )
