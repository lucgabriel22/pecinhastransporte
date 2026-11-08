"""Entrada do aplicativo: streamlit run app.py."""

import logging

import streamlit as st

from src.bootstrap import criar_sistema
from src.dominio import ErroDominio, ErroInfraestrutura
from src.interface import expedicao, inventario, rotas, torre
from src.interface.layout import preparar_layout, saude_bancos


LOGGER = logging.getLogger(__name__)


@st.cache_resource(show_spinner="Conectando aos serviços locais…")
def obter_sistema():
    return criar_sistema()


def principal() -> None:
    tela = preparar_layout()
    try:
        try:
            sistema = obter_sistema()
        except ValueError:
            st.error("A configuração local precisa ser preparada ou corrigida. Execute o configurador e revise os valores do arquivo .env.")
            st.code(".\\scripts\\configurar.ps1", language="powershell")
            return
        saude_bancos(sistema)
        paginas = {
            "Inventário e lotes": inventario.renderizar,
            "Torre de controle": torre.renderizar,
            "Otimizador de rotas": rotas.renderizar,
            "Despacho e recebimento": expedicao.renderizar,
        }
        paginas[tela](sistema)
    except ErroDominio as erro:
        st.warning(str(erro))
    except ErroInfraestrutura as erro:
        st.error(str(erro))
        st.info("Os dados não puderam ser confirmados nos bancos. Inicie os serviços locais e verifique a configuração no arquivo .env.")
        st.code(".\\scripts\\iniciar.ps1", language="powershell")
    except Exception:
        LOGGER.exception("Falha inesperada ao renderizar a interface")
        st.error("Não foi possível concluir esta ação. Consulte o registro do aplicativo para identificar a falha.")


if __name__ == "__main__":
    principal()
