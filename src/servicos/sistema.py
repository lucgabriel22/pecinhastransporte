"""Orquestração dos fluxos, com recuperação explícita entre bancos."""

from __future__ import annotations

from copy import deepcopy

from src.dominio import (
    ErroDominio, ErroInfraestrutura, agora_utc, assinatura_documento,
    assinatura_percurso, documento_json, ids_bloqueados, normalizar_itens,
    novo_id, quantidade_positiva, telemetria_com_validade, texto_obrigatorio,
    validar_telemetria,
)


class SistemaLogistico:
    def __init__(self, mongo, redis, neo4j, validade_telemetria_segundos=30):
        self.mongo = mongo
        self.redis = redis
        self.neo4j = neo4j
        self.validade_telemetria_segundos = validade_telemetria_segundos

    def verificar_conexoes(self):
        resultado = []
        for banco, repositorio in (("MongoDB", self.mongo), ("Redis", self.redis), ("Neo4j", self.neo4j)):
            try:
                detalhe = repositorio.verificar_conexao()
                resultado.append({"banco": banco, "ok": True, "detalhe": detalhe or "Conexão disponível."})
            except Exception:
                # Não apresentar mensagens de drivers que possam conter URI/credenciais.
                resultado.append({"banco": banco, "ok": False, "detalhe": "Conexão indisponível. Confira a configuração e os contêineres."})
        return resultado

    def listar_mercadorias(self):
        return self.mongo.listar_mercadorias()

    def listar_lotes(self):
        return self.mongo.listar_lotes()

    def listar_manifestos(self):
        return self.mongo.listar_manifestos()

    def listar_veiculos(self):
        veiculos = self.redis.listar_veiculos()
        for veiculo in veiculos:
            veiculo["telemetria"] = telemetria_com_validade(veiculo.get("telemetria"), self.validade_telemetria_segundos)
        return veiculos

    def obter_telemetria(self, veiculo_id):
        return telemetria_com_validade(self.redis.obter_telemetria(veiculo_id), self.validade_telemetria_segundos)

    def obter_malha(self):
        return self.neo4j.obter_malha()

    def cadastrar_mercadoria(self, descricao, especificacoes_tecnicas, especificacoes_fiscais):
        documento = {
            "_id": novo_id("MER"), "descricao": texto_obrigatorio(descricao, "a descrição da mercadoria"),
            "especificacoes_tecnicas": documento_json(especificacoes_tecnicas, "Especificações técnicas"),
            "especificacoes_fiscais": documento_json(especificacoes_fiscais, "Especificações fiscais"),
            "criado_em": agora_utc(), "demonstracao": True,
        }
        return self.mongo.cadastrar_mercadoria(documento)

    def cadastrar_lote(self, mercadoria_id, quantidade, unidade, local_id):
        local_id = texto_obrigatorio(local_id, "o local do lote")
        locais = self.obter_malha()["locais"]
        if not any(local["id"] == local_id for local in locais):
            raise ErroDominio("O local informado não existe na malha logística.")
        documento = {
            "_id": novo_id("LOT"), "mercadoria_id": texto_obrigatorio(mercadoria_id, "a mercadoria"),
            "quantidade": quantidade_positiva(quantidade), "unidade": texto_obrigatorio(unidade, "a unidade de medida"),
            "local_id": local_id, "criado_em": agora_utc(), "demonstracao": True,
        }
        return self.mongo.cadastrar_lote(documento)

    def calcular_rotas(self, origem_id, destino_id, trechos_bloqueados=None, locais_bloqueados=None):
        origem_id = texto_obrigatorio(origem_id, "a origem")
        destino_id = texto_obrigatorio(destino_id, "o destino")
        if origem_id == destino_id:
            raise ErroDominio("Escolha locais diferentes para origem e destino.")
        try:
            return self.neo4j.calcular_rotas(origem_id, destino_id, ids_bloqueados(trechos_bloqueados), ids_bloqueados(locais_bloqueados))
        except ValueError as exc:
            raise ErroDominio(str(exc)) from exc

    def despachar(self, manifesto_id, veiculo_id, origem_id, destino_id, itens,
                  documentacao_carga, trechos_bloqueados=None, locais_bloqueados=None,
                  percurso_esperado=None):
        manifesto_id = texto_obrigatorio(manifesto_id, "o ID do manifesto")
        solicitacao = {
            "veiculo_id": texto_obrigatorio(veiculo_id, "o veículo"),
            "origem_id": texto_obrigatorio(origem_id, "a origem"),
            "destino_id": texto_obrigatorio(destino_id, "o destino"),
            "itens": normalizar_itens(itens), "documentacao_carga": documento_json(documentacao_carga, "Documentação da carga"),
            "trechos_bloqueados": ids_bloqueados(trechos_bloqueados), "locais_bloqueados": ids_bloqueados(locais_bloqueados),
        }
        assinatura = assinatura_documento(solicitacao)
        existente = self.mongo.obter_manifesto(manifesto_id)
        if existente:
            if existente["assinatura_solicitacao"] != assinatura:
                raise ErroDominio("Este manifesto já foi confirmado com outros dados. Preserve os dados para repetir ou use um novo ID para outra carga.")
            if existente["status"] == "RECEBIDO":
                return self._sincronizar_recebimento(existente)
            return self._sincronizar_despacho(existente)

        calculo = self.calcular_rotas(solicitacao["origem_id"], solicitacao["destino_id"],
                                     solicitacao["trechos_bloqueados"], solicitacao["locais_bloqueados"])
        percurso = calculo["menor_distancia"]
        if not percurso:
            raise ErroDominio("Não existe percurso disponível para o despacho com os bloqueios atuais.")
        if percurso_esperado is not None and assinatura_percurso(percurso) != assinatura_percurso(percurso_esperado):
            raise ErroDominio("O percurso mudou desde a prévia. Recalcule e confira antes de confirmar o despacho.")
        percurso = deepcopy(percurso)
        rota_id = f"DEMO-ROT-{assinatura_documento({'manifesto_id': manifesto_id})[:20]}"
        try:
            self.neo4j.registrar_rota(rota_id, percurso)
        except ValueError as exc:
            raise ErroDominio(str(exc)) from exc
        percurso["rota_id"] = rota_id
        if not self.redis.reservar_veiculo(solicitacao["veiculo_id"], manifesto_id, assinatura):
            raise ErroDominio("Veículo indisponível ou reservado por outra solicitação. Confira a frota e os manifestos.")
        documento = {
            "_id": manifesto_id, **solicitacao, "assinatura_solicitacao": assinatura, "status": "DESPACHADO",
            "percurso": percurso, "despacho": {"operacao_id": f"despacho:{manifesto_id}", "confirmado_em": agora_utc()},
            "recebimento": None, "sincronizacao_redis": "PENDENTE", "demonstracao": True,
        }
        try:
            confirmado = self.mongo.confirmar_despacho(documento)
        except ErroDominio:
            # Erro de regra aborta a transação; só a reserva desta solicitação pode ser cancelada.
            self.redis.cancelar_reserva(solicitacao["veiculo_id"], manifesto_id)
            raise
        except ErroInfraestrutura as exc:
            raise ErroInfraestrutura(
                "O resultado do despacho no MongoDB precisa de conferência. "
                f"O veículo permanece reservado para {manifesto_id}. Repita com o mesmo ID e os mesmos dados; não inicie outra carga."
            ) from exc
        if confirmado["status"] == "RECEBIDO":
            return self._sincronizar_recebimento(confirmado)
        return self._sincronizar_despacho(confirmado)

    def _sincronizar_despacho(self, manifesto):
        resultado = deepcopy(manifesto)
        resultado["avisos"] = []
        try:
            reservado = self.redis.reservar_veiculo(manifesto["veiculo_id"], manifesto["_id"], manifesto["assinatura_solicitacao"])
            if not reservado or not self.redis.confirmar_despacho(manifesto["veiculo_id"], manifesto["_id"]):
                raise ErroInfraestrutura("A associação atual do veículo não corresponde a este manifesto.")
            self.mongo.marcar_sincronizacao(manifesto["_id"], "SINCRONIZADO", estado_esperado="DESPACHADO")
            resultado["sincronizacao_redis"] = "SINCRONIZADO"
        except (ErroInfraestrutura, ErroDominio):
            resultado["sincronizacao_redis"] = "PENDENTE"
            resultado["avisos"].append("Despacho confirmado e estoque baixado no MongoDB. Estado do veículo pendente de conferência; repita o despacho com o mesmo ID e dados.")
        return resultado

    def receber(self, manifesto_id):
        manifesto_id = texto_obrigatorio(manifesto_id, "o ID do manifesto")
        manifesto = self.mongo.confirmar_recebimento(manifesto_id)
        return self._sincronizar_recebimento(manifesto)

    def sincronizar_despacho(self, manifesto_id):
        manifesto = self.mongo.obter_manifesto(texto_obrigatorio(manifesto_id, "o ID do manifesto"))
        if not manifesto or manifesto["status"] != "DESPACHADO":
            raise ErroDominio("A sincronização do despacho exige um manifesto confirmado e ainda em transporte.")
        return self._sincronizar_despacho(manifesto)

    def sincronizar_recebimento(self, manifesto_id):
        manifesto = self.mongo.obter_manifesto(texto_obrigatorio(manifesto_id, "o ID do manifesto"))
        if not manifesto or manifesto["status"] != "RECEBIDO":
            raise ErroDominio("Confirme o recebimento integral antes de sincronizar a disponibilidade do veículo.")
        return self._sincronizar_recebimento(manifesto)

    def _sincronizar_recebimento(self, manifesto):
        resultado = deepcopy(manifesto)
        resultado["avisos"] = []
        try:
            estado = self.redis.liberar_veiculo(manifesto["veiculo_id"], manifesto["_id"])
            if estado == "INEXISTENTE":
                raise ErroInfraestrutura("Estado do veículo ausente no Redis.")
            if estado == "OUTRO_MANIFESTO":
                resultado["avisos"].append("A associação atual do veículo pertence a outra operação e foi preservada. Confira o estado da frota.")
            self.mongo.marcar_sincronizacao(manifesto["_id"], "SINCRONIZADO", estado_esperado="RECEBIDO")
            resultado["sincronizacao_redis"] = "SINCRONIZADO"
        except ErroInfraestrutura:
            resultado["sincronizacao_redis"] = "PENDENTE"
            resultado["avisos"].append("Recebimento integral confirmado no MongoDB. A disponibilidade do veículo está pendente de sincronização; use Sincronizar recebimento.")
        return resultado

    def atualizar_telemetria(self, veiculo_id, latitude, longitude, velocidade_kmh, temperatura_c):
        veiculo_id = texto_obrigatorio(veiculo_id, "o veículo")
        instante = agora_utc()
        telemetria = {
            **validar_telemetria(latitude, longitude, velocidade_kmh, temperatura_c),
            "medido_em": instante.isoformat(), "medido_epoch": instante.timestamp(),
            "recebido_em": instante.isoformat(), "demonstracao": True,
        }
        self.redis.atualizar_telemetria(veiculo_id, telemetria)
        return self.obter_telemetria(veiculo_id)

    def iniciar_assinante_alertas(self):
        return self.redis.iniciar_assinante()

    def estado_assinante_alertas(self):
        return self.redis.estado_assinante()

    def listar_alertas(self):
        return self.redis.consumir_alertas()

    def listar_auditoria_alertas(self):
        return self.mongo.listar_auditoria_alertas()

    def listar_auditoria(self):
        return self.mongo.listar_auditoria()

    def simular_alerta(self, tipo, veiculo_id):
        tipo = texto_obrigatorio(tipo, "o tipo do alerta").upper()
        if tipo not in {"DESVIO", "ACIDENTE"}:
            raise ErroDominio("Simule um alerta de desvio ou acidente.")
        veiculo_id = texto_obrigatorio(veiculo_id, "o veículo")
        estado = self.redis.obter_estado(veiculo_id)
        if not estado:
            raise ErroDominio("Veículo não cadastrado na demonstração.")
        evento = {"evento_id": novo_id("EVT"), "tipo": tipo, "veiculo_id": veiculo_id,
                  "manifesto_id": estado.get("manifesto_id"), "ocorrido_em": agora_utc().isoformat(),
                  "demonstracao": True, "publicacao": "PENDENTE"}
        self.mongo.registrar_alerta(evento)
        try:
            assinantes = self.redis.publicar_alerta(evento)
        except ErroInfraestrutura:
            self.mongo.atualizar_publicacao_alerta(evento["evento_id"], "FALHA_OU_RESULTADO_INDETERMINADO")
            raise
        evento.update(publicacao="PUBLICADO", assinantes_no_canal=assinantes)
        try:
            self.mongo.atualizar_publicacao_alerta(evento["evento_id"], "PUBLICADO", assinantes)
        except ErroInfraestrutura:
            evento["aviso"] = "Evento publicado no Redis, mas a confirmação da publicação está pendente na auditoria MongoDB."
        return evento

    def fechar(self):
        self.redis.encerrar_assinante()
