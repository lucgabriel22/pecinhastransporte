"""Executa unittest e exige bancos disponíveis quando integração é pedida."""

import argparse
from datetime import datetime, timezone
import json
import os
import unittest

from src.configuracao import RAIZ_PROJETO


def main() -> int:
    argumentos = argparse.ArgumentParser()
    argumentos.add_argument("--integracao", action="store_true")
    opcoes = argumentos.parse_args()
    if opcoes.integracao:
        from scripts.verificar import main as verificar_bancos
        from src.configuracao import Configuracao

        if verificar_bancos() != 0:
            print("Integração não executada: inicie os bancos antes de solicitar este teste.")
            return 2
        configuracao = Configuracao.carregar()
        os.environ.update(
            TESTAR_INTEGRACAO="1", TESTAR_NEO4J="1",
            NEO4J_URI=configuracao.neo4j_uri,
            NEO4J_USERNAME=configuracao.neo4j_usuario,
            NEO4J_PASSWORD=configuracao.neo4j_senha,
            NEO4J_DATABASE=configuracao.neo4j_database,
        )
    suite = unittest.defaultTestLoader.discover(str(RAIZ_PROJETO / "tests"))
    resultado = unittest.TextTestRunner(verbosity=2).run(suite)
    pasta = RAIZ_PROJETO / ".estado_local"
    pasta.mkdir(exist_ok=True)
    relatorio = {
        "verificado_em": datetime.now(timezone.utc).isoformat(),
        "integracao_solicitada": opcoes.integracao,
        "descobertos": resultado.testsRun,
        "executados": resultado.testsRun - len(resultado.skipped),
        "ignorados": len(resultado.skipped),
        "falhas": len(resultado.failures),
        "erros": len(resultado.errors),
        "sucesso": resultado.wasSuccessful(),
    }
    (pasta / "testes.json").write_text(json.dumps(relatorio, indent=2), encoding="utf-8")
    return 0 if resultado.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
