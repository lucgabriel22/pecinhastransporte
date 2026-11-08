"""Validações do estudo de caso, sem dependência de bancos ou da interface."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from uuid import uuid4


class ErroDominio(ValueError):
    """Entrada inválida ou operação incompatível com o estado atual."""


class ErroInfraestrutura(RuntimeError):
    """Banco indisponível ou resultado que exige conferência/repetição segura."""


def agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def novo_id(prefixo: str) -> str:
    return f"DEMO-{prefixo}-{uuid4().hex[:16]}"


def texto_obrigatorio(valor: str, campo: str) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise ErroDominio(f"Informe {campo}.")
    return valor.strip()


def quantidade_positiva(valor: int) -> int:
    # A demonstração usa unidades discretas; não arredondar quantidades recebidas.
    if isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
        raise ErroDominio("A quantidade deve ser um número inteiro positivo.")
    return valor


def documento_json(valor: dict, campo: str) -> dict:
    if not isinstance(valor, dict):
        raise ErroDominio(f"{campo} deve ser um objeto JSON.")

    def verificar_chaves(objeto):
        if isinstance(objeto, dict):
            for chave, conteudo in objeto.items():
                if not isinstance(chave, str) or "\x00" in chave:
                    raise ErroDominio(f"{campo} contém uma chave JSON inválida.")
                verificar_chaves(conteudo)
        elif isinstance(objeto, list):
            for conteudo in objeto:
                verificar_chaves(conteudo)

    verificar_chaves(valor)
    try:
        # O round trip também impede que um chamador altere o documento original.
        return json.loads(json.dumps(valor, allow_nan=False, ensure_ascii=False))
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ErroDominio(f"{campo} contém valores incompatíveis com JSON.") from exc


def normalizar_itens(itens: list[dict]) -> list[dict]:
    if not isinstance(itens, list) or not itens:
        raise ErroDominio("Inclua pelo menos um lote no manifesto.")
    resultado = []
    lotes = set()
    for item in itens:
        if not isinstance(item, dict):
            raise ErroDominio("Cada item deve informar lote e quantidade.")
        lote_id = texto_obrigatorio(item.get("lote_id"), "o lote")
        if lote_id in lotes:
            raise ErroDominio("Um lote só pode aparecer uma vez no manifesto.")
        lotes.add(lote_id)
        resultado.append({"lote_id": lote_id, "quantidade": quantidade_positiva(item.get("quantidade"))})
    return sorted(resultado, key=lambda item: item["lote_id"])


def ids_bloqueados(valores: list[str] | None) -> list[str]:
    if valores is None:
        return []
    if not isinstance(valores, list):
        raise ErroDominio("Os bloqueios devem ser uma lista de identificadores.")
    return sorted({texto_obrigatorio(valor, "o identificador do bloqueio") for valor in valores})


def assinatura_documento(documento: dict) -> str:
    serializado = json.dumps(documento, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(serializado.encode("utf-8")).hexdigest()


def assinatura_percurso(percurso: dict) -> str:
    try:
        dados = {
            "trechos": [
                {"id": trecho["id"], "origem_id": trecho["origem_id"],
                 "destino_id": trecho["destino_id"], "distancia_km": float(trecho["distancia_km"])}
                for trecho in percurso["trechos"]
            ],
            "distancia_total_km": float(percurso["distancia_total_km"]),
        }
        return assinatura_documento(dados)
    except (KeyError, TypeError, ValueError) as exc:
        raise ErroDominio("O percurso informado não possui trechos e distâncias válidos.") from exc


def validar_telemetria(latitude, longitude, velocidade_kmh, temperatura_c) -> dict:
    resultado = {}
    for nome, valor in (("latitude", latitude), ("longitude", longitude),
                        ("velocidade_kmh", velocidade_kmh), ("temperatura_c", temperatura_c)):
        if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not math.isfinite(valor):
            raise ErroDominio(f"Informe um número finito para {nome}.")
        resultado[nome] = float(valor)
    if not -90 <= resultado["latitude"] <= 90:
        raise ErroDominio("Latitude deve estar entre -90 e 90.")
    if not -180 <= resultado["longitude"] <= 180:
        raise ErroDominio("Longitude deve estar entre -180 e 180.")
    if resultado["velocidade_kmh"] < 0:
        raise ErroDominio("Velocidade não pode ser negativa.")
    return resultado


def telemetria_com_validade(telemetria: dict | None, validade_segundos: int, instante: datetime | None = None) -> dict | None:
    if not telemetria:
        return None
    resultado = dict(telemetria)
    try:
        medido = datetime.fromisoformat(str(telemetria["medido_em"]))
        if medido.tzinfo is None:
            medido = medido.replace(tzinfo=timezone.utc)
        idade = max(0.0, ((instante or agora_utc()) - medido).total_seconds())
        resultado.update(idade_segundos=idade, desatualizada=idade > validade_segundos)
    except (ValueError, TypeError, KeyError):
        resultado.update(idade_segundos=None, desatualizada=True)
    return resultado
