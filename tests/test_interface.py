"""Testes dos widgets com fixture isolada; não validam conexão ou bancos reais.

A aplicação de produção sempre usa criar_sistema e os três repositórios reais.
Esta fixture existe exclusivamente para exercitar a navegação e as confirmações
do Streamlit sem exigir contêineres durante os testes da interface.
"""

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from xml.etree import ElementTree

import streamlit as st
from streamlit.testing.v1 import AppTest

from src.dados_demo import LOCAIS, LOTES, MERCADORIAS, ROTAS, TRECHOS
from src.dominio import ErroDominio, ErroInfraestrutura, agora_utc
from src.interface.grafo import desenhar_malha


class SistemaFixtureInterface:
    """Dublê restrito à comunicação tela/serviço; sem simular garantias de banco."""

    def __init__(self):
        self.configuracao = SimpleNamespace(telemetria_atualizacao_segundos=5, telemetria_validade_segundos=30)
        self.malha = {"locais": deepcopy(LOCAIS), "trechos": deepcopy(TRECHOS), "rotas": deepcopy(ROTAS)}
        self.manifestos = []
        self.solicitacoes = []
        self.sincronizacoes_despacho = []
        self.falhar_despacho = False
        self.falhar_regra = False
        self.alertas = []

    def verificar_conexoes(self):
        return [{"banco": banco, "ok": True, "detalhe": "Fixture exclusiva do teste de widgets"} for banco in ("MongoDB", "Redis", "Neo4j")]

    def listar_mercadorias(self):
        return deepcopy(MERCADORIAS)

    def listar_lotes(self):
        return deepcopy(LOTES)

    def listar_manifestos(self):
        return deepcopy(self.manifestos)

    def obter_malha(self):
        return deepcopy(self.malha)

    def listar_veiculos(self):
        return [{"id": "DEMO-VEI-001", "nome": "Veículo de teste", "disponibilidade": "DISPONIVEL", "manifesto_id": None, "telemetria": None}]

    def calcular_rotas(self, origem_id, destino_id, trechos_bloqueados=None, locais_bloqueados=None):
        if origem_id == destino_id:
            raise ErroDominio("Escolha locais diferentes para origem e destino.")
        if destino_id in (locais_bloqueados or []):
            return {"menor_distancia": None, "menos_trechos": None}
        def percurso(ids):
            trechos = [next(t for t in TRECHOS if t["id"] == identificador) for identificador in ids]
            locais_ids = [trechos[0]["origem_id"], *[t["destino_id"] for t in trechos]]
            return {"locais": [next(l for l in LOCAIS if l["id"] == identificador) for identificador in locais_ids], "trechos": deepcopy(trechos), "distancia_total_km": sum(t["distancia_km"] for t in trechos)}
        return {"menor_distancia": percurso(["T4", "T5"] if "T2" in (trechos_bloqueados or []) else ["T1", "T2"]), "menos_trechos": percurso(["T3"])}

    def despachar(self, **dados):
        self.solicitacoes.append(deepcopy(dados))
        if self.falhar_despacho:
            self.falhar_despacho = False
            raise ErroInfraestrutura("Falha de conexão de teste; preserve a tentativa.")
        if self.falhar_regra:
            self.falhar_regra = False
            raise ErroDominio("Saldo alterado durante o teste.")
        manifesto = {"_id": dados["manifesto_id"], "status": "DESPACHADO", "veiculo_id": dados["veiculo_id"], "origem_id": dados["origem_id"], "destino_id": dados["destino_id"], "itens": dados["itens"], "percurso": dados["percurso_esperado"], "documentacao_carga": dados["documentacao_carga"], "despacho": {"confirmado_em": agora_utc()}, "recebimento": None, "sincronizacao_redis": "SINCRONIZADO", "avisos": []}
        self.manifestos = [manifesto]
        return deepcopy(manifesto)

    def iniciar_assinante_alertas(self):
        return self.estado_assinante_alertas()

    def sincronizar_despacho(self, manifesto_id):
        self.sincronizacoes_despacho.append(manifesto_id)
        manifesto = next(m for m in self.manifestos if m["_id"] == manifesto_id)
        manifesto["sincronizacao_redis"] = "SINCRONIZADO"
        return deepcopy(manifesto)

    def estado_assinante_alertas(self):
        return {"conectado": True, "erro": None, "descartados": 0}

    def listar_alertas(self):
        eventos, self.alertas = self.alertas, []
        return eventos

    def listar_auditoria_alertas(self):
        return []


class TestInterface(unittest.TestCase):
    def setUp(self):
        st.cache_resource.clear()
        self.sistema = SistemaFixtureInterface()
        self.patcher = patch("src.bootstrap.criar_sistema", return_value=self.sistema)
        self.patcher.start()
        self.app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=15)

    def tearDown(self):
        self.patcher.stop()
        st.cache_resource.clear()

    def botao(self, label):
        return next(botao for botao in self.app.button if botao.label == label)

    def preparar_despacho(self):
        self.app.run()
        self.app.sidebar.radio[0].set_value("Despacho e recebimento").run()
        self.botao("Conferir percurso para despacho").click().run()
        self.app.multiselect(key="carga_lotes_selecionados").set_value(["DEMO-LOT-001"]).run()
        self.app.number_input(key="carga_quantidade_DEMO-CD-001_DEMO-LOT-001").set_value(3)
        next(c for c in self.app.checkbox if "baixa das quantidades" in c.label).set_value(True)

    def test_quatro_telas_carregam_sem_excecao(self):
        self.app.run()
        for tela in self.app.sidebar.radio[0].options:
            with self.subTest(tela=tela):
                self.app.sidebar.radio[0].set_value(tela).run()
                self.assertEqual(len(self.app.exception), 0)
                self.assertEqual(len(self.app.error), 0)

    def test_svg_escapa_rotulos_e_mostra_setas(self):
        self.sistema.malha["locais"][0]["nome"] = '<script>inserção</script> & teste'
        svg = desenhar_malha(self.sistema.malha, trechos_bloqueados=["T2"])
        ElementTree.fromstring(svg)
        self.assertNotIn("<script>", svg)
        self.assertIn("&lt;script&gt;", svg)
        self.assertIn("marker-end=", svg)
        self.assertIn('stroke-dasharray="7 5"', svg)

    def test_despacho_envia_preview_sem_repetir_em_rerun(self):
        self.preparar_despacho()
        self.botao("Confirmar despacho").click().run()
        self.assertEqual(len(self.app.exception), 0)
        self.assertEqual(len(self.sistema.solicitacoes), 1)
        dados = self.sistema.solicitacoes[0]
        self.assertEqual(dados["itens"], [{"lote_id": "DEMO-LOT-001", "quantidade": 3}])
        self.assertEqual(dados["percurso_esperado"]["distancia_total_km"], 20)
        self.app.run()
        self.assertEqual(len(self.sistema.solicitacoes), 1)

    def test_erro_infra_preserva_identidade_e_payload_no_retry(self):
        self.preparar_despacho()
        self.sistema.falhar_despacho = True
        self.botao("Confirmar despacho").click().run()
        self.assertIn("despacho_pendente", self.app.session_state)
        self.app.run()
        self.botao("Repetir confirmação do mesmo despacho").click().run()
        self.assertEqual(len(self.app.exception), 0)
        self.assertEqual(len(self.sistema.solicitacoes), 2)
        self.assertEqual(self.sistema.solicitacoes[0], self.sistema.solicitacoes[1])
        self.assertNotIn("despacho_pendente", self.app.session_state)

    def test_erro_de_regra_libera_revisao_sem_pending(self):
        self.preparar_despacho()
        self.sistema.falhar_regra = True
        self.botao("Confirmar despacho").click().run()
        self.assertEqual(len(self.app.exception), 0)
        self.assertNotIn("despacho_pendente", self.app.session_state)
        self.assertNotIn("preparacao_despacho", self.app.session_state)
        self.assertNotIn("despacho_id", self.app.session_state)

        self.app.multiselect(key="despacho_trechos").set_value(["T2"]).run()
        self.botao("Conferir percurso para despacho").click().run()
        self.app.multiselect(key="carga_lotes_selecionados").set_value(["DEMO-LOT-001"]).run()
        self.app.number_input(key="carga_quantidade_DEMO-CD-001_DEMO-LOT-001").set_value(3)
        next(c for c in self.app.checkbox if "baixa das quantidades" in c.label).set_value(True)
        self.botao("Confirmar despacho").click().run()

        self.assertEqual(len(self.app.exception), 0)
        self.assertEqual(len(self.sistema.solicitacoes), 2)
        anterior, revisada = self.sistema.solicitacoes
        self.assertNotEqual(anterior["manifesto_id"], revisada["manifesto_id"])
        self.assertEqual([trecho["id"] for trecho in revisada["percurso_esperado"]["trechos"]], ["T4", "T5"])
        self.assertEqual(revisada["percurso_esperado"]["distancia_total_km"], 23)

    def test_mudar_parametros_invalida_preview(self):
        self.preparar_despacho()
        self.app.multiselect(key="despacho_trechos").set_value(["T2"]).run()
        self.assertFalse(any(b.label == "Confirmar despacho" for b in self.app.button))
        self.assertEqual(self.sistema.solicitacoes, [])

    def test_sincronizar_despacho_pelo_historico_apos_nova_sessao(self):
        self.preparar_despacho()
        self.botao("Confirmar despacho").click().run()
        manifesto = self.sistema.manifestos[0]
        manifesto["sincronizacao_redis"] = "PENDENTE"
        self.app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=15)
        self.app.run()
        self.app.sidebar.radio[0].set_value("Despacho e recebimento").run()
        self.assertNotIn("despacho_dados_confirmados", self.app.session_state)
        self.botao("Sincronizar disponibilidade deste despacho").click().run()
        self.assertEqual(len(self.app.exception), 0)
        self.assertEqual(self.sistema.sincronizacoes_despacho, [manifesto["_id"]])
        self.assertEqual(len(self.sistema.solicitacoes), 1)
        self.assertEqual(manifesto["sincronizacao_redis"], "SINCRONIZADO")


if __name__ == "__main__":
    unittest.main()
