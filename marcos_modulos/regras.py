
"""
Regras operacionais - Integracao OFS
Gestao de Oficinas + Painel Marcos

Modulo independente.
Nao altera MCI, MD ou dados do Supabase.
"""

import re
import unicodedata


def normalizar_texto(valor):
    if valor is None:
        return ""
    texto = str(valor).strip().lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(
        c for c in texto
        if not unicodedata.combining(c)
    )
    return re.sub(r"\s+", " ", texto)


def familia_servico(tipo):
    texto = normalizar_texto(tipo)

    if not texto:
        return "Nao informado"

    if "reinstal" in texto:
        return "Reinstalacao"
    if "instal" in texto:
        return "Instalacao"
    if "manut" in texto:
        return "Manutencao"
    if "renov" in texto:
        return "Renovacao"
    if "retir" in texto or "desinstal" in texto:
        return "Retirada"
    if "upgrade" in texto or "atualiz" in texto:
        return "Upgrade"

    return "Outros"


def classificar_resultado(status):
    texto = normalizar_texto(status)

    if not texto:
        return "Sem resultado"

    if "nao conclu" in texto:
        return "Nao concluida"
    if "cancel" in texto:
        return "Cancelada"
    if "conclu" in texto or "finaliz" in texto:
        return "Concluida"
    if "suspens" in texto:
        return "Suspensa"
    if "iniciad" in texto:
        return "Iniciada"
    if "pendent" in texto:
        return "Pendente"

    return "Outros"


def classificar_agendamento(
    consta_planejado,
    consta_resultado,
    status_resultado=None,
):
    """
    Classificacao preliminar.
    Nao comprova aceite nem perda definitiva.
    """
    if consta_planejado:
        if not consta_resultado:
            return "Sem resultado - verificar"

        return (
            "Programada - "
            + classificar_resultado(status_resultado)
        )

    if consta_resultado:
        return (
            "Extra - "
            + classificar_resultado(status_resultado)
        )

    return "Sem evidencia operacional"
