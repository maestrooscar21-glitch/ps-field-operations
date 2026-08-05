import io
import json
import re
import unicodedata
from datetime import date, datetime
from urllib.parse import quote

import pandas as pd
import plotly.express as px
import streamlit as st

try:
    from supabase import Client, create_client
except ImportError:
    Client = None
    create_client = None


# =========================================================
# CONFIGURAÇÃO
# =========================================================

st.set_page_config(
    page_title="Operações de Campo PS",
    page_icon="🚛",
    layout="wide",
)

META_MCI = 90.0
META_IMPRODUTIVIDADE = 10.0

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
    "Marcos Bispo": "Rio Grande do Sul e Santa Catarina",
    "Roberto Rugel": "Paraná",
    "Gleci Nunes": "Centro-Oeste",
    "Não definido": "Não definida",
}


# =========================================================
# SUPABASE
# =========================================================

@st.cache_resource
def obter_supabase():
    if create_client is None:
        return None

    url = st.secrets.get("SUPABASE_URL", "")
    chave = (
        st.secrets.get("SUPABASE_SERVICE_KEY", "")
        or st.secrets.get("SUPABASE_KEY", "")
    )

    if not url or not chave:
        return None

    return create_client(url, chave)


supabase = obter_supabase()
MODO_BANCO = supabase is not None


def executar_em_lotes(registros, tamanho=400):
    for inicio in range(0, len(registros), tamanho):
        yield registros[inicio: inicio + tamanho]


def buscar_todos(nome_tabela: str, colunas="*") -> list[dict]:
    if not MODO_BANCO:
        return []

    resultado = []
    inicio = 0
    tamanho = 1000

    while True:
        resposta = (
            supabase.table(nome_tabela)
            .select(colunas)
            .range(inicio, inicio + tamanho - 1)
            .execute()
        )
        dados = resposta.data or []
        resultado.extend(dados)

        if len(dados) < tamanho:
            break

        inicio += tamanho

    return resultado


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


def contar_unicos(df: pd.DataFrame, coluna: str) -> int:
    if df is None or coluna not in df.columns:
        return 0

    serie = df[coluna].apply(texto_limpo)
    serie = serie[serie != ""]
    return int(serie.nunique())


def valor_json_seguro(valor):
    if pd.isna(valor):
        return None
    if isinstance(valor, (datetime, date, pd.Timestamp)):
        return valor.isoformat()
    if hasattr(valor, "item"):
        try:
            return valor.item()
        except Exception:
            pass
    return valor


def linha_para_json(linha: pd.Series) -> dict:
    return {
        str(chave): valor_json_seguro(valor)
        for chave, valor in linha.to_dict().items()
    }


def formatar_percentual(valor: float) -> str:
    return f"{valor:.2f}%".replace(".", ",")


def normalizar_data(valor) -> str | None:
    texto = texto_limpo(valor)
    if not texto:
        return None

    convertido = pd.to_datetime(texto, dayfirst=True, errors="coerce")
    if pd.isna(convertido):
        return None

    return convertido.date().isoformat()


def detectar_data_base(df: pd.DataFrame) -> str | None:
    candidatos = [
        "Data",
        "Data da Atividade",
        "Data de Rota",
        "Data Operacional",
    ]

    for coluna in candidatos:
        if coluna in df.columns:
            datas = [
                normalizar_data(valor)
                for valor in df[coluna]
            ]
            datas = [valor for valor in datas if valor]
            if datas:
                return pd.Series(datas).mode().iloc[0]

    return None


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
                return limpar_colunas_texto(
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
        ["Nome Fantasia", "Oficina", "Nome da Oficina", "Nome"],
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
        [
            "Consultor",
            "Consultor responsável",
            "Consultor Responsavel",
        ],
    )
    coluna_prioridade = localizar_coluna(df, ["Prioridade"])
    coluna_status = localizar_coluna(df, ["Ativa", "Ativa?", "Status"])
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
    cadastro["ID"] = serie_coluna(df, coluna_id)
    cadastro["Oficina"] = serie_coluna(df, coluna_nome)
    cadastro["Cidade-base"] = serie_coluna(df, coluna_cidade)
    cadastro["UF-base"] = serie_coluna(
        df,
        coluna_uf,
    ).apply(padronizar_uf)

    cadastro["Consultor automático"] = (
        cadastro["UF-base"]
        .map(MAPA_CONSULTORES_UF)
        .fillna("Não definido")
    )

    cadastro["Consultor"] = serie_coluna(
        df,
        coluna_consultor,
    )
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

    cadastro["Prioridade"] = serie_coluna(
        df,
        coluna_prioridade,
        "Normal",
    )
    cadastro.loc[
        ~cadastro["Prioridade"].isin(
            ["Alta", "Normal", "Baixa"]
        ),
        "Prioridade",
    ] = "Normal"

    status = serie_coluna(df, coluna_status, "Sim")
    cadastro["Ativa"] = status.apply(
        lambda valor: normalizar_texto(valor)
        not in {"NAO", "N", "INATIVA", "INATIVO", "FALSE", "0"}
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


def cadastro_para_supabase(cadastro: pd.DataFrame) -> list[dict]:
    registros = []

    for _, linha in cadastro.iterrows():
        registros.append(
            {
                "chave_oficina": linha["Chave Oficina"],
                "codigo_oficina": texto_limpo(linha.get("ID", "")) or None,
                "nome_oficina": texto_limpo(linha["Oficina"]),
                "cidade": texto_limpo(linha["Cidade-base"]) or None,
                "uf": texto_limpo(linha["UF-base"]) or None,
                "consultor": texto_limpo(linha["Consultor"]) or "Não definido",
                "whatsapp": limpar_telefone(linha["WhatsApp"]) or None,
                "prioridade": texto_limpo(linha["Prioridade"]) or "Normal",
                "ativa": bool(linha["Ativa"]),
                "observacoes": texto_limpo(linha["Observações"]) or None,
                "atualizado_em": datetime.now().isoformat(),
            }
        )

    return registros


def salvar_cadastro_supabase(cadastro: pd.DataFrame):
    registros = cadastro_para_supabase(cadastro)

    for lote in executar_em_lotes(registros):
        (
            supabase.table("oficinas")
            .upsert(lote, on_conflict="chave_oficina")
            .execute()
        )


def carregar_cadastro_supabase() -> pd.DataFrame:
    dados = buscar_todos("oficinas")

    if not dados:
        return pd.DataFrame()

    df = pd.DataFrame(dados)
    renomear = {
        "codigo_oficina": "ID",
        "nome_oficina": "Oficina",
        "cidade": "Cidade-base",
        "uf": "UF-base",
        "consultor": "Consultor",
        "whatsapp": "WhatsApp",
        "prioridade": "Prioridade",
        "ativa": "Ativa",
        "observacoes": "Observações",
        "chave_oficina": "Chave Oficina",
    }
    df = df.rename(columns=renomear)

    for coluna in renomear.values():
        if coluna not in df.columns:
            df[coluna] = ""

    df["Consultor automático"] = (
        df["UF-base"]
        .map(MAPA_CONSULTORES_UF)
        .fillna("Não definido")
    )
    df["Contatos originais"] = ""

    return df[
        [
            "ID",
            "Oficina",
            "Cidade-base",
            "UF-base",
            "Consultor automático",
            "Consultor",
            "Contatos originais",
            "WhatsApp",
            "Prioridade",
            "Ativa",
            "Observações",
            "Chave Oficina",
        ]
    ].sort_values("Oficina").reset_index(drop=True)


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

    disponiveis = [
        coluna for coluna in colunas
        if coluna in cadastro.columns
    ]

    resultado = resultado.merge(
        cadastro[disponiveis].drop_duplicates(
            subset=["Chave Oficina"]
        ),
        on="Chave Oficina",
        how="left",
    )

    for coluna, padrao in {
        "Consultor": "Não definido",
        "Cidade-base": "",
        "UF-base": "",
        "WhatsApp": "",
        "Prioridade": "Normal",
    }.items():
        if coluna not in resultado.columns:
            resultado[coluna] = padrao
        else:
            resultado[coluna] = resultado[coluna].fillna(padrao)

    return resultado


# =========================================================
# CONCILIAÇÃO E INDICADORES
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

    vazias = (
        (df["Chave Ticket"] == "")
        & (df["Chave OS"] == "")
        & (df["Chave Placa"] == "")
    )
    df.loc[vazias, "Chave Atendimento"] = (
        "LINHA|"
        + df.loc[vazias].index.astype(str)
    )

    return df


def status_normalizado(valor) -> str:
    return normalizar_texto(valor)


def status_executado(valor) -> bool:
    status = status_normalizado(valor)

    if status_improdutivo(status):
        return False

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
    return "CANCEL" in status_normalizado(valor)


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
            OS_resultado=(
                "OS",
                lambda x: " | ".join(
                    sorted(
                        set(
                            valor
                            for valor in x
                            if texto_limpo(valor)
                        )
                    )
                ),
            ),
            Oficina_resultado=("Oficina", "first"),
            Estado_resultado=(
                "Estado",
                "first",
            ) if "Estado" in resultado.columns else (
                "Chave Atendimento",
                lambda x: "",
            ),
            Status_resultado=(
                col_status,
                lambda x: " | ".join(
                    sorted(
                        set(
                            texto_limpo(valor)
                            for valor in x
                            if texto_limpo(valor)
                        )
                    )
                ),
            ),
            Qtd_resultado=("Chave Atendimento", "size"),
        )
        .reset_index()
    )

    agregacoes_planejado = {
        "Ticket_planejado": ("Ticket Jira", "first"),
        "Placa_planejada": ("Placa", "first"),
        "OS_planejada": (
            "OS",
            lambda x: " | ".join(
                sorted(
                    set(
                        valor
                        for valor in x
                        if texto_limpo(valor)
                    )
                )
            ),
        ),
        "Oficina_planejada": ("Oficina", "first"),
        "Qtd_planejada": ("Chave Atendimento", "size"),
    }

    if "Estado" in planejado.columns:
        agregacoes_planejado["Estado_planejado"] = (
            "Estado",
            "first",
        )

    resumo_planejado = (
        planejado
        .groupby("Chave Atendimento", dropna=False)
        .agg(**agregacoes_planejado)
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

        if origem == "left_only":
            return "No-show"

        if origem == "right_only":
            if status_improdutivo(status):
                return "Improdutiva extra"
            if status_cancelado(status):
                return "Cancelada extra"
            if status_executado(status):
                return "Execução extra"
            return "Evento extra"

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

    estado_planejado = (
        conciliacao["Estado_planejado"]
        if "Estado_planejado" in conciliacao.columns
        else pd.Series("", index=conciliacao.index)
    )
    estado_resultado = (
        conciliacao["Estado_resultado"]
        if "Estado_resultado" in conciliacao.columns
        else pd.Series("", index=conciliacao.index)
    )
    conciliacao["Estado"] = estado_planejado.fillna(
        estado_resultado
    )

    return conciliacao


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

    total_executadas = (
        executadas_planejadas
        + executadas_extras
    )

    def percentual(parte, total):
        return 0.0 if total <= 0 else (parte / total) * 100

    return {
        "planejadas": planejadas,
        "executadas_planejadas": executadas_planejadas,
        "improdutivas": improdutivas,
        "canceladas": canceladas,
        "no_show": no_show,
        "executadas_extras": executadas_extras,
        "total_executadas": total_executadas,
        "indice_execucao": percentual(
            executadas_planejadas,
            planejadas,
        ),
        "indice_improdutividade": percentual(
            improdutivas,
            planejadas,
        ),
        "indice_cancelamento": percentual(
            canceladas,
            planejadas,
        ),
        "indice_no_show": percentual(
            no_show,
            planejadas,
        ),
        "indice_execucao_total": percentual(
            total_executadas,
            planejadas,
        ),
    }


# =========================================================
# PERSISTÊNCIA DAS BASES
# =========================================================

def dataframe_para_registros(
    df: pd.DataFrame,
    data_operacional: str,
) -> list[dict]:
    base = criar_chaves(df)
    registros = []

    for _, linha in base.iterrows():
        registros.append(
            {
                "data_operacional": data_operacional,
                "chave_atendimento": texto_limpo(
                    linha["Chave Atendimento"]
                ),
                "ticket_jira": texto_limpo(
                    linha.get("Ticket Jira", "")
                ) or None,
                "os": texto_limpo(
                    linha.get("OS", "")
                ) or None,
                "placa": texto_limpo(
                    linha.get("Placa", "")
                ) or None,
                "oficina": texto_limpo(
                    linha.get("Oficina", "")
                ) or None,
                "cliente": texto_limpo(
                    linha.get("Cliente", "")
                ) or None,
                "estado": texto_limpo(
                    linha.get("Estado", "")
                ) or None,
                "cidade": texto_limpo(
                    linha.get("Cidade", "")
                ) or None,
                "tipo_atividade": texto_limpo(
                    linha.get("Tipo de Atividade", "")
                ) or None,
                "status_atividade": texto_limpo(
                    linha.get("Status da Atividade", "")
                ) or None,
                "recurso": texto_limpo(
                    linha.get("Recurso", "")
                ) or None,
                "dados": linha_para_json(linha),
            }
        )

    return registros


def salvar_base_supabase(
    tipo: str,
    data_operacional: str,
    nome_arquivo: str,
    df: pd.DataFrame,
):
    tabela = (
        "atividades_planejadas"
        if tipo == "planejado"
        else "atividades_resultado"
    )

    (
        supabase.table(tabela)
        .delete()
        .eq("data_operacional", data_operacional)
        .execute()
    )

    registros = dataframe_para_registros(
        df,
        data_operacional,
    )

    for lote in executar_em_lotes(registros):
        supabase.table(tabela).insert(lote).execute()

    metadados = {
        "tipo": tipo,
        "data_operacional": data_operacional,
        "nome_arquivo": nome_arquivo,
        "quantidade_registros": len(df),
        "atualizado_em": datetime.now().isoformat(),
    }

    (
        supabase.table("bases_importadas")
        .upsert(
            metadados,
            on_conflict="tipo,data_operacional",
        )
        .execute()
    )


def registros_para_dataframe(dados: list[dict]) -> pd.DataFrame:
    if not dados:
        return pd.DataFrame()

    linhas = []
    for registro in dados:
        dados_originais = registro.get("dados") or {}
        if isinstance(dados_originais, str):
            try:
                dados_originais = json.loads(dados_originais)
            except json.JSONDecodeError:
                dados_originais = {}

        linha = dict(dados_originais)

        mapa_fallback = {
            "Ticket Jira": "ticket_jira",
            "OS": "os",
            "Placa": "placa",
            "Oficina": "oficina",
            "Cliente": "cliente",
            "Estado": "estado",
            "Cidade": "cidade",
            "Tipo de Atividade": "tipo_atividade",
            "Status da Atividade": "status_atividade",
            "Recurso": "recurso",
        }

        for destino, origem in mapa_fallback.items():
            if destino not in linha:
                linha[destino] = registro.get(origem)

        linha["Data Operacional"] = registro.get(
            "data_operacional"
        )
        linhas.append(linha)

    return pd.DataFrame(linhas)


def carregar_base_supabase(
    tipo: str,
    data_operacional: str,
) -> pd.DataFrame:
    tabela = (
        "atividades_planejadas"
        if tipo == "planejado"
        else "atividades_resultado"
    )

    resposta = (
        supabase.table(tabela)
        .select("*")
        .eq("data_operacional", data_operacional)
        .range(0, 9999)
        .execute()
    )

    return registros_para_dataframe(
        resposta.data or []
    )


def listar_bases_supabase() -> pd.DataFrame:
    dados = buscar_todos(
        "bases_importadas",
        "id,tipo,data_operacional,nome_arquivo,"
        "quantidade_registros,criado_em,atualizado_em",
    )

    if not dados:
        return pd.DataFrame()

    df = pd.DataFrame(dados)
    return df.sort_values(
        ["data_operacional", "tipo"],
        ascending=[False, True],
    ).reset_index(drop=True)


def excluir_base_supabase(
    tipo: str,
    data_operacional: str,
):
    tabela = (
        "atividades_planejadas"
        if tipo == "planejado"
        else "atividades_resultado"
    )

    (
        supabase.table(tabela)
        .delete()
        .eq("data_operacional", data_operacional)
        .execute()
    )
    (
        supabase.table("bases_importadas")
        .delete()
        .eq("tipo", tipo)
        .eq("data_operacional", data_operacional)
        .execute()
    )


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
# ESTADO DA SESSÃO E CARGA INICIAL
# =========================================================

estados_iniciais = {
    "cadastro_oficinas": None,
    "planejado_selecionado": None,
    "resultado_selecionado": None,
    "planejado_follow": None,
}

for chave, valor in estados_iniciais.items():
    if chave not in st.session_state:
        st.session_state[chave] = valor

if (
    MODO_BANCO
    and st.session_state.cadastro_oficinas is None
):
    try:
        cadastro_banco = carregar_cadastro_supabase()
        if not cadastro_banco.empty:
            st.session_state.cadastro_oficinas = cadastro_banco
    except Exception:
        pass


# =========================================================
# CABEÇALHO E MENU
# =========================================================

st.title("🚛 Operações de Campo PS")
st.caption("Sistema de Gestão Operacional de Campo")

if MODO_BANCO:
    st.success(
        "Banco Supabase conectado — dados persistentes ativos.",
        icon="✅",
    )
else:
    st.warning(
        "Supabase não conectado. Configure SUPABASE_URL e "
        "SUPABASE_SERVICE_KEY nos Secrets do Streamlit.",
        icon="⚠️",
    )

st.divider()

with st.sidebar:
    st.header("Navegação")

    pagina = st.radio(
        "Escolha uma tela",
        [
            "📊 Painel de Controle",
            "📥 Importações",
            "🗂 Bases Salvas",
            "🔄 Conciliação",
            "🏢 Cadastro de Oficinas",
            "🏆 Ranking por Consultor",
            "📞 Follow",
        ],
    )

    st.divider()
    st.caption("Versão 0.7 — Supabase e painel regional")


# =========================================================
# IMPORTAÇÕES
# =========================================================

if pagina == "📥 Importações":
    st.subheader("Importação permanente das bases")

    if not MODO_BANCO:
        st.error(
            "Configure o Supabase antes de salvar as bases."
        )
        st.stop()

    aba_oficinas, aba_planejado, aba_resultado = st.tabs(
        [
            "🏢 Cadastro de oficinas",
            "📋 Planejado",
            "📈 Resultado",
        ]
    )

    with aba_oficinas:
        arquivo_cadastro = st.file_uploader(
            "Cadastro oficial ou consolidado",
            type=["ods", "xlsx", "csv"],
            key="cadastro_supabase",
        )

        if arquivo_cadastro is not None:
            cadastro_bruto = ler_cadastro_oficinas(
                arquivo_cadastro
            )
            cadastro = preparar_cadastro(cadastro_bruto)

            st.write(
                f"Oficinas identificadas: **{len(cadastro)}**"
            )
            st.dataframe(
                cadastro.head(20),
                use_container_width=True,
                hide_index=True,
            )

            if st.button(
                "💾 Salvar cadastro no Supabase",
                type="primary",
            ):
                try:
                    salvar_cadastro_supabase(cadastro)
                    st.session_state.cadastro_oficinas = (
                        carregar_cadastro_supabase()
                    )
                    st.success(
                        f"{len(cadastro)} oficinas salvas/atualizadas."
                    )
                except Exception as erro:
                    st.error(f"Erro ao salvar oficinas: {erro}")

    with aba_planejado:
        arquivo_planejado = st.file_uploader(
            "Arquivo planejado do OFS",
            type=["csv"],
            key="planejado_supabase",
        )

        if arquivo_planejado is not None:
            df_planejado = ler_csv_ofs(arquivo_planejado)
            data_detectada = detectar_data_base(df_planejado)

            data_planejado = st.date_input(
                "Data operacional do planejado",
                value=(
                    date.fromisoformat(data_detectada)
                    if data_detectada
                    else date.today()
                ),
                key="data_planejado",
            )

            st.info(
                f"{len(df_planejado)} registros serão salvos "
                f"para {data_planejado.strftime('%d/%m/%Y')}."
            )

            substituir = st.checkbox(
                "Confirmo que, se já existir uma base dessa data, "
                "ela será substituída.",
                key="confirmar_planejado",
            )

            if st.button(
                "💾 Salvar planejado",
                type="primary",
                disabled=not substituir,
            ):
                try:
                    salvar_base_supabase(
                        "planejado",
                        data_planejado.isoformat(),
                        arquivo_planejado.name,
                        df_planejado,
                    )
                    st.success("Planejado salvo com sucesso.")
                except Exception as erro:
                    st.error(f"Erro ao salvar planejado: {erro}")

    with aba_resultado:
        arquivo_resultado = st.file_uploader(
            "Arquivo de resultado do OFS",
            type=["csv"],
            key="resultado_supabase",
        )

        if arquivo_resultado is not None:
            df_resultado = ler_csv_ofs(arquivo_resultado)
            data_detectada = detectar_data_base(df_resultado)

            data_resultado = st.date_input(
                "Data operacional do resultado",
                value=(
                    date.fromisoformat(data_detectada)
                    if data_detectada
                    else date.today()
                ),
                key="data_resultado",
            )

            st.info(
                f"{len(df_resultado)} registros serão salvos "
                f"para {data_resultado.strftime('%d/%m/%Y')}."
            )

            substituir = st.checkbox(
                "Confirmo que, se já existir uma base dessa data, "
                "ela será substituída.",
                key="confirmar_resultado",
            )

            if st.button(
                "💾 Salvar resultado",
                type="primary",
                disabled=not substituir,
            ):
                try:
                    salvar_base_supabase(
                        "resultado",
                        data_resultado.isoformat(),
                        arquivo_resultado.name,
                        df_resultado,
                    )
                    st.success("Resultado salvo com sucesso.")
                except Exception as erro:
                    st.error(f"Erro ao salvar resultado: {erro}")


# =========================================================
# BASES SALVAS
# =========================================================

elif pagina == "🗂 Bases Salvas":
    if not MODO_BANCO:
        st.error("Supabase não conectado.")
        st.stop()

    st.subheader("Bases armazenadas no Supabase")

    bases = listar_bases_supabase()

    if bases.empty:
        st.info("Nenhuma base foi salva ainda.")
        st.stop()

    st.dataframe(
        bases,
        use_container_width=True,
        hide_index=True,
    )

    opcoes = [
        (
            f"{linha['data_operacional']} — "
            f"{linha['tipo']} — "
            f"{linha['quantidade_registros']} registros"
        )
        for _, linha in bases.iterrows()
    ]

    selecao = st.selectbox(
        "Escolha uma base para visualizar, baixar ou excluir",
        range(len(opcoes)),
        format_func=lambda indice: opcoes[indice],
    )

    registro = bases.iloc[selecao]
    tipo = registro["tipo"]
    data_operacional = registro["data_operacional"]

    base = carregar_base_supabase(
        tipo,
        data_operacional,
    )

    st.dataframe(
        base,
        use_container_width=True,
        hide_index=True,
        height=450,
    )

    col1, col2 = st.columns(2)

    col1.download_button(
        "⬇️ Baixar em Excel",
        data=dataframe_para_excel(
            base,
            tipo.capitalize(),
        ),
        file_name=(
            f"{tipo}_{data_operacional}.xlsx"
        ),
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        use_container_width=True,
    )

    confirmar_exclusao = col2.checkbox(
        "Confirmar exclusão permanente",
        key=f"excluir_{tipo}_{data_operacional}",
    )

    if col2.button(
        "🗑 Excluir base",
        disabled=not confirmar_exclusao,
        use_container_width=True,
    ):
        try:
            excluir_base_supabase(
                tipo,
                data_operacional,
            )
            st.success("Base excluída.")
            st.rerun()
        except Exception as erro:
            st.error(f"Erro ao excluir: {erro}")


# =========================================================
# PAINEL DE CONTROLE
# =========================================================

elif pagina == "📊 Painel de Controle":
    if not MODO_BANCO:
        st.error("Supabase não conectado.")
        st.stop()

    bases = listar_bases_supabase()

    if bases.empty:
        st.warning("Importe planejados e resultados.")
        st.stop()

    planejados = set(
        bases.loc[
            bases["tipo"] == "planejado",
            "data_operacional",
        ].astype(str)
    )
    resultados = set(
        bases.loc[
            bases["tipo"] == "resultado",
            "data_operacional",
        ].astype(str)
    )
    datas_completas = sorted(
        planejados.intersection(resultados),
        reverse=True,
    )

    if not datas_completas:
        st.warning(
            "Ainda não existe uma data com planejado e resultado."
        )
        st.stop()

    data_analisada = st.selectbox(
        "Data operacional analisada",
        datas_completas,
        format_func=lambda valor: pd.to_datetime(
            valor
        ).strftime("%d/%m/%Y"),
    )

    planejado = carregar_base_supabase(
        "planejado",
        data_analisada,
    )
    resultado = carregar_base_supabase(
        "resultado",
        data_analisada,
    )
    cadastro = st.session_state.cadastro_oficinas

    conciliacao = conciliar_bases(
        planejado,
        resultado,
    )

    if cadastro is not None and not cadastro.empty:
        conciliacao = enriquecer_com_cadastro(
            conciliacao,
            cadastro,
        )
    else:
        conciliacao["Consultor"] = (
            conciliacao["Estado"]
            .apply(padronizar_uf)
            .map(MAPA_CONSULTORES_UF)
            .fillna("Não definido")
        )

    indicadores = calcular_indicadores(conciliacao)

    st.markdown("## Painel geral")
    c1, c2, c3, c4, c5, c6 = st.columns(6)

    c1.metric("Planejadas", indicadores["planejadas"])
    c2.metric(
        "Executadas planejadas",
        indicadores["executadas_planejadas"],
        formatar_percentual(
            indicadores["indice_execucao"]
        ),
    )
    c3.metric(
        "Improdutivas",
        indicadores["improdutivas"],
        formatar_percentual(
            indicadores["indice_improdutividade"]
        ),
        delta_color="inverse",
    )
    c4.metric(
        "Canceladas",
        indicadores["canceladas"],
        formatar_percentual(
            indicadores["indice_cancelamento"]
        ),
        delta_color="inverse",
    )
    c5.metric(
        "No-show",
        indicadores["no_show"],
        formatar_percentual(
            indicadores["indice_no_show"]
        ),
        delta_color="inverse",
    )
    c6.metric(
        "Executadas extras",
        indicadores["executadas_extras"],
    )

    st.markdown("### Indicadores MCI e MD")
    i1, i2, i3 = st.columns(3)

    i1.metric(
        "MCI — Execução do planejado",
        formatar_percentual(
            indicadores["indice_execucao"]
        ),
        delta=formatar_percentual(
            indicadores["indice_execucao"] - META_MCI
        ),
        help="Executadas planejadas ÷ Planejadas.",
    )
    i2.metric(
        "MD — Improdutividade",
        formatar_percentual(
            indicadores["indice_improdutividade"]
        ),
        delta=formatar_percentual(
            META_IMPRODUTIVIDADE
            - indicadores["indice_improdutividade"]
        ),
        help="Improdutivas ÷ Planejadas.",
    )
    i3.metric(
        "Execução total com extras",
        formatar_percentual(
            indicadores["indice_execucao_total"]
        ),
    )

    if indicadores["indice_improdutividade"] <= META_IMPRODUTIVIDADE:
        st.success("Improdutividade dentro da meta de 10%.")
    else:
        st.warning("Improdutividade acima da meta de 10%.")

    st.divider()
    st.markdown("## Indicadores por consultor e região")

    consultores_disponiveis = sorted(
        conciliacao["Consultor"]
        .fillna("Não definido")
        .unique()
        .tolist()
    )

    consultor = st.selectbox(
        "Selecione o consultor",
        consultores_disponiveis,
    )

    regional = conciliacao[
        conciliacao["Consultor"] == consultor
    ].copy()

    indicadores_regionais = calcular_indicadores(
        regional
    )

    st.caption(
        f"Região: {REGIOES_CONSULTORES.get(consultor, 'Não definida')}"
    )

    r1, r2, r3, r4, r5, r6 = st.columns(6)

    r1.metric(
        "Planejadas",
        indicadores_regionais["planejadas"],
    )
    r2.metric(
        "Executadas",
        indicadores_regionais[
            "executadas_planejadas"
        ],
    )
    r3.metric(
        "Improdutivas",
        indicadores_regionais["improdutivas"],
    )
    r4.metric(
        "Canceladas",
        indicadores_regionais["canceladas"],
    )
    r5.metric(
        "No-show",
        indicadores_regionais["no_show"],
    )
    r6.metric(
        "Extras",
        indicadores_regionais["executadas_extras"],
    )

    ri1, ri2, ri3 = st.columns(3)
    ri1.metric(
        "MCI regional",
        formatar_percentual(
            indicadores_regionais["indice_execucao"]
        ),
    )
    ri2.metric(
        "MD regional",
        formatar_percentual(
            indicadores_regionais[
                "indice_improdutividade"
            ]
        ),
    )
    ri3.metric(
        "Execução total regional",
        formatar_percentual(
            indicadores_regionais[
                "indice_execucao_total"
            ]
        ),
    )

    st.divider()
    esquerda, direita = st.columns(2)

    with esquerda:
        resumo = (
            conciliacao["Classificação"]
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
            title="Classificação geral",
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
        resumo_consultor = (
            regional["Classificação"]
            .value_counts()
            .reset_index()
        )
        resumo_consultor.columns = [
            "Classificação",
            "Quantidade",
        ]

        grafico_regional = px.bar(
            resumo_consultor,
            x="Quantidade",
            y="Classificação",
            orientation="h",
            text="Quantidade",
            title=f"Classificação — {consultor}",
        )
        grafico_regional.update_layout(
            showlegend=False,
            height=480,
        )
        st.plotly_chart(
            grafico_regional,
            use_container_width=True,
        )


# =========================================================
# CONCILIAÇÃO
# =========================================================

elif pagina == "🔄 Conciliação":
    if not MODO_BANCO:
        st.error("Supabase não conectado.")
        st.stop()

    bases = listar_bases_supabase()
    planejados = set(
        bases.loc[
            bases["tipo"] == "planejado",
            "data_operacional",
        ].astype(str)
    )
    resultados = set(
        bases.loc[
            bases["tipo"] == "resultado",
            "data_operacional",
        ].astype(str)
    )
    datas = sorted(
        planejados.intersection(resultados),
        reverse=True,
    )

    if not datas:
        st.warning(
            "Não há data completa para conciliação."
        )
        st.stop()

    data_escolhida = st.selectbox(
        "Data",
        datas,
        format_func=lambda valor: pd.to_datetime(
            valor
        ).strftime("%d/%m/%Y"),
        key="data_conciliacao",
    )

    conciliacao = conciliar_bases(
        carregar_base_supabase(
            "planejado",
            data_escolhida,
        ),
        carregar_base_supabase(
            "resultado",
            data_escolhida,
        ),
    )

    classificacoes = sorted(
        conciliacao["Classificação"]
        .unique()
        .tolist()
    )
    filtro = st.multiselect(
        "Classificação",
        classificacoes,
        default=classificacoes,
    )
    somente_troca = st.checkbox(
        "Somente troca de OS"
    )

    tabela = conciliacao[
        conciliacao["Classificação"].isin(filtro)
    ].copy()

    if somente_troca:
        tabela = tabela[
            tabela["Troca de OS"] == "Sim"
        ]

    st.dataframe(
        tabela,
        use_container_width=True,
        hide_index=True,
        height=600,
    )

    st.download_button(
        "⬇️ Baixar conciliação",
        data=dataframe_para_excel(
            tabela,
            "Conciliacao",
        ),
        file_name=f"conciliacao_{data_escolhida}.xlsx",
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
    )


# =========================================================
# CADASTRO DE OFICINAS
# =========================================================

elif pagina == "🏢 Cadastro de Oficinas":
    cadastro = st.session_state.cadastro_oficinas

    if cadastro is None or cadastro.empty:
        st.warning(
            "Importe o cadastro das oficinas."
        )
        st.stop()

    st.subheader("Cadastro mestre de oficinas")

    pesquisa = st.text_input("Pesquisar oficina")
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
                options=["Alta", "Normal", "Baixa"],
            ),
            "Ativa": st.column_config.CheckboxColumn(
                "Ativa"
            ),
        },
        disabled=[
            "Chave Oficina",
            "Consultor automático",
        ],
    )

    if MODO_BANCO and st.button(
        "💾 Salvar alterações no Supabase",
        type="primary",
    ):
        try:
            cadastro_editado["Chave Oficina"] = (
                cadastro_editado["Oficina"]
                .apply(normalizar_texto)
            )
            salvar_cadastro_supabase(
                cadastro_editado
            )
            st.session_state.cadastro_oficinas = (
                carregar_cadastro_supabase()
            )
            st.success("Cadastro atualizado.")
        except Exception as erro:
            st.error(f"Erro ao salvar: {erro}")


# =========================================================
# RANKING
# =========================================================

elif pagina == "🏆 Ranking por Consultor":
    if not MODO_BANCO:
        st.error("Supabase não conectado.")
        st.stop()

    cadastro = st.session_state.cadastro_oficinas
    bases = listar_bases_supabase()
    datas = sorted(
        bases.loc[
            bases["tipo"] == "planejado",
            "data_operacional",
        ].astype(str).unique(),
        reverse=True,
    )

    if cadastro is None or cadastro.empty or not datas:
        st.warning(
            "É necessário ter cadastro e planejado salvos."
        )
        st.stop()

    data_planejada = st.selectbox(
        "Data do planejado",
        datas,
        format_func=lambda valor: pd.to_datetime(
            valor
        ).strftime("%d/%m/%Y"),
    )

    base = enriquecer_com_cadastro(
        carregar_base_supabase(
            "planejado",
            data_planejada,
        ),
        cadastro,
    )

    consultores = sorted(
        base["Consultor"].unique().tolist()
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
# FOLLOW
# =========================================================

elif pagina == "📞 Follow":
    if not MODO_BANCO:
        st.error("Supabase não conectado.")
        st.stop()

    cadastro = st.session_state.cadastro_oficinas
    bases = listar_bases_supabase()
    datas = sorted(
        bases.loc[
            bases["tipo"] == "planejado",
            "data_operacional",
        ].astype(str).unique(),
        reverse=True,
    )

    if cadastro is None or cadastro.empty or not datas:
        st.warning(
            "É necessário ter cadastro e planejado salvos."
        )
        st.stop()

    data_planejada = st.selectbox(
        "Data do follow",
        datas,
        format_func=lambda valor: pd.to_datetime(
            valor
        ).strftime("%d/%m/%Y"),
    )

    base = enriquecer_com_cadastro(
        carregar_base_supabase(
            "planejado",
            data_planejada,
        ),
        cadastro,
    )
    base = base[
        base["Oficina"].apply(texto_limpo) != ""
    ]

    consultores = sorted(
        base["Consultor"].unique().tolist()
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
                f"programado(s) para "
                f"{pd.to_datetime(data_planejada).strftime('%d/%m/%Y')}. "
                f"Existe algum impedimento para a execução? "
                f"Caso exista, informe para que possamos atuar "
                f"preventivamente."
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
