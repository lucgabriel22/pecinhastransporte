"""Estado atômico da frota, última leitura e consumidor Redis Pub/Sub."""

from __future__ import annotations

import json
import queue
import threading
from functools import wraps

from redis.exceptions import RedisError

from src.dominio import ErroDominio, ErroInfraestrutura, agora_utc


def _tratar_falha(funcao):
    @wraps(funcao)
    def executar(*args, **kwargs):
        try:
            return funcao(*args, **kwargs)
        except RedisError as exc:
            raise ErroInfraestrutura("Redis indisponível. Confira o banco antes de repetir a operação.") from exc
    return executar


def _texto(valor):
    return valor.decode("utf-8") if isinstance(valor, bytes) else valor


class RepositorioRedis:
    _INICIALIZAR = """
        redis.call('SADD', KEYS[1], ARGV[1])
        redis.call('HSETNX', KEYS[2], 'nome', ARGV[2])
        if redis.call('HEXISTS', KEYS[2], 'disponibilidade') == 0 then
            redis.call('HSET', KEYS[2], 'disponibilidade', 'DISPONIVEL',
                'manifesto_id', '', 'atualizado_em', ARGV[3], 'demonstracao', 'true')
        end
        return 1
    """
    _RESERVAR = """
        if redis.call('SISMEMBER', KEYS[1], ARGV[1]) == 0 then return -1 end
        if redis.call('SISMEMBER', KEYS[3], ARGV[2]) == 1 then return -2 end
        local estado = redis.call('HGET', KEYS[2], 'disponibilidade')
        local dono = redis.call('HGET', KEYS[2], 'manifesto_id')
        local assinatura = redis.call('HGET', KEYS[2], 'assinatura_solicitacao')
        if dono == ARGV[2] and assinatura == ARGV[4] and (estado == 'RESERVADO' or estado == 'EM_TRANSPORTE') then return 1 end
        if estado ~= 'DISPONIVEL' then return 0 end
        redis.call('HSET', KEYS[2], 'disponibilidade', 'RESERVADO',
            'manifesto_id', ARGV[2], 'assinatura_solicitacao', ARGV[4], 'ultima_operacao', 'despacho:' .. ARGV[2], 'atualizado_em', ARGV[3])
        return 1
    """
    _CONFIRMAR = """
        local estado = redis.call('HGET', KEYS[1], 'disponibilidade')
        if redis.call('HGET', KEYS[1], 'manifesto_id') ~= ARGV[1] then return 0 end
        if estado ~= 'RESERVADO' and estado ~= 'EM_TRANSPORTE' then return 0 end
        redis.call('HSET', KEYS[1], 'disponibilidade', 'EM_TRANSPORTE', 'atualizado_em', ARGV[2])
        return 1
    """
    _CANCELAR = """
        if redis.call('HGET', KEYS[1], 'manifesto_id') ~= ARGV[1] then return 0 end
        if redis.call('HGET', KEYS[1], 'disponibilidade') ~= 'RESERVADO' then return 0 end
        redis.call('HSET', KEYS[1], 'disponibilidade', 'DISPONIVEL', 'manifesto_id', '', 'atualizado_em', ARGV[2])
        return 1
    """
    _LIBERAR = """
        redis.call('SADD', KEYS[2], ARGV[1])
        local estado = redis.call('HGET', KEYS[1], 'disponibilidade')
        if not estado then return 'INEXISTENTE' end
        local dono = redis.call('HGET', KEYS[1], 'manifesto_id')
        if dono == ARGV[1] and (estado == 'RESERVADO' or estado == 'EM_TRANSPORTE') then
            redis.call('HSET', KEYS[1], 'disponibilidade', 'DISPONIVEL', 'manifesto_id', '',
                'ultimo_manifesto_recebido', ARGV[1], 'ultima_operacao', 'recebimento:' .. ARGV[1], 'atualizado_em', ARGV[2])
            return 'LIBERADO'
        end
        if estado == 'DISPONIVEL' and redis.call('HGET', KEYS[1], 'ultimo_manifesto_recebido') == ARGV[1] then
            return 'JA_LIBERADO'
        end
        return 'OUTRO_MANIFESTO'
    """
    _TELEMETRIA = """
        if redis.call('SISMEMBER', KEYS[1], ARGV[1]) == 0 then return -1 end
        local ultima = tonumber(redis.call('HGET', KEYS[2], 'medido_epoch'))
        if ultima and ultima > tonumber(ARGV[2]) then return 0 end
        redis.call('HSET', KEYS[2], 'medido_epoch', ARGV[2], 'latitude', ARGV[3],
            'longitude', ARGV[4], 'velocidade_kmh', ARGV[5], 'temperatura_c', ARGV[6],
            'medido_em', ARGV[7], 'recebido_em', ARGV[8], 'demonstracao', 'true')
        return 1
    """

    def __init__(self, client, prefixo="sc:demo:"):
        self.client = client
        self.prefixo = prefixo
        self._fila = queue.Queue(maxsize=500)
        self._parar = threading.Event()
        self._pronto = threading.Event()
        self._lock = threading.Lock()
        self._thread = None
        self._conectado = False
        self._erro_assinante = None
        self._descartados = 0

    def _chave(self, veiculo_id, parte):
        return f"{self.prefixo}veiculo:{veiculo_id}:{parte}"

    @property
    def canais(self):
        return [f"{self.prefixo}alertas:desvio", f"{self.prefixo}alertas:acidente"]

    @_tratar_falha
    def verificar_conexao(self):
        self.client.ping()
        return "Conexão disponível."

    @_tratar_falha
    def inicializar_veiculo(self, veiculo_id, nome):
        return self.client.eval(self._INICIALIZAR, 2, f"{self.prefixo}frota:veiculos",
                                self._chave(veiculo_id, "estado"), veiculo_id, nome, agora_utc().isoformat())

    @_tratar_falha
    def obter_estado(self, veiculo_id):
        resultado = {_texto(chave): _texto(valor) for chave, valor in self.client.hgetall(self._chave(veiculo_id, "estado")).items()}
        if not resultado:
            return None
        resultado["manifesto_id"] = resultado.get("manifesto_id") or None
        resultado["demonstracao"] = resultado.get("demonstracao") == "true"
        return resultado

    @_tratar_falha
    def listar_veiculos(self):
        ids = sorted(_texto(valor) for valor in self.client.smembers(f"{self.prefixo}frota:veiculos"))
        return [{"id": veiculo_id, **(self.obter_estado(veiculo_id) or {"disponibilidade": "DESCONHECIDA"}),
                 "telemetria": self.obter_telemetria(veiculo_id)} for veiculo_id in ids]

    @_tratar_falha
    def reservar_veiculo(self, veiculo_id, manifesto_id, assinatura_solicitacao=""):
        resultado = self.client.eval(self._RESERVAR, 3, f"{self.prefixo}frota:veiculos",
                                     self._chave(veiculo_id, "estado"), f"{self.prefixo}manifestos:recebidos",
                                     veiculo_id, manifesto_id, agora_utc().isoformat(), assinatura_solicitacao)
        if resultado == -1:
            raise ErroDominio("Veículo não cadastrado na frota de demonstração.")
        if resultado == -2:
            raise ErroDominio("Este manifesto já teve o recebimento sincronizado; confira seu histórico no MongoDB.")
        return resultado == 1

    @_tratar_falha
    def confirmar_despacho(self, veiculo_id, manifesto_id):
        return self.client.eval(self._CONFIRMAR, 1, self._chave(veiculo_id, "estado"), manifesto_id, agora_utc().isoformat()) == 1

    @_tratar_falha
    def cancelar_reserva(self, veiculo_id, manifesto_id):
        return self.client.eval(self._CANCELAR, 1, self._chave(veiculo_id, "estado"), manifesto_id, agora_utc().isoformat()) == 1

    @_tratar_falha
    def liberar_veiculo(self, veiculo_id, manifesto_id):
        return _texto(self.client.eval(self._LIBERAR, 2, self._chave(veiculo_id, "estado"),
                                      f"{self.prefixo}manifestos:recebidos", manifesto_id, agora_utc().isoformat()))

    @_tratar_falha
    def atualizar_telemetria(self, veiculo_id, telemetria):
        resultado = self.client.eval(self._TELEMETRIA, 2, f"{self.prefixo}frota:veiculos", self._chave(veiculo_id, "telemetria"),
                                     veiculo_id, telemetria["medido_epoch"], telemetria["latitude"], telemetria["longitude"],
                                     telemetria["velocidade_kmh"], telemetria["temperatura_c"],
                                     telemetria["medido_em"], telemetria["recebido_em"])
        if resultado == -1:
            raise ErroDominio("Veículo não cadastrado na frota de demonstração.")
        return resultado == 1

    @_tratar_falha
    def obter_telemetria(self, veiculo_id):
        resultado = {_texto(chave): _texto(valor) for chave, valor in self.client.hgetall(self._chave(veiculo_id, "telemetria")).items()}
        if not resultado:
            return None
        try:
            for campo in ("latitude", "longitude", "velocidade_kmh", "temperatura_c", "medido_epoch"):
                resultado[campo] = float(resultado[campo])
        except (KeyError, ValueError) as exc:
            raise ErroInfraestrutura("A leitura de telemetria no Redis possui formato inválido.") from exc
        resultado["demonstracao"] = True
        return resultado

    @_tratar_falha
    def publicar_alerta(self, evento):
        canal = f"{self.prefixo}alertas:{evento['tipo'].lower()}"
        return self.client.publish(canal, json.dumps(evento, ensure_ascii=False, allow_nan=False))

    def iniciar_assinante(self):
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._parar.clear()
                self._pronto.clear()
                self._thread = threading.Thread(target=self._executar_assinante, name="alertas-redis-demo", daemon=True)
                self._thread.start()
        self._pronto.wait(timeout=2)
        return self.estado_assinante()

    def _enfileirar(self, evento):
        try:
            self._fila.put_nowait(evento)
        except queue.Full:
            try:
                self._fila.get_nowait()
            except queue.Empty:
                pass
            self._descartados += 1
            try:
                self._fila.put_nowait(evento)
            except queue.Full:
                self._descartados += 1

    def _executar_assinante(self):
        # pubsub() reserva uma conexão dedicada; a thread não acessa Streamlit.
        while not self._parar.is_set():
            pubsub = None
            try:
                pubsub = self.client.pubsub(ignore_subscribe_messages=False)
                pubsub.subscribe(*self.canais)
                confirmados = set()
                while not self._parar.is_set():
                    mensagem = pubsub.get_message(timeout=0.5)
                    if not mensagem:
                        continue
                    tipo = _texto(mensagem["type"])
                    if tipo == "subscribe":
                        confirmados.add(_texto(mensagem["channel"]))
                        if len(confirmados) == len(self.canais):
                            self._conectado = True
                            self._erro_assinante = None
                            self._pronto.set()
                    elif tipo == "message":
                        try:
                            evento = json.loads(_texto(mensagem["data"]))
                            if isinstance(evento, dict) and evento.get("tipo") in {"DESVIO", "ACIDENTE"}:
                                evento["recebido_em"] = agora_utc().isoformat()
                                self._enfileirar(evento)
                        except (ValueError, TypeError, UnicodeDecodeError):
                            self._erro_assinante = "Mensagem recebida com JSON inválido."
            except RedisError:
                self._erro_assinante = "Assinante desconectado; tentará reconectar. Eventos deste intervalo podem ser perdidos."
            finally:
                self._conectado = False
                if pubsub is not None:
                    try:
                        pubsub.close()
                    except RedisError:
                        pass
            self._parar.wait(timeout=1)

    def estado_assinante(self):
        return {"conectado": self._conectado, "erro": self._erro_assinante, "descartados": self._descartados}

    def consumir_alertas(self):
        eventos = []
        while True:
            try:
                eventos.append(self._fila.get_nowait())
            except queue.Empty:
                return eventos

    def encerrar_assinante(self):
        self._parar.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
