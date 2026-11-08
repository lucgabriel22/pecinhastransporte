"""Telemetria real do Redis e eventos simulados recebidos por Pub/Sub."""

from datetime import datetime

import streamlit as st

from src.interface.comum import executar, horario, numero
from src.interface.layout import cabecalho, titulo_secao, vazio


def renderizar(sistema) -> None:
    cabecalho("Torre de controle", "Acompanhe a última leitura de cada veículo e simule eventos de desvio ou acidente.")
    atualizacao = sistema.configuracao.telemetria_atualizacao_segundos
    validade = sistema.configuracao.telemetria_validade_segundos
    st.caption(f"Telemetria de demonstração · Tela atualizada a cada {atualizacao} s · Leitura desatualizada após {validade} s.")
    executar(sistema.iniciar_assinante_alertas)

    @st.fragment(run_every=atualizacao)
    def painel_tempo_real() -> None:
        ok, veiculos = executar(sistema.listar_veiculos)
        if not ok:
            return
        a, b, c = st.columns(3)
        a.metric("Veículos monitorados", len(veiculos))
        b.metric("Em transporte", sum(v["disponibilidade"] == "EM_TRANSPORTE" for v in veiculos))
        c.metric("Leituras atuais", sum(bool(v.get("telemetria")) and not v["telemetria"].get("desatualizada", True) for v in veiculos))
        titulo_secao("Veículos da operação", "Posição, condições de transporte e disponibilidade.", f"Consulta {horario(datetime.now().astimezone())}")
        if not veiculos:
            st.info("Nenhum veículo cadastrado. Execute a carga de demonstração.")
        for veiculo in veiculos:
            with st.container(border=True, key=f"pt_veiculo_{veiculo['id']}"):
                estados = {"DISPONIVEL": "Disponível", "RESERVADO": "Reservado", "EM_TRANSPORTE": "Em transporte"}
                estado = estados.get(veiculo["disponibilidade"], veiculo["disponibilidade"].replace("_", " ").capitalize())
                titulo_secao(veiculo["nome"], veiculo["id"], estado)
                if veiculo.get("manifesto_id"):
                    st.caption(f"Manifesto: {veiculo['manifesto_id']}")
                leitura = veiculo.get("telemetria")
                if not leitura:
                    st.warning("Telemetria indisponível. Uma leitura ausente não indica veículo parado ou disponível.")
                    continue
                a, b, c = st.columns(3)
                a.metric("Velocidade", f"{numero(leitura['velocidade_kmh'])} km/h")
                b.metric("Temperatura", f"{numero(leitura['temperatura_c'])} °C")
                idade = leitura.get("idade_segundos")
                c.metric("Idade da leitura", f"{numero(idade, 0)} s" if idade is not None else "Indisponível")
                st.write(f"GPS: {float(leitura['latitude']):.6f}, {float(leitura['longitude']):.6f}")
                st.caption(f"Medido em {horario(leitura['medido_em'])} · Recebido em {horario(leitura['recebido_em'])}")
                if leitura.get("desatualizada", True):
                    st.warning("Leitura desatualizada. Envie uma nova telemetria pelo simulador abaixo.")
                else:
                    st.success("Leitura atual")
        titulo_secao("Central de alertas", "Eventos recebidos pelo assinante durante esta sessão.")
        ok, eventos = executar(sistema.listar_alertas)
        if ok:
            historico = st.session_state.setdefault("alertas_recebidos", [])
            ids_existentes = {evento["evento_id"] for evento in historico}
            for evento in eventos:
                if evento["evento_id"] not in ids_existentes:
                    historico.insert(0, evento)
                    ids_existentes.add(evento["evento_id"])
            st.session_state["alertas_recebidos"] = historico[:30]
            if historico:
                st.dataframe([{ "Ocorrência": horario(e.get("ocorrido_em")), "Tipo": e["tipo"], "Veículo": e["veiculo_id"], "Manifesto": e.get("manifesto_id") or "—", "Evento": e["evento_id"]} for e in historico[:30]], hide_index=True, width="stretch")
            else:
                vazio("Nenhum alerta recebido", "Os eventos de desvio e acidente recebidos nesta sessão aparecerão aqui.")
        st.caption("Somente eventos recebidos pelo assinante Pub/Sub aparecem acima. Pub/Sub não recupera mensagens perdidas durante uma desconexão.")
        with st.expander("Estado do assinante de alertas"):
            st.json(sistema.estado_assinante_alertas())

    painel_tempo_real()
    st.divider()
    titulo_secao("Simuladores de demonstração", "Envie uma leitura ou publique um evento fictício para acompanhar o fluxo.", "DADOS FICTÍCIOS")
    veiculos = sistema.listar_veiculos()
    if not veiculos:
        return
    por_id = {v["id"]: v for v in veiculos}
    veiculo_id = st.selectbox("Veículo da simulação", list(por_id), format_func=lambda v: f"{por_id[v]['nome']} · {v}")
    st.caption("Os valores são informados manualmente. Desvios e acidentes são eventos explícitos; não são inferidos da velocidade, da posição ou da temperatura.")
    telemetria = por_id[veiculo_id].get("telemetria") or {}
    with st.form("nova_telemetria"):
        st.markdown("**Enviar leitura simulada**")
        a, b, c, d = st.columns(4)
        latitude = a.number_input("Latitude", min_value=-90.0, max_value=90.0, value=float(telemetria.get("latitude", 0.0)), format="%.6f", key=f"latitude_{veiculo_id}")
        longitude = b.number_input("Longitude", min_value=-180.0, max_value=180.0, value=float(telemetria.get("longitude", 0.0)), format="%.6f", key=f"longitude_{veiculo_id}")
        velocidade = c.number_input("Velocidade (km/h)", min_value=0.0, value=float(telemetria.get("velocidade_kmh", 0.0)), step=1.0, key=f"velocidade_{veiculo_id}")
        temperatura = d.number_input("Temperatura (°C)", value=float(telemetria.get("temperatura_c", 0.0)), step=0.5, key=f"temperatura_{veiculo_id}")
        enviar = st.form_submit_button("Enviar telemetria", type="primary")
    if enviar:
        ok, _ = executar(sistema.atualizar_telemetria, veiculo_id, latitude, longitude, velocidade, temperatura)
        if ok:
            st.success("Leitura gravada no Redis. O painel será atualizado na próxima consulta.")
    a, b = st.columns(2)
    for coluna, tipo, rotulo in ((a, "desvio", "Simular desvio de rota"), (b, "acidente", "Simular acidente")):
        if coluna.button(rotulo, width="stretch"):
            ok, resultado = executar(sistema.simular_alerta, tipo, veiculo_id)
            if ok:
                st.success("Evento de demonstração publicado. Aguarde a recepção no painel de alertas.")
                if resultado.get("aviso"):
                    st.warning(resultado["aviso"])
    with st.expander("Histórico documental dos eventos publicados"):
        if st.button("Consultar auditoria de alertas"):
            ok, historico = executar(sistema.listar_auditoria_alertas)
            if ok:
                st.json(historico)
        st.caption("A auditoria no MongoDB registra a publicação. Esse registro não comprova a entrega ao assinante Pub/Sub.")
