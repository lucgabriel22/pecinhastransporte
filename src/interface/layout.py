"""Identidade PecinhasTransportes e navegação das quatro áreas do trabalho."""

from html import escape
from pathlib import Path

import streamlit as st


TELAS = ("Inventário e lotes", "Torre de controle", "Otimizador de rotas", "Despacho e recebimento")
CONTEXTOS = {
    "Inventário e lotes": ("01", "GESTÃO DE ESTOQUE"),
    "Torre de controle": ("02", "MONITORAMENTO DA FROTA"),
    "Otimizador de rotas": ("03", "INTELIGÊNCIA LOGÍSTICA"),
    "Despacho e recebimento": ("04", "CONTROLE DE EXPEDIÇÃO"),
}
MARCA = """<svg viewBox="0 0 40 40" fill="none" aria-hidden="true">
<rect x="1" y="1" width="38" height="38" rx="11" fill="#FFB45B"/>
<path d="M11 13.5 20 9l9 4.5v12L20 31l-9-5.5v-12Z" stroke="#102F46" stroke-width="2" stroke-linejoin="round"/>
<path d="m11 13.5 9 5 9-5M20 18.5V31m-4.5-19.7 9 5" stroke="#102F46" stroke-width="2" stroke-linejoin="round"/>
</svg>"""


def preparar_layout() -> str:
    st.set_page_config(page_title="PecinhasTransportes · Central de operações", page_icon="📦", layout="wide")
    estilos = Path(__file__).with_name("estilos.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{estilos}</style>", unsafe_allow_html=True)
    with st.sidebar:
        st.markdown(
            f'<div class="pt-marca">{MARCA}<div class="pt-wordmark">Pecinhas<span>Transportes</span>'
            '<small>CENTRAL DE OPERAÇÕES</small></div></div>', unsafe_allow_html=True,
        )
        st.markdown('<div class="pt-menu-label">ESPAÇO DE TRABALHO</div>', unsafe_allow_html=True)
        tela = st.radio("Áreas do sistema", TELAS, label_visibility="collapsed", key="pt_navegacao")
        st.markdown(
            '<div class="pt-sidebar-nota"><span class="pt-mini-label">AMBIENTE DE DEMONSTRAÇÃO</span>'
            '<strong>Uma operação conectada.</strong><p>Estoque, frota e percursos no mesmo lugar.</p>'
            '<span class="pt-demo-rodape">Estudo de caso 04 · Dados fictícios</span></div>', unsafe_allow_html=True,
        )
    return tela


def cabecalho(titulo: str, descricao: str) -> None:
    numero, contexto = CONTEXTOS.get(titulo, ("", "CENTRAL DE OPERAÇÕES"))
    with st.container(key="pt_cabecalho"):
        st.markdown(f'<div class="pt-eyebrow"><span>{escape(numero)}</span>{escape(contexto)}</div>', unsafe_allow_html=True)
        st.title(titulo)
        st.markdown(f'<p class="pt-descricao">{escape(descricao)}</p>', unsafe_allow_html=True)


def titulo_secao(titulo: str, descricao: str = "", etiqueta: str = "") -> None:
    complemento = f'<span class="pt-section-tag">{escape(etiqueta)}</span>' if etiqueta else ""
    detalhe = f'<p>{escape(descricao)}</p>' if descricao else ""
    st.markdown(
        f'<div class="pt-section-heading"><div><h3>{escape(titulo)}</h3>{detalhe}</div>{complemento}</div>', unsafe_allow_html=True,
    )


def vazio(titulo: str, descricao: str) -> None:
    st.markdown(
        f'<div class="pt-empty-state"><span aria-hidden="true">◌</span><strong>{escape(titulo)}</strong>'
        f'<p>{escape(descricao)}</p></div>', unsafe_allow_html=True,
    )


def saude_bancos(sistema) -> bool:
    estados = sistema.verificar_conexoes()
    todos_ok = all(estado["ok"] for estado in estados)
    online = sum(bool(estado["ok"]) for estado in estados)
    classe = "online" if todos_ok else "atencao"
    mensagem = "Serviços conectados" if todos_ok else "Verifique as conexões"
    st.markdown(
        '<div class="pt-topbar"><div class="pt-breadcrumb">PecinhasTransportes<span>/</span>'
        '<strong>Central de operações</strong></div><div class="pt-topbar-right">'
        f'<span class="pt-ambiente">DEMONSTRAÇÃO</span><span class="pt-status pt-status-{classe}">'
        f'<i></i>{escape(mensagem)}</span></div></div>', unsafe_allow_html=True,
    )
    with st.sidebar:
        with st.expander("Conexões dos bancos", expanded=not todos_ok):
            for estado in estados:
                situacao = "Conectado" if estado["ok"] else "Indisponível"
                cor = "ok" if estado["ok"] else "erro"
                st.markdown(
                    f'<div class="pt-conexao"><span>{escape(estado["banco"])}</span>'
                    f'<small class="pt-conexao-{cor}">{situacao}</small></div>', unsafe_allow_html=True,
                )
            st.caption(f"{online} de {len(estados)} serviços disponíveis · Ambiente local")
    if not todos_ok:
        st.error("Alguns serviços estão indisponíveis. Confira as conexões no menu lateral.")
        st.info("Inicie os serviços locais pelo procedimento do README e confirme a configuração no arquivo .env.")
        st.code(".\\scripts\\iniciar.ps1", language="powershell")
    return todos_ok
