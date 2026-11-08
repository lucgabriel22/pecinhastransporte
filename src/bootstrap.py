"""Composição dos clientes reais usados pela aplicação e pelos scripts."""

import atexit

from neo4j import GraphDatabase
from pymongo import MongoClient
from redis import Redis

from src.configuracao import Configuracao
from src.repositorios.mongo import RepositorioMongo
from src.repositorios.neo4j import RepositorioNeo4j
from src.repositorios.redis import RepositorioRedis
from src.servicos.sistema import SistemaLogistico


def criar_sistema(configuracao: Configuracao | None = None) -> SistemaLogistico:
    configuracao = configuracao or Configuracao.carregar()
    mongo = MongoClient(
        configuracao.mongo_uri,
        serverSelectionTimeoutMS=3000,
        connectTimeoutMS=3000,
        tz_aware=True,
        maxPoolSize=10,
    )
    redis = Redis.from_url(
        configuracao.redis_url,
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,
        max_connections=12,
    )
    neo4j = GraphDatabase.driver(
        configuracao.neo4j_uri,
        auth=(configuracao.neo4j_usuario, configuracao.neo4j_senha),
        connection_timeout=3,
        connection_acquisition_timeout=5,
        max_connection_pool_size=10,
    )
    sistema = SistemaLogistico(
        RepositorioMongo(mongo[configuracao.mongo_database]),
        RepositorioRedis(redis, prefixo=configuracao.redis_prefixo),
        RepositorioNeo4j(neo4j, database=configuracao.neo4j_database),
        validade_telemetria_segundos=configuracao.telemetria_validade_segundos,
    )
    sistema.configuracao = configuracao
    atexit.register(mongo.close)
    atexit.register(redis.close)
    atexit.register(neo4j.close)
    atexit.register(sistema.fechar)
    return sistema
