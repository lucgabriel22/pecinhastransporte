"""Consulta e cadastro dos documentos de mercadorias e lotes."""

import streamlit as st

from src.interface.comum import executar, objeto_json, opcoes_locais
from src.interface.layout import cabecalho, titulo_secao, vazio


def renderizar(sistema) -> None:
    cabecalho("Inventário e lotes", "Consulte saldos por local e organize a documentação das mercadorias.")
    mensagem = st.session_state.pop("mensagem_inventario", None)
    if mensagem:
        st.success(mensagem)
    mercadorias = sistema.listar_mercadorias()
    lotes = sistema.listar_lotes()
    malha = sistema.obter_malha()
    nomes_mercadorias = {m["_id"]: m["descricao"] for m in mercadorias}
    nomes_locais = opcoes_locais(malha)
    a, b, c = st.columns(3)
    a.metric("Mercadorias", len(mercadorias))
    b.metric("Lotes cadastrados", len(lotes))
    c.metric("Locais na malha", len(malha["locais"]))
    titulo_secao("Controle do inventário", "Consulte os saldos e mantenha os cadastros da operação.", f"{len(lotes)} lotes")
    consulta, cadastro_mercadoria, cadastro_lote = st.tabs(["Consultar inventário", "Nova mercadoria", "Novo lote"])
    with consulta:
        busca_coluna, local_coluna = st.columns([2, 1])
        busca = busca_coluna.text_input("Buscar no inventário", placeholder="Lote ou descrição da mercadoria", key="inventario_busca").strip().casefold()
        local_filtro = local_coluna.selectbox("Filtrar por local", [None, *nomes_locais], format_func=lambda v: "Todos os locais" if v is None else nomes_locais[v])
        linhas = [
            {"Lote": lote["_id"], "Mercadoria": nomes_mercadorias.get(lote["mercadoria_id"], lote["mercadoria_id"]),
             "Saldo": lote["quantidade"], "Unidade": lote["unidade"], "Local": nomes_locais.get(lote["local_id"], lote["local_id"])}
            for lote in lotes
            if (local_filtro is None or lote["local_id"] == local_filtro)
            and (not busca or busca in f"{lote['_id']} {nomes_mercadorias.get(lote['mercadoria_id'], '')}".casefold())
        ]
        if linhas:
            st.dataframe(linhas, hide_index=True, width="stretch", column_config={
                "Lote": st.column_config.TextColumn(width="medium"),
                "Mercadoria": st.column_config.TextColumn(width="large"),
                "Saldo": st.column_config.NumberColumn(format="%d", width="small"),
            })
            st.caption(f"{len(linhas)} de {len(lotes)} lotes exibidos")
        else:
            vazio("Nenhum lote encontrado", "Ajuste a busca ou o local selecionado para consultar outros registros.")
        st.caption("O saldo da origem baixa na confirmação do despacho. O recebimento integral não executa uma segunda baixa.")
        if mercadorias:
            with st.expander("Consultar especificações técnicas e fiscais"):
                id_mercadoria = st.selectbox("Mercadoria", list(nomes_mercadorias), format_func=lambda v: f"{nomes_mercadorias[v]} · {v}", key="inventario_documento")
                st.json(next(m for m in mercadorias if m["_id"] == id_mercadoria))
    with cadastro_mercadoria:
        titulo_secao("Nova mercadoria", "Defina a descrição e organize as especificações em JSON.")
        st.caption("Cadastros desta aplicação são de demonstração. Os campos fiscais são livres; não há cálculo de tributos nem emissão fiscal.")
        with st.form("cadastrar_mercadoria", clear_on_submit=False):
            descricao = st.text_input("Descrição da mercadoria", max_chars=200)
            esquerda, direita = st.columns(2)
            tecnico = esquerda.text_area("Especificações técnicas em JSON", value="{}", height=160)
            fiscal = direita.text_area("Especificações fiscais em JSON", value="{}", height=160)
            salvar = st.form_submit_button("Cadastrar mercadoria", type="primary")
        if salvar:
            ok, resultado = executar(lambda: sistema.cadastrar_mercadoria(descricao, objeto_json(tecnico, "Especificações técnicas"), objeto_json(fiscal, "Especificações fiscais")))
            if ok:
                st.session_state["mensagem_inventario"] = f"Mercadoria cadastrada: {resultado}"
                st.rerun()
    with cadastro_lote:
        titulo_secao("Novo lote de estoque", "Relacione a mercadoria, a quantidade e o local de armazenamento.")
        if not mercadorias or not nomes_locais:
            st.info("Cadastre uma mercadoria e inicialize a malha antes de cadastrar lotes.")
            return
        with st.form("cadastrar_lote", clear_on_submit=False):
            mercadoria_id = st.selectbox("Mercadoria do lote", list(nomes_mercadorias), format_func=lambda v: f"{nomes_mercadorias[v]} · {v}")
            a, b, c = st.columns(3)
            quantidade = a.number_input("Quantidade inteira", min_value=1, value=10, step=1)
            unidade = b.text_input("Unidade de contagem", value="unidade", max_chars=40)
            local_id = c.selectbox("Local do estoque", list(nomes_locais), format_func=nomes_locais.get)
            salvar = st.form_submit_button("Cadastrar lote", type="primary")
        if salvar:
            ok, resultado = executar(sistema.cadastrar_lote, mercadoria_id, int(quantidade), unidade, local_id)
            if ok:
                st.session_state["mensagem_inventario"] = f"Lote cadastrado: {resultado}"
                st.rerun()
