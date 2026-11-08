"""Gera somente a configuração ausente, sem imprimir credenciais."""

from pathlib import Path
import secrets

from src.configuracao import RAIZ_PROJETO


def preparar_configuracao(raiz: Path = RAIZ_PROJETO) -> bool:
    destino = raiz / ".env"
    if destino.exists():
        print("Configuração .env existente preservada.")
        return False
    conteudo = (raiz / ".env.example").read_text(encoding="utf-8")
    conteudo = conteudo.replace("SUBSTITUA_POR_UMA_SENHA_LOCAL", secrets.token_urlsafe(24))
    with destino.open("x", encoding="utf-8", newline="\n") as arquivo:
        arquivo.write(conteudo)
    print("Configuração .env criada com senha local gerada automaticamente.")
    return True


if __name__ == "__main__":
    preparar_configuracao()
