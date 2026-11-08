"""Validações puras, sem substituir testes dos bancos reais."""

from datetime import datetime, timedelta, timezone
import unittest

from src.dominio import (
    ErroDominio, assinatura_documento, documento_json, normalizar_itens,
    quantidade_positiva, telemetria_com_validade, validar_telemetria,
)


class DominioTests(unittest.TestCase):
    def test_quantidade_discreta_rejeita_fracao_booleano_e_saldo_invalido(self):
        for valor in (0, -1, 0.5, True, "1", None):
            with self.subTest(valor=valor), self.assertRaises(ErroDominio):
                quantidade_positiva(valor)

    def test_nao_aceita_lote_duplicado_no_manifesto(self):
        with self.assertRaisesRegex(ErroDominio, "uma vez"):
            normalizar_itens([{"lote_id": "L1", "quantidade": 1}, {"lote_id": "L1", "quantidade": 2}])

    def test_itens_normalizados_nao_dependem_da_ordem_da_selecao(self):
        itens = [{"lote_id": "L2", "quantidade": 1}, {"lote_id": "L1", "quantidade": 2}]
        self.assertEqual(normalizar_itens(itens), normalizar_itens(list(reversed(itens))))

    def test_documentacao_aceita_json_flexivel_sem_presumir_campos_fiscais(self):
        original = {"demonstracao": True, "observacoes": ["Exemplo", {"livre": 2}]}
        copia = documento_json(original, "Documento")
        copia["observacoes"].append("Outra observação")
        self.assertEqual(len(original["observacoes"]), 2)

    def test_json_rejeita_nao_finitos_e_chaves_que_nao_sao_texto(self):
        for valor in ({"x": float("nan")}, {"x": float("inf")}, {1: "texto"}):
            with self.subTest(valor=valor), self.assertRaises(ErroDominio):
                documento_json(valor, "Documento")

    def test_assinatura_documento_independe_da_ordem_das_chaves(self):
        self.assertEqual(assinatura_documento({"a": 1, "b": 2}), assinatura_documento({"b": 2, "a": 1}))

    def test_telemetria_rejeita_coordenadas_impossiveis(self):
        for parametros in ((91, 0, 0, 0), (0, 181, 0, 0), (0, 0, -1, 0), (0, 0, 0, float("nan"))):
            with self.subTest(parametros=parametros), self.assertRaises(ErroDominio):
                validar_telemetria(*parametros)

    def test_telemetria_expira_apos_trinta_segundos_e_nao_desaparece(self):
        agora = datetime(2026, 10, 26, 15, 0, tzinfo=timezone.utc)
        leitura = {"medido_em": (agora - timedelta(seconds=31)).isoformat(), "velocidade_kmh": 50}
        resultado = telemetria_com_validade(leitura, 30, agora)
        self.assertTrue(resultado["desatualizada"])
        self.assertEqual(resultado["velocidade_kmh"], 50)
        self.assertEqual(resultado["idade_segundos"], 31)

    def test_ausencia_de_telemetria_nao_e_velocidade_zero(self):
        self.assertIsNone(telemetria_com_validade(None, 30))


if __name__ == "__main__":
    unittest.main()
