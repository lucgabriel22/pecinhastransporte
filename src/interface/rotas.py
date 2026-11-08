"""Seleção de caminhos por distância e avaliação de indisponibilidades."""

import streamlit as st

from src.interface.comum import assinatura_malha, executar, exibir_percurso, numero, opcoes_locais
from src.interface.grafo import desenhar_malha
from src.interface.layout import cabecalho, titulo_secao


def selecionar_parametros(malha: dict, prefixo: str) -> dict | None:
    nomes = opcoes_locais(malha)
    if len(nomes) < 2:
        st.info("Inicialize a malha de demonstração para selecionar origem e destino.")
        return None
    estado = st.session_state.get("simulacao_rota", {})
    ids = list(nomes)
    origem_padrao = next((local["id"] for local in malha["locais"] if local["tipo"] == "CentroDistribuição"), ids[0])
    destino_padrao = next((local["id"] for local in malha["locais"] if local["tipo"] == "Cliente"), ids[-1])
    origem_anterior = estado.get("origem_id", origem_padrao)
    destino_anterior = estado.get("destino_id", destino_padrao)
    a, b = st.columns(2)
    origem = a.selectbox("Origem", ids, index=ids.index(origem_anterior) if origem_anterior in ids else 0, format_func=nomes.get, key=f"{prefixo}_origem")
    destino = b.selectbox("Destino", ids, index=ids.index(destino_anterior) if destino_anterior in ids else len(ids)-1, format_func=nomes.get, key=f"{prefixo}_destino")
    trechos = {t["id"]: t for t in malha["trechos"]}
    with st.expander("Simular indisponibilidades", expanded=bool(estado.get("trechos_bloqueados") or estado.get("locais_bloqueados"))):
        st.caption("Bloqueios valem para esta sessão. Cada trecho possui sentido explícito; não se presume trajeto de retorno.")
        bloqueios_t = st.multiselect("Trechos bloqueados", list(trechos), default=[v for v in estado.get("trechos_bloqueados", []) if v in trechos], format_func=lambda v: f"{v} · {nomes.get(trechos[v]['origem_id'])} → {nomes.get(trechos[v]['destino_id'])}", key=f"{prefixo}_trechos")
        bloqueios_l = st.multiselect("Locais inoperantes", ids, default=[v for v in estado.get("locais_bloqueados", []) if v in ids], format_func=nomes.get, key=f"{prefixo}_locais")
    parametros = {"origem_id": origem, "destino_id": destino, "trechos_bloqueados": sorted(bloqueios_t), "locais_bloqueados": sorted(bloqueios_l)}
    st.session_state["simulacao_rota"] = parametros
    return parametros


def renderizar(sistema) -> None:
    cabecalho("Otimizador de rotas", "Compare a menor quilometragem com o menor número de trechos e avalie bloqueios na malha.")
    malha = sistema.obter_malha()
    titulo_secao("Planeje um percurso", "Escolha origem e destino e, se necessário, simule uma indisponibilidade.")
    parametros = selecionar_parametros(malha, "otimizador")
    if parametros is None:
        return
    if st.button("Calcular e comparar percursos", type="primary"):
        ok, calculo = executar(sistema.calcular_rotas, **parametros)
        if ok:
            sem_bloqueios = {**parametros, "trechos_bloqueados": [], "locais_bloqueados": []}
            ok_base, base = executar(sistema.calcular_rotas, **sem_bloqueios)
            st.session_state["resultado_rotas"] = {"parametros": parametros, "malha": assinatura_malha(malha), "calculo": calculo, "base": base if ok_base else None}
    salvo = st.session_state.get("resultado_rotas")
    atual = salvo and salvo["parametros"] == parametros and salvo.get("malha") == assinatura_malha(malha)
    percurso = salvo["calculo"]["menor_distancia"] if atual else None
    titulo_secao("Malha logística", "Conexões dirigidas entre distribuição, transbordo e entrega.", f"{len(malha['locais'])} locais · {len(malha['trechos'])} trechos")
    st.image(desenhar_malha(malha, percurso, parametros["trechos_bloqueados"], parametros["locais_bloqueados"]), width="stretch")
    st.caption("Âmbar: menor distância calculada · Vermelho tracejado: indisponibilidade · Setas: sentido do trecho. Desenho e distâncias fictícios.")
    if salvo and not atual:
        st.info("A seleção ou a malha mudou. Recalcule para exibir os resultados correspondentes.")
    if not atual:
        return
    a, b = st.columns(2)
    with a:
        exibir_percurso(percurso, "Menor distância em quilômetros")
    with b:
        exibir_percurso(salvo["calculo"]["menos_trechos"], "Menos trechos · shortestPath")
    base = (salvo.get("base") or {}).get("menor_distancia")
    if parametros["trechos_bloqueados"] or parametros["locais_bloqueados"]:
        if base and percurso:
            aumento = percurso["distancia_total_km"] - base["distancia_total_km"]
            st.info(f"Impacto da simulação: {numero(base['distancia_total_km'])} km sem bloqueios → {numero(percurso['distancia_total_km'])} km com bloqueios. Variação de {numero(aumento)} km.")
        elif base and not percurso:
            st.warning("Os bloqueios interromperam a conexão entre a origem e o destino.")
    with st.expander("Como interpretar o resultado"):
        st.write("shortestPath compara o número de relações TRECHO. A menor distância compara a soma dos quilômetros. Uma rota é o percurso completo, formado pela sequência dos trechos.")
        st.write("Na malha inicial: Centro A → Cliente A custa 30 km em um trecho; passando pelo Transbordo A, são 20 km em dois trechos. Bloquear T2 leva ao percurso de 23 km pelo Transbordo B.")
    if malha.get("rotas"):
        with st.expander("Percursos completos registrados no Neo4j"):
            st.dataframe([{ "Rota": r["id"], "Trechos": " → ".join(r.get("trechos_ids", [])), "Distância (km)": r["distancia_total_km"]} for r in malha["rotas"]], hide_index=True, width="stretch")
