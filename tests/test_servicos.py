"""Testes de coordenação com repositórios em memória.

Os dublês expressam os contratos atômicos dos repositórios. Estes testes não
comprovam execução de Lua, transações MongoDB ou conectividade com bancos.
"""

from copy import deepcopy
import unittest

from src.dominio import ErroDominio, ErroInfraestrutura, agora_utc
from src.servicos.sistema import SistemaLogistico


class MongoEmMemoria:
    def __init__(self):
        self.saldos = {"L1": 10, "L2": 5}
        self.manifestos = {}
        self.auditoria = []
        self.falha_transacao = None
        self.recebimentos = 0

    def obter_manifesto(self, manifesto_id):
        return deepcopy(self.manifestos.get(manifesto_id))

    def confirmar_despacho(self, documento):
        existente = self.obter_manifesto(documento["_id"])
        if existente:
            if existente["assinatura_solicitacao"] != documento["assinatura_solicitacao"]:
                raise ErroDominio("ID utilizado por outro pedido")
            return existente
        if self.falha_transacao == "ANTES_COMMIT":
            self.falha_transacao = None
            raise ErroInfraestrutura("Falha antes do commit")
        saldos = dict(self.saldos)
        for item in documento["itens"]:
            saldo = saldos.get(item["lote_id"], 0)
            if saldo < item["quantidade"]:
                raise ErroDominio("Saldo insuficiente")
            saldos[item["lote_id"]] -= item["quantidade"]
        self.saldos = saldos
        self.manifestos[documento["_id"]] = deepcopy(documento)
        self.auditoria.append(documento["despacho"]["operacao_id"])
        if self.falha_transacao == "DEPOIS_COMMIT":
            self.falha_transacao = None
            raise ErroInfraestrutura("Resposta do commit perdida")
        return deepcopy(documento)

    def confirmar_recebimento(self, manifesto_id):
        manifesto = self.manifestos.get(manifesto_id)
        if not manifesto:
            raise ErroDominio("Manifesto inexistente")
        if manifesto["status"] != "RECEBIDO":
            self.recebimentos += 1
            manifesto.update(status="RECEBIDO", sincronizacao_redis="PENDENTE", recebimento={"integral": True})
            self.auditoria.append(f"recebimento:{manifesto_id}")
        return deepcopy(manifesto)

    def marcar_sincronizacao(self, manifesto_id, status, estado_esperado=None):
        if estado_esperado and self.manifestos[manifesto_id]["status"] != estado_esperado:
            raise ErroInfraestrutura("Estado alterado por outra operação")
        self.manifestos[manifesto_id]["sincronizacao_redis"] = status


class RedisEmMemoria:
    def __init__(self):
        self.estado = {"disponibilidade": "DISPONIVEL", "manifesto_id": None, "assinatura_solicitacao": ""}
        self.recebidos = set()
        self.falhar_confirmacao = False
        self.falhar_liberacao = False
        self.leitura = None

    def reservar_veiculo(self, veiculo_id, manifesto_id, assinatura_solicitacao=""):
        if manifesto_id in self.recebidos:
            raise ErroDominio("Manifesto já recebido")
        if self.estado["manifesto_id"] == manifesto_id and self.estado["assinatura_solicitacao"] == assinatura_solicitacao:
            return True
        if self.estado["disponibilidade"] != "DISPONIVEL":
            return False
        self.estado.update(disponibilidade="RESERVADO", manifesto_id=manifesto_id, assinatura_solicitacao=assinatura_solicitacao)
        return True

    def confirmar_despacho(self, veiculo_id, manifesto_id):
        if self.falhar_confirmacao:
            raise ErroInfraestrutura("Redis desconectado após commit")
        if self.estado["manifesto_id"] != manifesto_id:
            return False
        self.estado["disponibilidade"] = "EM_TRANSPORTE"
        return True

    def cancelar_reserva(self, veiculo_id, manifesto_id):
        if self.estado["manifesto_id"] == manifesto_id and self.estado["disponibilidade"] == "RESERVADO":
            self.estado.update(disponibilidade="DISPONIVEL", manifesto_id=None)
            return True
        return False

    def liberar_veiculo(self, veiculo_id, manifesto_id):
        if self.falhar_liberacao:
            raise ErroInfraestrutura("Redis indisponível")
        self.recebidos.add(manifesto_id)
        if self.estado["manifesto_id"] == manifesto_id:
            self.estado.update(disponibilidade="DISPONIVEL", manifesto_id=None)
            return "LIBERADO"
        if self.estado["disponibilidade"] == "DISPONIVEL":
            return "JA_LIBERADO"
        return "OUTRO_MANIFESTO"

    def atualizar_telemetria(self, veiculo_id, leitura):
        self.leitura = deepcopy(leitura)
        return True

    def obter_telemetria(self, veiculo_id):
        return deepcopy(self.leitura)


class GrafoEmMemoria:
    def __init__(self):
        self.percurso = {
            "locais": [{"id": "ORIGEM"}, {"id": "DESTINO"}],
            "trechos": [{"id": "T1", "origem_id": "ORIGEM", "destino_id": "DESTINO", "distancia_km": 20}],
            "distancia_total_km": 20,
        }
        self.rotas = {}

    def calcular_rotas(self, *args):
        return {"menor_distancia": deepcopy(self.percurso), "menos_trechos": deepcopy(self.percurso)}

    def registrar_rota(self, rota_id, percurso):
        self.rotas[rota_id] = deepcopy(percurso)


class FluxosTests(unittest.TestCase):
    def setUp(self):
        self.mongo = MongoEmMemoria()
        self.redis = RedisEmMemoria()
        self.grafo = GrafoEmMemoria()
        self.sistema = SistemaLogistico(self.mongo, self.redis, self.grafo)
        self.pedido = dict(manifesto_id="M1", veiculo_id="V1", origem_id="ORIGEM", destino_id="DESTINO",
                           itens=[{"lote_id": "L1", "quantidade": 3}], documentacao_carga={"demonstracao": True},
                           trechos_bloqueados=[], locais_bloqueados=[])

    def test_repetir_despacho_nao_repete_baixa_nem_auditoria(self):
        primeiro = self.sistema.despachar(**self.pedido)
        segundo = self.sistema.despachar(**self.pedido)
        self.assertEqual(primeiro["_id"], segundo["_id"])
        self.assertEqual(self.mongo.saldos["L1"], 7)
        self.assertEqual(self.mongo.auditoria, ["despacho:M1"])
        self.assertEqual(self.redis.estado["disponibilidade"], "EM_TRANSPORTE")

    def test_recebimento_integral_nao_baixa_estoque_novamente(self):
        self.sistema.despachar(**self.pedido)
        self.sistema.receber("M1")
        resultado = self.sistema.receber("M1")
        self.assertEqual(resultado["status"], "RECEBIDO")
        self.assertEqual(self.mongo.recebimentos, 1)
        self.assertEqual(self.mongo.saldos["L1"], 7)
        self.assertEqual(self.redis.estado["disponibilidade"], "DISPONIVEL")

    def test_falha_de_um_lote_nao_debita_nenhum_e_cancela_reserva(self):
        self.pedido["itens"].append({"lote_id": "L2", "quantidade": 6})
        with self.assertRaises(ErroDominio):
            self.sistema.despachar(**self.pedido)
        self.assertEqual(self.mongo.saldos, {"L1": 10, "L2": 5})
        self.assertFalse(self.mongo.manifestos)
        self.assertEqual(self.redis.estado["disponibilidade"], "DISPONIVEL")

    def test_veiculo_associado_a_outra_carga_impede_novo_debito(self):
        self.sistema.despachar(**self.pedido)
        outro = {**self.pedido, "manifesto_id": "M2"}
        with self.assertRaises(ErroDominio):
            self.sistema.despachar(**outro)
        self.assertEqual(self.mongo.saldos["L1"], 7)
        self.assertEqual(self.redis.estado["manifesto_id"], "M1")

    def test_mesmo_id_com_dados_distintos_e_rejeitado(self):
        self.sistema.despachar(**self.pedido)
        outro = {**self.pedido, "itens": [{"lote_id": "L1", "quantidade": 4}]}
        with self.assertRaisesRegex(ErroDominio, "outros dados"):
            self.sistema.despachar(**outro)
        self.assertEqual(self.mongo.saldos["L1"], 7)

    def test_commit_com_resposta_perdida_preserva_reserva_e_retry_nao_duplica(self):
        self.mongo.falha_transacao = "DEPOIS_COMMIT"
        with self.assertRaisesRegex(ErroInfraestrutura, "mesmo ID"):
            self.sistema.despachar(**self.pedido)
        self.assertEqual(self.redis.estado["disponibilidade"], "RESERVADO")
        self.assertEqual(self.mongo.saldos["L1"], 7)
        recuperado = self.sistema.despachar(**self.pedido)
        self.assertEqual(recuperado["sincronizacao_redis"], "SINCRONIZADO")
        self.assertEqual(self.mongo.saldos["L1"], 7)

    def test_falha_antes_commit_mantem_reserva_e_retry_conclui_uma_vez(self):
        self.mongo.falha_transacao = "ANTES_COMMIT"
        with self.assertRaises(ErroInfraestrutura):
            self.sistema.despachar(**self.pedido)
        self.assertEqual(self.redis.estado["disponibilidade"], "RESERVADO")
        self.assertEqual(self.mongo.saldos["L1"], 10)
        self.sistema.despachar(**self.pedido)
        self.assertEqual(self.mongo.saldos["L1"], 7)

    def test_falha_redis_depois_debito_informa_confirmacao_e_pendencia(self):
        self.redis.falhar_confirmacao = True
        resultado = self.sistema.despachar(**self.pedido)
        self.assertEqual(resultado["status"], "DESPACHADO")
        self.assertEqual(resultado["sincronizacao_redis"], "PENDENTE")
        self.assertTrue(resultado["avisos"])
        self.redis.falhar_confirmacao = False
        recuperado = self.sistema.despachar(**self.pedido)
        self.assertEqual(recuperado["sincronizacao_redis"], "SINCRONIZADO")
        self.assertEqual(self.mongo.saldos["L1"], 7)

    def test_recebimento_confirmado_com_redis_fora_pode_ser_sincronizado(self):
        self.sistema.despachar(**self.pedido)
        self.redis.falhar_liberacao = True
        resultado = self.sistema.receber("M1")
        self.assertEqual(resultado["status"], "RECEBIDO")
        self.assertEqual(resultado["sincronizacao_redis"], "PENDENTE")
        self.redis.falhar_liberacao = False
        self.assertEqual(self.sistema.sincronizar_recebimento("M1")["sincronizacao_redis"], "SINCRONIZADO")
        self.assertEqual(self.mongo.recebimentos, 1)
        self.assertEqual(self.mongo.saldos["L1"], 7)

    def test_sincronizar_despacho_recupera_estado_sem_baixa_nem_novo_calculo(self):
        self.redis.falhar_confirmacao = True
        self.sistema.despachar(**self.pedido)
        self.redis.falhar_confirmacao = False
        # Simula a recuperação após perda do estado Redis, mantendo o MongoDB.
        self.redis.estado.update(disponibilidade="DISPONIVEL", manifesto_id=None, assinatura_solicitacao="")
        self.grafo.percurso = None
        resultado = self.sistema.sincronizar_despacho("M1")
        self.assertEqual(resultado["sincronizacao_redis"], "SINCRONIZADO")
        self.assertEqual(self.redis.estado["disponibilidade"], "EM_TRANSPORTE")
        self.assertEqual(self.redis.estado["manifesto_id"], "M1")
        self.assertEqual(self.mongo.saldos["L1"], 7)
        self.assertEqual(self.mongo.auditoria, ["despacho:M1"])

    def test_sincronizar_despacho_nao_reabre_manifesto_recebido(self):
        self.sistema.despachar(**self.pedido)
        self.sistema.receber("M1")
        with self.assertRaisesRegex(ErroDominio, "ainda em transporte"):
            self.sistema.sincronizar_despacho("M1")
        self.assertEqual(self.redis.estado["disponibilidade"], "DISPONIVEL")

    def test_recebimento_antigo_nao_libera_veiculo_em_novo_despacho(self):
        self.sistema.despachar(**self.pedido)
        self.sistema.receber("M1")
        self.sistema.despachar(**{**self.pedido, "manifesto_id": "M2"})
        self.sistema.receber("M1")
        self.assertEqual(self.redis.estado["manifesto_id"], "M2")
        self.assertEqual(self.redis.estado["disponibilidade"], "EM_TRANSPORTE")
        self.assertEqual(self.mongo.saldos["L1"], 4)

    def test_retry_antigo_despacho_recebido_nao_reabre_veiculo(self):
        self.sistema.despachar(**self.pedido)
        self.sistema.receber("M1")
        resultado = self.sistema.despachar(**self.pedido)
        self.assertEqual(resultado["status"], "RECEBIDO")
        self.assertEqual(self.redis.estado["disponibilidade"], "DISPONIVEL")
        self.assertEqual(self.mongo.saldos["L1"], 7)

    def test_percurso_alterado_apos_previa_nao_reserva_nem_debita(self):
        esperado = deepcopy(self.grafo.percurso)
        self.grafo.percurso["trechos"][0]["distancia_km"] = 30
        self.grafo.percurso["distancia_total_km"] = 30
        with self.assertRaisesRegex(ErroDominio, "mudou"):
            self.sistema.despachar(**self.pedido, percurso_esperado=esperado)
        self.assertEqual(self.mongo.saldos["L1"], 10)
        self.assertEqual(self.redis.estado["disponibilidade"], "DISPONIVEL")

    def test_ausencia_de_percurso_nao_reserva_veiculo(self):
        self.grafo.percurso = None
        with self.assertRaisesRegex(ErroDominio, "Não existe percurso"):
            self.sistema.despachar(**self.pedido)
        self.assertEqual(self.redis.estado["disponibilidade"], "DISPONIVEL")

    def test_nao_sincroniza_recebimento_antes_da_confirmacao(self):
        self.sistema.despachar(**self.pedido)
        with self.assertRaises(ErroDominio):
            self.sistema.sincronizar_recebimento("M1")
        self.assertEqual(self.redis.estado["disponibilidade"], "EM_TRANSPORTE")

    def test_telemetria_simulada_e_identificada_e_atual(self):
        resultado = self.sistema.atualizar_telemetria("V1", -23.5, -46.6, 50, 21)
        self.assertTrue(resultado["demonstracao"])
        self.assertFalse(resultado["desatualizada"])
        self.assertEqual(resultado["velocidade_kmh"], 50)


if __name__ == "__main__":
    unittest.main()
