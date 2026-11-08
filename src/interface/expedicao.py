"""Despacho idempotente e confirmação do recebimento integral."""

from uuid import uuid4

import streamlit as st

from src.dominio import ErroDominio, ErroInfraestrutura
from src.interface.comum import (
    assinatura_malha, executar, exibir_avisos, exibir_percurso, horario,
    json_legivel, objeto_json, opcoes_locais,
)
from src.interface.grafo import desenhar_malha
from src.interface.layout import cabecalho, vazio
from src.interface.rotas import selecionar_parametros


def _confirmar_despacho(sistema, dados: dict) -> None:
    # O snapshot permanece na sessão em caso de falha, inclusive de conexão.
    # Repetir a confirmação reutiliza o mesmo manifesto e os mesmos argumentos.
    st.session_state["despacho_pendente"] = dados
    try:
        resultado = sistema.despachar(**dados)
    except ErroDominio as erro:
        # O serviço só lança erro de domínio após garantir que a transação
        # não confirmou efeitos; falhas com resultado incerto são de infraestrutura.
        st.session_state.pop("despacho_pendente", None)
        st.session_state.pop("preparacao_despacho", None)
        st.session_state.pop("despacho_id", None)
        st.warning(str(erro))
        st.info("Revise a carga e confira novamente o percurso antes de confirmar.")
    except ErroInfraestrutura as erro:
        st.error(str(erro))
        st.info("A tentativa foi preservada. Repita a mesma confirmação para recuperar o resultado com segurança.")
    else:
        st.session_state["despacho_dados_confirmados"] = dados
        st.session_state["despacho_concluido"] = resultado
        st.session_state.pop("despacho_pendente", None)
        st.rerun()


def _novo_despacho(sistema) -> None:
    concluido = st.session_state.get("despacho_concluido")
    if concluido:
        st.success(f"Despacho confirmado: {concluido['_id']}")
        st.write("O estoque da origem foi baixado no despacho.")
        if concluido["status"] == "RECEBIDO":
            st.info("Esta carga já teve o recebimento integral registrado.")
        else:
            st.write("O veículo permanece indisponível durante o transporte.")
        exibir_avisos(concluido)
        with st.expander("Manifesto confirmado"):
            st.json(concluido)
        if concluido.get("sincronizacao_redis") == "PENDENTE":
            if st.button("Repetir sincronização deste despacho", type="primary"):
                _confirmar_despacho(sistema, st.session_state["despacho_dados_confirmados"])
            return
        if st.button("Preparar outro despacho", type="primary"):
            for chave in ("despacho_concluido", "despacho_id", "preparacao_despacho", "despacho_dados_confirmados"):
                st.session_state.pop(chave, None)
            for chave in list(st.session_state):
                if chave.startswith("carga_quantidade_") or chave == "carga_lotes_selecionados":
                    del st.session_state[chave]
            st.rerun()
        return
    pendente = st.session_state.get("despacho_pendente")
    if pendente:
        st.warning("A confirmação anterior não foi concluída na interface. Repita a mesma operação para consultar ou recuperar seu resultado.")
        st.write(f"Manifesto: **{pendente['manifesto_id']}** · Veículo: **{pendente['veiculo_id']}**")
        st.json({"origem_id": pendente["origem_id"], "destino_id": pendente["destino_id"], "itens": pendente["itens"], "documentacao_carga": pendente["documentacao_carga"]})
        if st.button("Repetir confirmação do mesmo despacho", type="primary"):
            _confirmar_despacho(sistema, pendente)
        st.caption("A identificação foi preservada para impedir uma segunda baixa de estoque. Os dados dessa tentativa permanecem fixos até a recuperação.")
        return
    malha = sistema.obter_malha()
    parametros = selecionar_parametros(malha, "despacho")
    if parametros is None:
        return
    if st.button("Conferir percurso para despacho", type="primary"):
        ok, calculo = executar(sistema.calcular_rotas, **parametros)
        if ok:
            st.session_state["preparacao_despacho"] = {"parametros": parametros, "malha": assinatura_malha(malha), "percurso": calculo["menor_distancia"]}
    previa = st.session_state.get("preparacao_despacho")
    if not previa or previa["parametros"] != parametros or previa["malha"] != assinatura_malha(malha):
        st.info("Confira o percurso da seleção atual antes de preparar a carga.")
        return
    percurso = previa["percurso"]
    if not percurso:
        st.warning("Não há percurso viável. Ajuste os bloqueios, a origem ou o destino.")
        return
    st.image(desenhar_malha(malha, percurso, parametros["trechos_bloqueados"], parametros["locais_bloqueados"]), width="stretch")
    exibir_percurso(percurso, "Percurso completo que será confirmado")
    st.caption("A confirmação verifica novamente a malha. Se o percurso mudar, o despacho é recusado para que você revise a seleção.")
    lotes = [l for l in sistema.listar_lotes() if l["local_id"] == parametros["origem_id"] and l["quantidade"] > 0]
    veiculos = [v for v in sistema.listar_veiculos() if v["disponibilidade"] == "DISPONIVEL"]
    mercadorias = {m["_id"]: m["descricao"] for m in sistema.listar_mercadorias()}
    if not lotes:
        st.info("Nenhum lote com saldo disponível nessa origem.")
        return
    if not veiculos:
        st.info("Nenhum veículo disponível. Confirme o recebimento de uma carga em transporte antes de um novo despacho.")
        return
    por_lote = {l["_id"]: l for l in lotes}
    por_veiculo = {v["id"]: v for v in veiculos}
    selecionados = st.multiselect("Lotes que compõem a carga", list(por_lote), format_func=lambda v: f"{v} · {mercadorias.get(por_lote[v]['mercadoria_id'], por_lote[v]['mercadoria_id'])} · saldo {por_lote[v]['quantidade']} {por_lote[v]['unidade']}", key="carga_lotes_selecionados")
    st.session_state.setdefault("despacho_id", f"DEMO-MAN-{uuid4().hex[:16].upper()}")
    manifesto_id = st.session_state["despacho_id"]
    st.caption(f"Identificação desta operação: {manifesto_id}")
    with st.form("confirmar_despacho"):
        veiculo_id = st.selectbox("Veículo disponível", list(por_veiculo), format_func=lambda v: f"{por_veiculo[v]['nome']} · {v}")
        itens = []
        for lote_id in selecionados:
            lote = por_lote[lote_id]
            quantidade = st.number_input(f"Quantidade de {lote_id} · saldo {lote['quantidade']} {lote['unidade']}", min_value=0, value=0, step=1, key=f"carga_quantidade_{parametros['origem_id']}_{lote_id}")
            if quantidade > 0:
                itens.append({"lote_id": lote_id, "quantidade": int(quantidade)})
        documentacao = st.text_area("Documentação da carga em JSON", value="{}", height=140, help="Objeto livre de demonstração. Não há emissão de documento fiscal.")
        confirmar = st.checkbox("Confirmo o despacho e a baixa das quantidades no estoque da origem.")
        enviar = st.form_submit_button("Confirmar despacho", type="primary", disabled=not selecionados)
    if enviar:
        if not confirmar:
            st.warning("Marque a confirmação do despacho antes de continuar.")
            return
        if not itens:
            st.warning("Informe uma quantidade positiva para pelo menos um lote.")
            return
        if any(item["quantidade"] > por_lote[item["lote_id"]]["quantidade"] for item in itens):
            st.warning("Uma quantidade informada excede o saldo disponível do lote. Revise a carga.")
            return
        ok, documento = executar(objeto_json, documentacao, "Documentação da carga")
        if ok:
            dados = {**parametros, "manifesto_id": manifesto_id, "veiculo_id": veiculo_id, "itens": itens, "documentacao_carga": documento, "percurso_esperado": percurso}
            _confirmar_despacho(sistema, dados)


def _recebimento(sistema) -> None:
    if st.button("Atualizar manifestos"):
        st.rerun()
    manifestos = sistema.listar_manifestos()
    if not manifestos:
        vazio("Nenhuma expedição registrada", "Os manifestos aparecerão aqui após a confirmação de um despacho.")
        return
    nomes = opcoes_locais(sistema.obter_malha())
    st.dataframe([
        {"Manifesto": m["_id"], "Estado": m["status"], "Veículo": m["veiculo_id"], "Origem": nomes.get(m["origem_id"], m["origem_id"]), "Destino": nomes.get(m["destino_id"], m["destino_id"]), "Distância (km)": m.get("percurso", {}).get("distancia_total_km"), "Despacho": horario(m.get("despacho", {}).get("confirmado_em")), "Redis": m.get("sincronizacao_redis", "—")}
        for m in manifestos
    ], hide_index=True, width="stretch")
    por_id = {m["_id"]: m for m in manifestos}
    manifesto_id = st.selectbox("Manifesto para conferência", list(por_id), format_func=lambda v: f"{v} · {por_id[v]['status']}")
    manifesto = por_id[manifesto_id]
    st.write(f"**{nomes.get(manifesto['origem_id'], manifesto['origem_id'])} → {nomes.get(manifesto['destino_id'], manifesto['destino_id'])}**")
    st.dataframe(manifesto["itens"], hide_index=True, width="stretch")
    st.caption("O recebimento confirma todos os itens e quantidades do manifesto. A baixa da origem já foi realizada no despacho.")
    if manifesto["status"] == "DESPACHADO":
        if manifesto.get("sincronizacao_redis") == "PENDENTE":
            st.warning("O despacho está confirmado; a associação do veículo com o Redis aguarda sincronização.")
            if st.button("Sincronizar disponibilidade deste despacho"):
                ok, resultado = executar(sistema.sincronizar_despacho, manifesto_id)
                if ok:
                    manifesto = resultado
                    exibir_avisos(resultado)
                    if resultado.get("sincronizacao_redis") == "SINCRONIZADO":
                        st.success("Disponibilidade sincronizada. O veículo permanece vinculado a esta carga em transporte.")
                    else:
                        st.warning("A sincronização continua pendente. Confira a conexão e o estado do veículo antes de repetir.")
                    concluido = st.session_state.get("despacho_concluido")
                    if concluido and concluido["_id"] == manifesto_id:
                        st.session_state["despacho_concluido"] = resultado
        with st.form(f"receber_{manifesto_id}"):
            confirmado = st.checkbox("Confirmo o recebimento integral de todos os itens desta carga.")
            receber = st.form_submit_button("Confirmar recebimento integral", type="primary")
        if receber:
            if not confirmado:
                st.warning("Marque a confirmação do recebimento integral antes de continuar.")
            else:
                ok, resultado = executar(sistema.receber, manifesto_id)
                if ok:
                    st.success("Recebimento integral registrado.")
                    exibir_avisos(resultado)
                    if resultado.get("sincronizacao_redis") == "PENDENTE":
                        st.warning("O recebimento foi salvo. A liberação do veículo aguarda sincronização com o Redis; atualize esta consulta para repetir a sincronização.")
                    else:
                        st.success("Sincronização da disponibilidade concluída.")
                    st.json(resultado)
    elif manifesto["status"] == "RECEBIDO":
        st.success(f"Recebimento integral confirmado em {horario((manifesto.get('recebimento') or {}).get('confirmado_em'))}.")
        if manifesto.get("sincronizacao_redis") == "PENDENTE":
            st.warning("A confirmação documental está salva; a sincronização do veículo com o Redis está pendente.")
            if st.button("Repetir sincronização do recebimento", type="primary"):
                ok, resultado = executar(sistema.sincronizar_recebimento, manifesto_id)
                if ok:
                    exibir_avisos(resultado)
                    if resultado.get("sincronizacao_redis") == "SINCRONIZADO":
                        st.success("Sincronização concluída.")
                    else:
                        st.warning("A sincronização continua pendente. Confira a conexão com o Redis e repita a ação.")
    with st.expander("Documento completo e histórico"):
        st.json(manifesto)
        st.download_button("Baixar manifesto JSON", data=json_legivel(manifesto), file_name=f"{manifesto_id}.json", mime="application/json")


def renderizar(sistema) -> None:
    cabecalho("Despacho e recebimento", "Vincule carga, veículo e percurso. A entrega é confirmada integralmente.")
    despacho, recebimento = st.tabs(["Preparar despacho", "Recebimentos e histórico"])
    with despacho:
        executar(_novo_despacho, sistema)
    with recebimento:
        executar(_recebimento, sistema)
