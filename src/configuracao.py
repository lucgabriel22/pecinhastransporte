"""Configuração local sem dependências além da biblioteca padrão."""

from dataclasses import dataclass
from pathlib import Path
import os


RAIZ_PROJETO = Path(__file__).resolve().parents[1]


def carregar_arquivo_ambiente(caminho: Path) -> dict[str, str]:
    """Lê pares simples sem executar comandos ou expandir expressões."""
    if not caminho.is_file():
        return {}
    valores: dict[str, str] = {}
    for numero, linha in enumerate(caminho.read_text(encoding="utf-8-sig").splitlines(), 1):
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        if "=" not in linha:
            raise ValueError(f"Linha {numero} inválida no arquivo de configuração.")
        chave, valor = linha.split("=", 1)
        chave, valor = chave.strip(), valor.strip()
        if not chave.isidentifier():
            raise ValueError(f"Nome de variável inválido na linha {numero}.")
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
            valor = valor[1:-1]
        valores[chave] = valor
    return valores


@dataclass(frozen=True)
class Configuracao:
    mongo_uri: str
    mongo_database: str
    redis_url: str
    redis_prefixo: str
    neo4j_uri: str
    neo4j_usuario: str
    neo4j_senha: str
    neo4j_database: str
    telemetria_atualizacao_segundos: int = 5
    telemetria_validade_segundos: int = 30

    @classmethod
    def carregar(cls, caminho: Path | None = None) -> "Configuracao":
        valores = carregar_arquivo_ambiente(caminho or RAIZ_PROJETO / ".env")
        valores.update(os.environ)
        senha = valores.get("NEO4J_PASSWORD", "")
        if not senha or senha == "SUBSTITUA_POR_UMA_SENHA_LOCAL":
            raise ValueError("Gere a configuração local executando .\\scripts\\configurar.ps1.")
        atualizacao = int(valores.get("TELEMETRIA_ATUALIZACAO_SEGUNDOS", "5"))
        validade = int(valores.get("TELEMETRIA_VALIDADE_SEGUNDOS", "30"))
        if atualizacao <= 0 or validade <= 0:
            raise ValueError("Os intervalos de telemetria devem ser positivos.")
        return cls(
            mongo_uri=valores.get("MONGODB_URI", "mongodb://127.0.0.1:27017/?replicaSet=rs0&directConnection=true"),
            mongo_database=valores.get("MONGODB_DATABASE", "supply_chain_demo"),
            redis_url=valores.get("REDIS_URL", "redis://127.0.0.1:6379/0"),
            redis_prefixo=valores.get("REDIS_PREFIXO", "sc:demo:"),
            neo4j_uri=valores.get("NEO4J_URI", "bolt://127.0.0.1:7687"),
            neo4j_usuario=valores.get("NEO4J_USERNAME", "neo4j"),
            neo4j_senha=senha,
            neo4j_database=valores.get("NEO4J_DATABASE", "neo4j"),
            telemetria_atualizacao_segundos=atualizacao,
            telemetria_validade_segundos=validade,
        )
