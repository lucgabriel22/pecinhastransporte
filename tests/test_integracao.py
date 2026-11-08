"""Fluxos com MongoDB, Redis e Neo4j reais, sem substituir bancos por fakes.

Executar optando por TESTAR_INTEGRACAO=1 após a inicialização local. Os dados
ficam em supply_chain_testes e em um prefixo Redis único por execução. Nada
é apagado. O Neo4j compartilha a malha fictícia inicial, sem alterar bloqueios
persistidos ou restaurar trechos que alguém tenha modificado.
"""

from dataclasses import replace
import os
import time
import unittest
from uuid import uuid4


@unittest.skipUnless(os.getenv("TESTAR_INTEGRACAO") == "1", "Integração com os três bancos não solicitada")
class SistemaIntegracaoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from src.bootstrap import criar_sistema
        from src.configuracao import Configuracao
        from scripts.inicializar import inicializar_sistema

        try:
            configuracao = replace(
                Configuracao.carregar(),
                mongo_database="supply_chain_testes",
                redis_prefixo=f"sc:teste:{uuid4().hex}:",
            )
        except ValueError as erro:
            raise unittest.SkipTest(f"Configuração local ainda indisponível: {erro}") from erro
        cls.sistema = criar_sistema(configuracao)
        cls.addClassCleanup(cls.sistema.fechar)
        falhas = [banco["banco"] for banco in cls.sistema.verificar_conexoes() if not banco["ok"]]
        if falhas:
            raise unittest.SkipTest("Bancos reais indisponíveis; integração não executada: " + ", ".join(falhas))
        inicializar_sistema(cls.sistema)

    def setUp(self):
        self.execucao = uuid4().hex

    def _nova_carga(self, quantidade=10):
        mercadoria = self.sistema.cadastrar_mercadoria(
            f"Mercadoria do teste {self.execucao}", {}, {},
        )
        lote = self.sistema.cadastrar_lote(mercadoria, quantidade, "unidade", "DEMO-CD-001")
        veiculo = f"DEMO-TEST-VEI-{self.execucao}"
        self.sistema.redis.inicializar_veiculo(veiculo, "Veículo exclusivo de teste")
        return lote, veiculo

    def _solicitacao(self, lote_id, veiculo_id, quantidade=4, sufixo="A"):
        return {
            "manifesto_id": f"DEMO-TEST-MAN-{self.execucao}-{sufixo}",
            "veiculo_id": veiculo_id,
            "origem_id": "DEMO-CD-001",
            "destino_id": "DEMO-CLI-001",
            "itens": [{"lote_id": lote_id, "quantidade": quantidade}],
            "documentacao_carga": {"demonstracao": True, "teste": self.execucao},
        }

    def _saldo(self, lote_id):
        return next(lote["quantidade"] for lote in self.sistema.listar_lotes() if lote["_id"] == lote_id)

    def test_rotas_em_quilometros_e_bloqueios(self):
        inicial = self.sistema.calcular_rotas("DEMO-CD-001", "DEMO-CLI-001")
        self.assertEqual(inicial["menor_distancia"]["distancia_total_km"], 20.0)
        self.assertEqual(inicial["menos_trechos"]["distancia_total_km"], 30.0)
        bloqueado = self.sistema.calcular_rotas("DEMO-CD-001", "DEMO-CLI-001", ["T2"])
        self.assertEqual(bloqueado["menor_distancia"]["distancia_total_km"], 23.0)
        self.assertEqual(
            self.sistema.calcular_rotas("DEMO-CD-001", "DEMO-CLI-001", locais_bloqueados=["DEMO-CLI-001"]),
            {"menor_distancia": None, "menos_trechos": None},
        )

    def test_pubsub_recebe_eventos_depois_da_confirmacao_de_assinatura(self):
        _, veiculo = self._nova_carga()
        estado = self.sistema.iniciar_assinante_alertas()
        self.assertTrue(estado["conectado"], "O consumidor não confirmou a inscrição nos canais Redis.")
        for tipo in ("DESVIO", "ACIDENTE"):
            with self.subTest(tipo=tipo):
                publicado = self.sistema.simular_alerta(tipo, veiculo)
                self.assertEqual(publicado["publicacao"], "PUBLICADO")
                self.assertGreaterEqual(publicado["assinantes_no_canal"], 1)
                limite = time.monotonic() + 5
                recebido = None
                while time.monotonic() < limite:
                    eventos = self.sistema.listar_alertas()
                    recebido = next((evento for evento in eventos if evento["evento_id"] == publicado["evento_id"]), None)
                    if recebido is not None:
                        break
                    time.sleep(0.05)
                self.assertIsNotNone(recebido, "A publicação não chegou ao consumidor real no prazo de 5 segundos.")
                self.assertEqual(recebido["tipo"], tipo)
                self.assertEqual(recebido["veiculo_id"], veiculo)
                self.assertTrue(recebido["demonstracao"])
                registro = self.sistema.mongo.database.auditoria.find_one({"_id": publicado["evento_id"]})
                self.assertEqual(registro["detalhes"]["publicacao"], "PUBLICADO")

    def test_despacho_e_recebimento_nao_repetem_baixa_de_estoque(self):
        lote, veiculo = self._nova_carga(10)
        solicitacao = self._solicitacao(lote, veiculo, quantidade=4)
        despachado = self.sistema.despachar(**solicitacao)
        self.assertEqual(despachado["status"], "DESPACHADO")
        self.assertEqual(despachado["sincronizacao_redis"], "SINCRONIZADO")
        self.assertEqual(self._saldo(lote), 6)
        estado = self.sistema.redis.obter_estado(veiculo)
        self.assertEqual(estado["disponibilidade"], "EM_TRANSPORTE")
        self.assertEqual(estado["manifesto_id"], solicitacao["manifesto_id"])

        self.sistema.despachar(**solicitacao)
        self.assertEqual(self._saldo(lote), 6)
        recebido = self.sistema.receber(solicitacao["manifesto_id"])
        self.assertEqual(recebido["status"], "RECEBIDO")
        self.assertTrue(recebido["recebimento"]["integral"])
        self.assertEqual(recebido["sincronizacao_redis"], "SINCRONIZADO")
        self.assertEqual(self._saldo(lote), 6)
        self.assertEqual(self.sistema.redis.obter_estado(veiculo)["disponibilidade"], "DISPONIVEL")

        self.sistema.receber(solicitacao["manifesto_id"])
        self.assertEqual(self._saldo(lote), 6)
        banco = self.sistema.mongo.database
        self.assertEqual(banco.manifestos.count_documents({"_id": solicitacao["manifesto_id"]}), 1)
        self.assertEqual(banco.auditoria.count_documents({"_id": f"despacho:{solicitacao['manifesto_id']}"}), 1)
        self.assertEqual(banco.auditoria.count_documents({"_id": f"recebimento:{solicitacao['manifesto_id']}"}), 1)
        rota_id = recebido["percurso"]["rota_id"]
        rota = next(rota for rota in self.sistema.obter_malha()["rotas"] if rota["id"] == rota_id)
        self.assertEqual(rota["trechos_ids"], ["T1", "T2"])

    def test_recebimento_antigo_preserva_veiculo_em_novo_despacho(self):
        lote, veiculo = self._nova_carga(20)
        antigo = self._solicitacao(lote, veiculo, quantidade=3, sufixo="ANTIGO")
        novo = self._solicitacao(lote, veiculo, quantidade=5, sufixo="NOVO")
        self.sistema.despachar(**antigo)
        self.sistema.receber(antigo["manifesto_id"])
        self.sistema.despachar(**novo)
        self.sistema.receber(antigo["manifesto_id"])
        estado = self.sistema.redis.obter_estado(veiculo)
        self.assertEqual(estado["disponibilidade"], "EM_TRANSPORTE")
        self.assertEqual(estado["manifesto_id"], novo["manifesto_id"])
        self.assertEqual(self._saldo(lote), 12)
        self.sistema.receber(novo["manifesto_id"])
        self.assertEqual(self.sistema.redis.obter_estado(veiculo)["disponibilidade"], "DISPONIVEL")

    def test_transacao_com_saldo_insuficiente_nao_debita_parte_dos_lotes(self):
        from src.dominio import ErroDominio

        lote_a, veiculo = self._nova_carga(10)
        mercadoria = self.sistema.cadastrar_mercadoria("Mercadoria para rollback de demonstração", {}, {})
        lote_b = self.sistema.cadastrar_lote(mercadoria, 1, "unidade", "DEMO-CD-001")
        solicitacao = self._solicitacao(lote_a, veiculo)
        # O lote de saldo suficiente vem primeiro na ordem efetiva da transação.
        primeiro, segundo = sorted((lote_a, lote_b))
        saldos = {lote_a: 10, lote_b: 1}
        solicitacao["itens"] = [
            {"lote_id": primeiro, "quantidade": 1},
            {"lote_id": segundo, "quantidade": saldos[segundo] + 1},
        ]
        with self.assertRaises(ErroDominio):
            self.sistema.despachar(**solicitacao)
        self.assertEqual(self._saldo(lote_a), 10)
        self.assertEqual(self._saldo(lote_b), 1)
        self.assertIsNone(self.sistema.mongo.obter_manifesto(solicitacao["manifesto_id"]))
        self.assertEqual(self.sistema.redis.obter_estado(veiculo)["disponibilidade"], "DISPONIVEL")

    def test_telemetria_persistida_e_identificada_como_demonstracao(self):
        _, veiculo = self._nova_carga()
        self.sistema.atualizar_telemetria(veiculo, 0.001, 0.002, 12.0, 21.0)
        leitura = self.sistema.obter_telemetria(veiculo)
        self.assertEqual(leitura["latitude"], 0.001)
        self.assertEqual(leitura["velocidade_kmh"], 12.0)
        self.assertEqual(leitura["temperatura_c"], 21.0)
        self.assertTrue(leitura["demonstracao"])
        self.assertFalse(leitura["desatualizada"])


if __name__ == "__main__":
    unittest.main()
