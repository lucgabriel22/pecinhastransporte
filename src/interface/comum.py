"""Formatação e tratamento de ações compartilhados entre as telas."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable

import streamlit as st

from src.dominio import ErroDominio, ErroInfraestrutura


def executar(acao: Callable, *args: Any, **kwargs: Any) -> tuple[bool, Any]:
    """Apresenta falhas previstas sem anunciar uma operação como concluída."""
    try:
        return True, acao(*args, **kwargs)
    except ErroDominio as erro:
        st.warning(str(erro))
    except ErroInfraestrutura as erro:
        st.error(str(erro))
        st.caption("Confira os serviços locais e a configuração de conexão. A ação pode ser repetida com a mesma identificação.")
    return False, None


def objeto_json(texto: str, campo: str) -> dict:
    try:
        valor = json.loads(texto)
    except json.JSONDecodeError as erro:
        raise ErroDominio(f"{campo}: JSON inválido na linha {erro.lineno}, coluna {erro.colno}.") from erro
    if not isinstance(valor, dict):
        raise ErroDominio(f"{campo} deve ser um objeto JSON, entre {{ e }}.")
    return valor


def json_legivel(valor: Any) -> str:
    return json.dumps(valor, ensure_ascii=False, indent=2, default=str)


def horario(valor: Any) -> str:
    if not valor:
        return "Sem informação"
    if isinstance(valor, str):
        try:
            valor = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        except ValueError:
            return valor
    if isinstance(valor, datetime):
        # O processo é local no Windows; astimezone usa o fuso da máquina.
        return valor.astimezone().strftime("%d/%m/%Y %H:%M:%S %Z")
    return str(valor)


def numero(valor: float | int, casas: int = 1) -> str:
    return f"{valor:,.{casas}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def opcoes_locais(malha: dict) -> dict[str, str]:
    return {local["id"]: local["nome"] for local in malha["locais"]}


def assinatura_percurso(percurso: dict | None) -> tuple:
    if not percurso:
        return ()
    return (
        tuple((trecho["id"], float(trecho["distancia_km"])) for trecho in percurso["trechos"]),
        float(percurso["distancia_total_km"]),
    )


def assinatura_malha(malha: dict) -> str:
    """Invalida uma prévia quando a malha consultada muda."""
    return json.dumps(malha, ensure_ascii=False, sort_keys=True, default=str)


def exibir_percurso(percurso: dict | None, titulo: str) -> None:
    st.markdown(f"**{titulo}**")
    if not percurso:
        st.warning("Nenhum percurso disponível para essa seleção.")
        return
    st.metric("Distância total", f"{numero(percurso['distancia_total_km'])} km")
    st.write(" → ".join(local["nome"] for local in percurso["locais"]))
    st.caption(f"{len(percurso['trechos'])} trecho(s): " + " → ".join(t["id"] for t in percurso["trechos"]))


def exibir_avisos(resultado: dict) -> None:
    for aviso in resultado.get("avisos", []):
        st.warning(str(aviso))
