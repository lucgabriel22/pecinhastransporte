"""Documentos e transações locais no replica set MongoDB."""

from __future__ import annotations

from copy import deepcopy

from pymongo import ASCENDING, DESCENDING, ReadPreference
from pymongo.errors import DuplicateKeyError, PyMongoError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from src.dominio import ErroDominio, ErroInfraestrutura, agora_utc


class RepositorioMongo:
    def __init__(self, database):
        self.database = database.with_options(
            read_concern=ReadConcern("majority"),
            write_concern=WriteConcern(w="majority", j=True),
            read_preference=ReadPreference.PRIMARY,
        )

    def verificar_conexao(self):
        try:
            self.database.client.admin.command("ping")
            hello = self.database.client.admin.command("hello")
            if not hello.get("setName") or not hello.get("isWritablePrimary"):
                raise ErroInfraestrutura("MongoDB precisa de um replica set com primário disponível.")
            return "Replica set acessível; transações habilitadas."
        except PyMongoError as exc:
            raise ErroInfraestrutura("MongoDB indisponível. Confira o Docker Compose e a inicialização do replica set.") from exc

    def inicializar(self):
        esquemas = {
            "mercadorias": {
                "required": ["_id", "descricao", "especificacoes_tecnicas", "especificacoes_fiscais", "demonstracao"],
                "properties": {"_id": {"bsonType": "string"}, "descricao": {"bsonType": "string", "minLength": 1},
                               "especificacoes_tecnicas": {"bsonType": "object"},
                               "especificacoes_fiscais": {"bsonType": "object"}, "demonstracao": {"bsonType": "bool"}},
            },
            "lotes": {
                "required": ["_id", "mercadoria_id", "quantidade", "unidade", "local_id", "demonstracao"],
                "properties": {"_id": {"bsonType": "string"}, "mercadoria_id": {"bsonType": "string"},
                               "quantidade": {"bsonType": ["int", "long"], "minimum": 0},
                               "unidade": {"bsonType": "string", "minLength": 1}, "local_id": {"bsonType": "string"},
                               "demonstracao": {"bsonType": "bool"}},
            },
            "manifestos": {
                "required": ["_id", "status", "assinatura_solicitacao", "itens", "veiculo_id", "percurso", "despacho", "demonstracao"],
                "properties": {"_id": {"bsonType": "string"}, "status": {"enum": ["DESPACHADO", "RECEBIDO"]},
                               "assinatura_solicitacao": {"bsonType": "string"}, "itens": {"bsonType": "array", "minItems": 1},
                               "veiculo_id": {"bsonType": "string"}, "percurso": {"bsonType": "object"},
                               "documentacao_carga": {"bsonType": "object"}, "despacho": {"bsonType": "object"},
                               "recebimento": {"bsonType": ["object", "null"]}, "demonstracao": {"bsonType": "bool"}},
            },
            "auditoria": {
                "required": ["_id", "operacao_id", "entidade_tipo", "entidade_id", "acao", "ocorrido_em", "detalhes", "demonstracao"],
                "properties": {"_id": {"bsonType": "string"}, "operacao_id": {"bsonType": "string"},
                               "entidade_tipo": {"bsonType": "string"}, "entidade_id": {"bsonType": "string"},
                               "acao": {"bsonType": "string"}, "ocorrido_em": {"bsonType": "date"},
                               "detalhes": {"bsonType": "object"}, "demonstracao": {"bsonType": "bool"}},
            },
        }
        try:
            existentes = set(self.database.list_collection_names())
            for nome, esquema in esquemas.items():
                validator = {"$jsonSchema": {"bsonType": "object", **esquema}}
                if nome in existentes:
                    self.database.command("collMod", nome, validator=validator, validationLevel="strict")
                else:
                    self.database.create_collection(nome, validator=validator, validationLevel="strict")
            self.database.lotes.create_index([("mercadoria_id", ASCENDING)])
            self.database.lotes.create_index([("local_id", ASCENDING)])
            self.database.manifestos.create_index([("veiculo_id", ASCENDING), ("despacho.confirmado_em", DESCENDING)])
            self.database.manifestos.create_index([("status", ASCENDING)])
            self.database.manifestos.create_index(
                [("veiculo_id", ASCENDING)], unique=True,
                partialFilterExpression={"status": "DESPACHADO"}, name="veiculo_com_um_manifesto_ativo",
            )
            self.database.auditoria.create_index([("entidade_id", ASCENDING), ("ocorrido_em", DESCENDING)])
            self.database.auditoria.create_index([("acao", ASCENDING), ("ocorrido_em", DESCENDING)])
        except PyMongoError as exc:
            raise ErroInfraestrutura("Não foi possível inicializar coleções e índices do MongoDB.") from exc

    def _listar(self, colecao, filtro=None, ordenacao=None):
        try:
            cursor = self.database[colecao].find(filtro or {})
            return list(cursor.sort(ordenacao or [("_id", ASCENDING)]))
        except PyMongoError as exc:
            raise ErroInfraestrutura(f"Não foi possível consultar {colecao} no MongoDB.") from exc

    def listar_mercadorias(self):
        return self._listar("mercadorias")

    def listar_lotes(self):
        return self._listar("lotes")

    def listar_manifestos(self):
        return self._listar("manifestos", ordenacao=[("despacho.confirmado_em", DESCENDING)])

    def listar_auditoria(self):
        return self._listar("auditoria", ordenacao=[("ocorrido_em", DESCENDING)])

    def listar_auditoria_alertas(self):
        return self._listar("auditoria", {"acao": "ALERTA_SIMULADO"}, [("ocorrido_em", DESCENDING)])

    def obter_manifesto(self, manifesto_id):
        try:
            return self.database.manifestos.find_one({"_id": manifesto_id})
        except PyMongoError as exc:
            raise ErroInfraestrutura("Não foi possível conferir o manifesto. Preserve o ID e repita a operação.") from exc

    def cadastrar_mercadoria(self, documento):
        try:
            self.database.mercadorias.insert_one(documento)
            return documento["_id"]
        except PyMongoError as exc:
            raise ErroInfraestrutura("Não foi possível cadastrar a mercadoria no MongoDB.") from exc

    def cadastrar_lote(self, documento):
        try:
            if not self.database.mercadorias.find_one({"_id": documento["mercadoria_id"]}, {"_id": 1}):
                raise ErroDominio("A mercadoria selecionada não existe.")
            self.database.lotes.insert_one(documento)
            return documento["_id"]
        except PyMongoError as exc:
            raise ErroInfraestrutura("Não foi possível cadastrar o lote no MongoDB.") from exc

    def _transacao(self, executar):
        try:
            with self.database.client.start_session() as session:
                return session.with_transaction(
                    executar,
                    read_concern=ReadConcern("snapshot"),
                    write_concern=WriteConcern(w="majority", j=True),
                    read_preference=ReadPreference.PRIMARY,
                )
        except DuplicateKeyError:
            # A operação chamadora confere se outra execução já confirmou o mesmo ID.
            raise
        except PyMongoError as exc:
            # Não compensar aqui: um erro de comunicação pode ocultar commit bem-sucedido.
            raise ErroInfraestrutura(
                "Não foi possível confirmar o resultado da transação MongoDB. "
                "Preserve o ID do manifesto e repita a mesma ação para conferir o resultado."
            ) from exc

    def confirmar_despacho(self, documento):
        def executar(session):
            existente = self.database.manifestos.find_one({"_id": documento["_id"]}, session=session)
            if existente:
                if existente["assinatura_solicitacao"] != documento["assinatura_solicitacao"]:
                    raise ErroDominio("Este ID de manifesto já foi utilizado com outros dados.")
                return existente
            for item in documento["itens"]:
                atualizado = self.database.lotes.update_one(
                    {"_id": item["lote_id"], "local_id": documento["origem_id"], "quantidade": {"$gte": item["quantidade"]}},
                    {"$inc": {"quantidade": -item["quantidade"]}}, session=session,
                )
                if atualizado.modified_count != 1:
                    raise ErroDominio(f"Lote {item['lote_id']} ausente na origem ou com saldo insuficiente.")
            self.database.manifestos.insert_one(deepcopy(documento), session=session)
            self.database.auditoria.insert_one({
                "_id": documento["despacho"]["operacao_id"], "operacao_id": documento["despacho"]["operacao_id"],
                "entidade_tipo": "manifesto", "entidade_id": documento["_id"], "acao": "DESPACHO_CONFIRMADO",
                "ocorrido_em": documento["despacho"]["confirmado_em"],
                "detalhes": {"itens": documento["itens"], "veiculo_id": documento["veiculo_id"], "origem_id": documento["origem_id"]},
                "demonstracao": True,
            }, session=session)
            return deepcopy(documento)
        try:
            return self._transacao(executar)
        except DuplicateKeyError as exc:
            existente = self.obter_manifesto(documento["_id"])
            if existente and existente["assinatura_solicitacao"] == documento["assinatura_solicitacao"]:
                return existente
            raise ErroDominio("Conflito de identificação ou veículo com outro manifesto em transporte. Confira os manifestos.") from exc

    def confirmar_recebimento(self, manifesto_id):
        def executar(session):
            manifesto = self.database.manifestos.find_one({"_id": manifesto_id}, session=session)
            if not manifesto:
                raise ErroDominio("Manifesto não encontrado.")
            if manifesto["status"] == "RECEBIDO":
                return manifesto
            recebimento = {"operacao_id": f"recebimento:{manifesto_id}", "confirmado_em": agora_utc(), "integral": True}
            self.database.manifestos.update_one(
                {"_id": manifesto_id, "status": "DESPACHADO"},
                {"$set": {"status": "RECEBIDO", "recebimento": recebimento, "sincronizacao_redis": "PENDENTE"}},
                session=session,
            )
            self.database.auditoria.insert_one({
                "_id": recebimento["operacao_id"], "operacao_id": recebimento["operacao_id"],
                "entidade_tipo": "manifesto", "entidade_id": manifesto_id, "acao": "RECEBIMENTO_INTEGRAL_CONFIRMADO",
                "ocorrido_em": recebimento["confirmado_em"], "detalhes": {"itens": manifesto["itens"], "veiculo_id": manifesto["veiculo_id"]},
                "demonstracao": True,
            }, session=session)
            manifesto.update(status="RECEBIDO", recebimento=recebimento, sincronizacao_redis="PENDENTE")
            return manifesto
        try:
            return self._transacao(executar)
        except DuplicateKeyError as exc:
            existente = self.obter_manifesto(manifesto_id)
            if existente and existente["status"] == "RECEBIDO":
                return existente
            raise ErroInfraestrutura("O recebimento concorrente exige conferência. Repita a confirmação com o mesmo ID.") from exc

    def marcar_sincronizacao(self, manifesto_id, status, estado_esperado=None):
        try:
            filtro = {"_id": manifesto_id}
            if estado_esperado:
                filtro["status"] = estado_esperado
            resultado = self.database.manifestos.update_one(filtro, {"$set": {"sincronizacao_redis": status}})
            if not resultado.matched_count:
                raise ErroInfraestrutura("O manifesto mudou durante a sincronização. Atualize a consulta para conferir o estado atual.")
        except PyMongoError as exc:
            raise ErroInfraestrutura("O estado no Redis foi atualizado, mas o marcador no MongoDB exige nova conferência.") from exc

    def registrar_alerta(self, evento):
        try:
            self.database.auditoria.update_one({"_id": evento["evento_id"]}, {"$setOnInsert": {
                "operacao_id": evento["evento_id"], "entidade_tipo": "veiculo", "entidade_id": evento["veiculo_id"],
                "acao": "ALERTA_SIMULADO", "ocorrido_em": agora_utc(), "detalhes": deepcopy(evento), "demonstracao": True,
            }}, upsert=True)
        except PyMongoError as exc:
            raise ErroInfraestrutura("Não foi possível registrar a auditoria do alerta; a publicação não foi iniciada.") from exc

    def atualizar_publicacao_alerta(self, evento_id, status, assinantes=0):
        try:
            self.database.auditoria.update_one({"_id": evento_id}, {"$set": {
                "detalhes.publicacao": status, "detalhes.assinantes_no_canal": assinantes,
            }})
        except PyMongoError as exc:
            raise ErroInfraestrutura("O resultado da publicação do alerta não pôde ser atualizado na auditoria.") from exc
