"""Validação documental e, quando solicitada, consultas ao Neo4j real.

Integração: definir TESTAR_NEO4J=1 e NEO4J_URI/NEO4J_USERNAME/NEO4J_PASSWORD
em uma base exclusiva de demonstração; a carga é idempotente e não apaga dados.
"""

from copy import deepcopy
import os
import unittest

from src.dados_demo import LOCAIS, TRECHOS
from src.repositorios.neo4j import RepositorioNeo4j, _validar_percurso


def percurso_demonstracao():
    locais = {local["id"]: deepcopy(local) for local in LOCAIS}
    trechos = [deepcopy(trecho) for trecho in TRECHOS if trecho["id"] in ("T1", "T2")]
    return {
        "locais": [locais["DEMO-CD-001"], locais["DEMO-PT-001"], locais["DEMO-CLI-001"]],
        "trechos": trechos,
        "distancia_total_km": 20.0,
    }


class ValidacaoPercursoTests(unittest.TestCase):
    def test_rejeita_trechos_fora_da_ordem_do_percurso(self):
        percurso = percurso_demonstracao()
        percurso["trechos"].reverse()
        with self.assertRaisesRegex(ValueError, "contínua"):
            _validar_percurso(percurso)

    def test_rejeita_total_que_nao_corresponde_aos_trechos(self):
        percurso = percurso_demonstracao()
        percurso["distancia_total_km"] = 1.0
        with self.assertRaisesRegex(ValueError, "soma"):
            _validar_percurso(percurso)

    def test_rejeita_distancias_invalidas(self):
        for distancia in (0, -1, float("inf"), float("nan"), True):
            with self.subTest(distancia=distancia):
                percurso = percurso_demonstracao()
                percurso["trechos"][0]["distancia_km"] = distancia
                with self.assertRaisesRegex(ValueError, "finita e positiva"):
                    _validar_percurso(percurso)

    def test_rejeita_rota_sem_percurso_completo(self):
        percurso = percurso_demonstracao()
        percurso["locais"].pop()
        with self.assertRaisesRegex(ValueError, "sequência completa"):
            _validar_percurso(percurso)


@unittest.skipUnless(os.getenv("TESTAR_NEO4J") == "1", "Integração Neo4j não solicitada")
class RotasNeo4jIntegracaoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from neo4j import GraphDatabase
        cls.driver = GraphDatabase.driver(
            os.environ["NEO4J_URI"],
            auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
        )
        cls.repositorio = RepositorioNeo4j(cls.driver, os.getenv("NEO4J_DATABASE", "neo4j"))
        cls.repositorio.verificar_conexao()
        cls.repositorio.inicializar()
        cls.repositorio.carregar_demonstracao()

    @classmethod
    def tearDownClass(cls):
        cls.driver.close()

    def calcular(self, trechos=None, locais=None, origem="DEMO-CD-001", destino="DEMO-CLI-001"):
        return self.repositorio.calcular_rotas(origem, destino, trechos, locais)

    def test_distingue_menor_distancia_de_menos_trechos(self):
        resultado = self.calcular()
        self.assertEqual(resultado["menor_distancia"]["distancia_total_km"], 20.0)
        self.assertEqual([t["id"] for t in resultado["menor_distancia"]["trechos"]], ["T1", "T2"])
        self.assertEqual(resultado["menos_trechos"]["distancia_total_km"], 30.0)
        self.assertEqual([t["id"] for t in resultado["menos_trechos"]["trechos"]], ["T3"])

    def test_recalcula_apos_bloqueio_de_trecho_ou_transbordo(self):
        for trechos, locais in ((["T2"], []), ([], ["DEMO-PT-001"])):
            with self.subTest(trechos=trechos, locais=locais):
                resultado = self.calcular(trechos, locais)
                self.assertEqual(resultado["menor_distancia"]["distancia_total_km"], 23.0)

    def test_shortestpath_exclui_bloqueio_antes_de_escolher(self):
        resultado = self.calcular(["T3"])
        self.assertIsNotNone(resultado["menos_trechos"])
        self.assertEqual(len(resultado["menos_trechos"]["trechos"]), 2)
        self.assertNotIn("T3", [t["id"] for t in resultado["menos_trechos"]["trechos"]])

    def test_origem_ou_destino_bloqueado_sem_caminho(self):
        for local in ("DEMO-CD-001", "DEMO-CLI-001"):
            self.assertEqual(self.calcular(locais=[local]), {"menor_distancia": None, "menos_trechos": None})

    def test_nao_presume_retorno_dos_trechos(self):
        resultado = self.calcular(origem="DEMO-CLI-001", destino="DEMO-CD-001")
        self.assertEqual(resultado, {"menor_distancia": None, "menos_trechos": None})

    def test_metadados_de_rota_nao_criam_atalho(self):
        resultado = self.calcular(["T1", "T3", "T4"])
        self.assertEqual(resultado, {"menor_distancia": None, "menos_trechos": None})

    def test_registro_com_mesmo_id_nao_sobrescreve_historico(self):
        original = self.calcular()["menor_distancia"]
        rota = self.repositorio.registrar_rota("DEMO-ROT-001", original)
        self.assertEqual(rota["trechos_ids"], ["T1", "T2"])
        alternativo = self.calcular(["T2"])["menor_distancia"]
        with self.assertRaisesRegex(ValueError, "histórico foi preservado"):
            self.repositorio.registrar_rota("DEMO-ROT-001", alternativo)
        rotas = self.repositorio.obter_malha()["rotas"]
        self.assertEqual(next(r for r in rotas if r["id"] == "DEMO-ROT-001")["trechos_ids"], ["T1", "T2"])


if __name__ == "__main__":
    unittest.main()
