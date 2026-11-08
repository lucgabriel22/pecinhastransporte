"""Verifica os bancos reais e grava um relatório local sem credenciais."""

from datetime import datetime, timezone
import json
import sys

from src.bootstrap import criar_sistema
from src.configuracao import RAIZ_PROJETO


def main() -> int:
    sistema = None
    try:
        sistema = criar_sistema()
        resultados = sistema.verificar_conexoes()
        for resultado in resultados:
            situacao = "OK" if resultado["ok"] else "INDISPONÍVEL"
            print(f"{resultado['banco']}: {situacao}")
        relatorio = {
            "verificado_em": datetime.now(timezone.utc).isoformat(),
            "bancos": [{"banco": item["banco"], "ok": item["ok"]} for item in resultados],
        }
        pasta = RAIZ_PROJETO / ".estado_local"
        pasta.mkdir(exist_ok=True)
        (pasta / "bancos.json").write_text(json.dumps(relatorio, indent=2), encoding="utf-8")
        return 0 if all(item["ok"] for item in resultados) else 1
    except Exception as erro:
        print(f"Verificação não concluída: {erro}", file=sys.stderr)
        return 1
    finally:
        if sistema is not None:
            sistema.fechar()


if __name__ == "__main__":
    raise SystemExit(main())
