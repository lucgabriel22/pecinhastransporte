"""Malha dirigida e percursos completos, sem APOC ou Graph Data Science.

A soma de caminhos em Cypher é adequada à pequena malha de demonstração.
Enumerar caminhos pode ter custo exponencial em grafos maiores; não há limite
arbitrário de saltos, que poderia excluir o percurso de menor distância.
"""

from __future__ import annotations

from functools import wraps
from math import isclose, isfinite
from typing import Any

from neo4j.exceptions import DriverError, Neo4jError

from src.dados_demo import LOCAIS, ROTAS, TRECHOS
from src.dominio import ErroInfraestrutura


TIPOS_LOCAIS = ("CentroDistribuição", "PontoTransbordo", "Cliente")


def _tratar_falha(funcao):
    @wraps(funcao)
    def executar(*args, **kwargs):
        try:
            return funcao(*args, **kwargs)
        except (DriverError, Neo4jError) as erro:
            raise ErroInfraestrutura(
                "Não foi possível concluir a operação no Neo4j. Confira a conexão e a malha antes de repetir."
            ) from erro
    return executar


def _projecao_local(variavel: str) -> str:
    """A variável vem apenas das consultas constantes deste módulo."""
    return (
        f"{{id: {variavel}.id, nome: coalesce({variavel}.nome, {variavel}.id), "
        f"tipo: head([tipo IN labels({variavel}) WHERE tipo IN $tipos]), "
        f"operante: coalesce({variavel}.operante, false), "
        f"x: coalesce({variavel}.x, 0.5), y: coalesce({variavel}.y, 0.5), "
        f"demonstracao: coalesce({variavel}.demonstracao, false)}}"
    )


_PROJECAO_TRECHO = """{
    id: t.id, origem_id: startNode(t).id, destino_id: endNode(t).id,
    distancia_km: t.distancia_km, operante: coalesce(t.operante, false),
    demonstracao: coalesce(t.demonstracao, false)
}"""

_FILTROS_CAMINHO = """
    all(n IN nodes(caminho) WHERE n.operante = true
        AND NOT n.id IN $locais_bloqueados
        AND any(tipo IN labels(n) WHERE tipo IN $tipos))
    AND all(t IN relationships(caminho) WHERE t.operante = true
        AND t.distancia_km > 0 AND NOT t.id IN $trechos_bloqueados)
"""

_RETORNO_CAMINHO = f"""
    [n IN nodes(caminho) | {_projecao_local('n')}] AS locais,
    [t IN relationships(caminho) | {_PROJECAO_TRECHO}] AS trechos,
    reduce(total = 0.0, t IN relationships(caminho) |
        total + t.distancia_km) AS distancia_total_km
"""

_MENOR_DISTANCIA = f"""
    MATCH (origem {{id: $origem_id}}), (destino {{id: $destino_id}})
    WHERE any(tipo IN labels(origem) WHERE tipo IN $tipos)
      AND any(tipo IN labels(destino) WHERE tipo IN $tipos)
    MATCH caminho = (origem)-[:TRECHO*1..]->(destino)
    WHERE {_FILTROS_CAMINHO}
    RETURN {_RETORNO_CAMINHO}
    ORDER BY distancia_total_km, size(trechos), [t IN trechos | t.id]
    LIMIT 1
"""

# O WHERE pertence ao próprio MATCH de shortestPath: os filtros universais
# participam da busca, em vez de descartar um único caminho escolhido antes.
_MENOS_TRECHOS = f"""
    MATCH (origem {{id: $origem_id}}), (destino {{id: $destino_id}})
    WHERE any(tipo IN labels(origem) WHERE tipo IN $tipos)
      AND any(tipo IN labels(destino) WHERE tipo IN $tipos)
    MATCH caminho = shortestPath((origem)-[:TRECHO*1..]->(destino))
    WHERE {_FILTROS_CAMINHO}
    RETURN {_RETORNO_CAMINHO}
"""


def _validar_percurso(percurso: dict[str, Any]) -> None:
    """Rejeita documentação descontínua ou com distâncias inconsistentes."""
    locais = percurso.get("locais", [])
    trechos = percurso.get("trechos", [])
    if not trechos or len(locais) != len(trechos) + 1:
        raise ValueError("O percurso precisa de trechos e de sua sequência completa de locais.")
    if any(not isinstance(local.get("id"), str) or not local["id"].strip() for local in locais):
        raise ValueError("Todo local do percurso precisa de um identificador.")
    total = 0.0
    for indice, trecho in enumerate(trechos):
        if not isinstance(trecho.get("id"), str) or not trecho["id"].strip():
            raise ValueError("Todo trecho precisa de um identificador.")
        if (trecho.get("origem_id") != locais[indice]["id"]
                or trecho.get("destino_id") != locais[indice + 1]["id"]):
            raise ValueError("A sequência de trechos do percurso não é contínua.")
        distancia = trecho.get("distancia_km")
        if (isinstance(distancia, bool) or not isinstance(distancia, (int, float))
                or not isfinite(distancia) or distancia <= 0):
            raise ValueError("A distância de cada trecho deve ser finita e positiva.")
        total += distancia
    informado = percurso.get("distancia_total_km")
    if (isinstance(informado, bool) or not isinstance(informado, (int, float))
            or not isfinite(informado) or not isclose(total, informado, rel_tol=1e-9, abs_tol=1e-9)):
        raise ValueError("A distância total não corresponde à soma dos trechos.")


class RepositorioNeo4j:
    def __init__(self, driver: Any, database: str = "neo4j") -> None:
        self._driver = driver
        self._database = database

    @_tratar_falha
    def verificar_conexao(self) -> None:
        self._driver.verify_connectivity()
        with self._driver.session(database=self._database) as sessao:
            sessao.run("RETURN 1 AS disponivel").consume()

    @_tratar_falha
    def inicializar(self) -> None:
        with self._driver.session(database=self._database) as sessao:
            for indice, rotulo in enumerate((*TIPOS_LOCAIS, "Rota")):
                sessao.run(
                    f"CREATE CONSTRAINT logistica_no_{indice}_id IF NOT EXISTS "
                    f"FOR (n:`{rotulo}`) REQUIRE n.id IS UNIQUE"
                ).consume()
            sessao.run(
                "CREATE CONSTRAINT logistica_trecho_id IF NOT EXISTS "
                "FOR ()-[t:TRECHO]-() REQUIRE t.id IS UNIQUE"
            ).consume()

    @_tratar_falha
    def obter_malha(self) -> dict[str, list[dict[str, Any]]]:
        with self._driver.session(database=self._database) as sessao:
            return sessao.execute_read(self._ler_malha)

    @staticmethod
    def _ler_malha(tx: Any) -> dict[str, list[dict[str, Any]]]:
        locais = [registro["local"] for registro in tx.run(
            f"MATCH (n) WHERE any(tipo IN labels(n) WHERE tipo IN $tipos) "
            f"RETURN {_projecao_local('n')} AS local ORDER BY local.id",
            tipos=list(TIPOS_LOCAIS),
        )]
        ids = [local["id"] for local in locais]
        if len(ids) != len(set(ids)):
            raise ValueError("Há IDs de locais repetidos entre os rótulos da malha.")
        trechos = [registro["trecho"] for registro in tx.run(
            f"MATCH (a)-[t:TRECHO]->(b) "
            "WHERE any(tipo IN labels(a) WHERE tipo IN $tipos) "
            "AND any(tipo IN labels(b) WHERE tipo IN $tipos) "
            f"RETURN {_PROJECAO_TRECHO} AS trecho ORDER BY trecho.id",
            tipos=list(TIPOS_LOCAIS),
        )]
        rotas = [registro["rota"] for registro in tx.run(
            "MATCH (r:Rota) "
            "OPTIONAL MATCH (r)-[:TEM_ORIGEM]->(origem) "
            "OPTIONAL MATCH (r)-[:TEM_DESTINO]->(destino) "
            "RETURN r{.*, origem_id: origem.id, destino_id: destino.id} AS rota "
            "ORDER BY rota.id"
        )]
        return {"locais": locais, "trechos": trechos, "rotas": rotas}

    @_tratar_falha
    def calcular_rotas(
        self, origem_id: str, destino_id: str,
        trechos_bloqueados: list[str] | None = None,
        locais_bloqueados: list[str] | None = None,
    ) -> dict[str, dict[str, Any] | None]:
        parametros = {
            "origem_id": origem_id, "destino_id": destino_id,
            "trechos_bloqueados": trechos_bloqueados or [],
            "locais_bloqueados": locais_bloqueados or [],
            "tipos": list(TIPOS_LOCAIS),
        }
        vazio = {"menor_distancia": None, "menos_trechos": None}
        if not origem_id or not destino_id or origem_id == destino_id:
            return vazio
        if origem_id in parametros["locais_bloqueados"] or destino_id in parametros["locais_bloqueados"]:
            return vazio
        with self._driver.session(database=self._database) as sessao:
            return sessao.execute_read(self._calcular, parametros)

    @staticmethod
    def _calcular(tx: Any, parametros: dict[str, Any]) -> dict[str, Any]:
        resultado = {}
        for nome, consulta in (("menor_distancia", _MENOR_DISTANCIA), ("menos_trechos", _MENOS_TRECHOS)):
            registro = tx.run(consulta, **parametros).single()
            resultado[nome] = dict(registro) if registro is not None else None
        return resultado

    @_tratar_falha
    def registrar_rota(self, rota_id: str, percurso: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(rota_id, str) or not rota_id.strip():
            raise ValueError("Informe um identificador para a rota completa.")
        _validar_percurso(percurso)
        with self._driver.session(database=self._database) as sessao:
            return sessao.execute_write(self._registrar_rota, rota_id, percurso)

    @staticmethod
    def _registrar_rota(tx: Any, rota_id: str, percurso: dict[str, Any]) -> dict[str, Any]:
        trechos_ids = [trecho["id"] for trecho in percurso["trechos"]]
        registros = list(tx.run(
            "UNWIND range(0, size($trechos_ids) - 1) AS indice "
            "MATCH (a)-[t:TRECHO]->(b) WHERE t.id = $trechos_ids[indice] "
            "AND any(tipo IN labels(a) WHERE tipo IN $tipos) "
            "AND any(tipo IN labels(b) WHERE tipo IN $tipos) "
            f"RETURN indice, {_projecao_local('a')} AS origem, "
            f"{_projecao_local('b')} AS destino, {_PROJECAO_TRECHO} AS trecho "
            "ORDER BY indice",
            trechos_ids=trechos_ids, tipos=list(TIPOS_LOCAIS),
        ))
        if len(registros) != len(trechos_ids):
            raise ValueError("Um trecho do percurso não existe mais ou possui ID duplicado.")
        atuais = {
            "locais": [registros[0]["origem"]] + [r["destino"] for r in registros],
            "trechos": [r["trecho"] for r in registros],
            "distancia_total_km": sum(r["trecho"]["distancia_km"] for r in registros),
        }
        _validar_percurso(atuais)
        if (any(not local["operante"] for local in atuais["locais"])
                or any(not trecho["operante"] for trecho in atuais["trechos"])):
            raise ValueError("O percurso contém local ou trecho inoperante na malha atual.")
        mesmos_locais = [n["id"] for n in atuais["locais"]] == [n["id"] for n in percurso["locais"]]
        mesmas_distancias = all(
            isclose(atual["distancia_km"], anterior["distancia_km"], rel_tol=1e-9, abs_tol=1e-9)
            for atual, anterior in zip(atuais["trechos"], percurso["trechos"])
        )
        if not mesmos_locais or not mesmas_distancias:
            raise ValueError("A malha mudou. Recalcule o percurso antes de registrar o despacho.")
        parametros = {
            "rota_id": rota_id, "trechos_ids": trechos_ids,
            "distancia_total_km": float(atuais["distancia_total_km"]),
            "origem_id": atuais["locais"][0]["id"],
            "destino_id": atuais["locais"][-1]["id"],
            "demonstracao": all(n.get("demonstracao", False) for n in atuais["locais"])
                and all(t.get("demonstracao", False) for t in atuais["trechos"]),
        }
        registro = tx.run(
            "MATCH (origem {id: $origem_id}), (destino {id: $destino_id}) "
            "WHERE any(tipo IN labels(origem) WHERE tipo IN $tipos) "
            "AND any(tipo IN labels(destino) WHERE tipo IN $tipos) "
            "MERGE (r:Rota {id: $rota_id}) "
            "ON CREATE SET r.trechos_ids = $trechos_ids, "
            "r.distancia_total_km = $distancia_total_km, r.demonstracao = $demonstracao "
            "WITH r, origem, destino "
            "WHERE r.trechos_ids = $trechos_ids AND r.distancia_total_km = $distancia_total_km "
            "AND NOT EXISTS { MATCH (r)-[:TEM_ORIGEM]->(outro) WHERE outro <> origem } "
            "AND NOT EXISTS { MATCH (r)-[:TEM_DESTINO]->(outro) WHERE outro <> destino } "
            "MERGE (r)-[:TEM_ORIGEM]->(origem) "
            "MERGE (r)-[:TEM_DESTINO]->(destino) "
            "RETURN r{.*, origem_id: origem.id, destino_id: destino.id} AS rota",
            **parametros, tipos=list(TIPOS_LOCAIS),
        ).single()
        if registro is None:
            raise ValueError("O identificador da rota já pertence a outro percurso. O histórico foi preservado.")
        return dict(registro["rota"])

    @_tratar_falha
    def carregar_demonstracao(self) -> None:
        with self._driver.session(database=self._database) as sessao:
            sessao.execute_write(self._carregar_demonstracao)

    @staticmethod
    def _carregar_demonstracao(tx: Any) -> None:
        for local in LOCAIS:
            existente = tx.run(
                "MATCH (n {id: $id}) WHERE any(tipo IN labels(n) WHERE tipo IN $tipos) "
                "RETURN labels(n) AS rotulos",
                id=local["id"], tipos=list(TIPOS_LOCAIS),
            ).single()
            if existente is not None and local["tipo"] not in existente["rotulos"]:
                raise ValueError("Um ID da demonstração já pertence a outro tipo de local.")
            propriedades = {chave: valor for chave, valor in local.items() if chave != "tipo"}
            tx.run(
                f"MERGE (n:`{local['tipo']}` {{id: $id}}) ON CREATE SET n += $propriedades",
                id=local["id"], propriedades=propriedades,
            ).consume()
        for trecho in TRECHOS:
            propriedades = {chave: valor for chave, valor in trecho.items() if chave not in ("origem_id", "destino_id")}
            # Um ID existente não autoriza reconstruir ou reativar sua relação.
            existe = tx.run("MATCH ()-[t:TRECHO {id: $id}]->() RETURN t.id AS id", id=trecho["id"]).single()
            if existe is None:
                tx.run(
                    "MATCH (origem {id: $origem_id}), (destino {id: $destino_id}) "
                    "WHERE any(tipo IN labels(origem) WHERE tipo IN $tipos) "
                    "AND any(tipo IN labels(destino) WHERE tipo IN $tipos) "
                    "CREATE (origem)-[t:TRECHO]->(destino) SET t = $propriedades",
                    origem_id=trecho["origem_id"], destino_id=trecho["destino_id"],
                    propriedades=propriedades, tipos=list(TIPOS_LOCAIS),
                ).consume()
        locais_por_id = {local["id"]: local for local in LOCAIS}
        trechos_por_id = {trecho["id"]: trecho for trecho in TRECHOS}
        for rota in ROTAS:
            if tx.run("MATCH (r:Rota {id: $id}) RETURN r.id AS id", id=rota["id"]).single() is not None:
                continue
            trechos = [trechos_por_id[id_trecho] for id_trecho in rota["trechos_ids"]]
            percurso = {
                "locais": [locais_por_id[trechos[0]["origem_id"]]]
                    + [locais_por_id[trecho["destino_id"]] for trecho in trechos],
                "trechos": trechos,
                "distancia_total_km": rota["distancia_total_km"],
            }
            RepositorioNeo4j._registrar_rota(tx, rota["id"], percurso)
