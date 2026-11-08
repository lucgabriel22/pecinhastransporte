"""Inicializa estruturas e insere os dados fictícios que ainda não existem."""

import sys

from src.bootstrap import criar_sistema
from src.dados_demo import LOTES, MERCADORIAS, VEICULOS


def inicializar_sistema(sistema) -> None:
    falhas = [banco["banco"] for banco in sistema.verificar_conexoes() if not banco["ok"]]
    if falhas:
        raise RuntimeError("Bancos indisponíveis: " + ", ".join(falhas))
    sistema.mongo.inicializar()
    sistema.neo4j.inicializar()
    sistema.neo4j.carregar_demonstracao()
    banco = sistema.mongo.database
    for mercadoria in MERCADORIAS:
        banco.mercadorias.update_one({"_id": mercadoria["_id"]}, {"$setOnInsert": mercadoria}, upsert=True)
    for lote in LOTES:
        banco.lotes.update_one({"_id": lote["_id"]}, {"$setOnInsert": lote}, upsert=True)
    for veiculo in VEICULOS:
        sistema.redis.inicializar_veiculo(veiculo["id"], veiculo["nome"])
        if not sistema.obter_telemetria(veiculo["id"]):
            sistema.atualizar_telemetria(
                veiculo["id"], veiculo["latitude"], veiculo["longitude"],
                veiculo["velocidade_kmh"], veiculo["temperatura_c"],
            )
    # Redis pode ter sido reinicializado separadamente. O histórico MongoDB
    # continua impedindo que um veículo em transporte apareça como disponível.
    for manifesto in sistema.listar_manifestos():
        if manifesto["status"] != "DESPACHADO":
            continue
        if not sistema.redis.obter_estado(manifesto["veiculo_id"]):
            sistema.redis.inicializar_veiculo(
                manifesto["veiculo_id"], f"Veículo de demonstração {manifesto['veiculo_id']}",
            )
        resultado = sistema.sincronizar_despacho(manifesto["_id"])
        if resultado.get("sincronizacao_redis") != "SINCRONIZADO":
            raise RuntimeError(
                f"Manifesto {manifesto['_id']} em transporte com estado conflitante ou pendente no Redis. "
                "A associação existente foi preservada; confira a sincronização antes de novos despachos."
            )


def main() -> int:
    sistema = None
    try:
        sistema = criar_sistema()
        inicializar_sistema(sistema)
    except Exception as erro:
        print(f"Inicialização não concluída: {erro}", file=sys.stderr)
        return 1
    finally:
        if sistema is not None:
            sistema.fechar()
    print("Estruturas e dados de demonstração preparados; cadastros e saldos existentes preservados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
