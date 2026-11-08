"""Gera uma entrega reproduzível por lista explícita, sem credenciais locais."""
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


RAIZ = Path(__file__).resolve().parents[1]
ARQUIVOS = (
    "app.py", "README.md", "PLANEJAMENTO.md", "MODELAGEM.md",
    "requirements.txt", "compose.yaml", ".env.example", ".gitignore",
    ".streamlit/config.toml",
)
PASTAS = {"src": {".py", ".css"}, "scripts": {".py", ".ps1"},
          "tests": {".py"}, "docs": {".md", ".json"}}
PRIVADOS = {"DEFESA.md", "DEMONSTRACAO.md", "FALA_APRESENTACAO.md", "PERGUNTAS_DEFESA.md"}


def main() -> None:
    fontes = [RAIZ / nome for nome in ARQUIVOS]
    for pasta, extensoes in PASTAS.items():
        fontes.extend(p for p in (RAIZ / pasta).rglob("*")
                      if p.is_file() and p.suffix in extensoes
                      and "__pycache__" not in p.parts and p.name not in PRIVADOS)
    faltantes = [p.relative_to(RAIZ).as_posix() for p in fontes if not p.is_file()]
    if faltantes:
        raise SystemExit(f"Arquivos ausentes: {faltantes}")
    relatorio = json.loads((RAIZ / "docs/RESULTADO_TESTES.json").read_text(encoding="utf-8"))
    if not (relatorio.get("sucesso") and relatorio.get("integracao_solicitada")
            and relatorio.get("ignorados") == 0):
        raise SystemExit("A entrega exige testes de integração aprovados sem ignorados.")
    conteudos = {p.relative_to(RAIZ).as_posix(): p.read_bytes() for p in sorted(fontes)}
    manifesto = {nome: sha256(dados).hexdigest() for nome, dados in conteudos.items()}
    destino = RAIZ / "entrega/PecinhasTransportes.zip"
    destino.parent.mkdir(exist_ok=True)
    with ZipFile(destino, "w", ZIP_DEFLATED) as pacote:
        for nome, dados in conteudos.items():
            pacote.writestr(f"PecinhasTransportes/{nome}", dados)
        pacote.writestr("PecinhasTransportes/MANIFESTO_SHA256.json",
                        json.dumps(manifesto, indent=2, ensure_ascii=False))
    with ZipFile(destino) as pacote:
        if pacote.testzip() is not None:
            raise SystemExit("Falha na verificação do ZIP.")
        for nome, resumo in manifesto.items():
            if sha256(pacote.read(f"PecinhasTransportes/{nome}")).hexdigest() != resumo:
                raise SystemExit(f"Conteúdo divergente: {nome}")
    destino.with_suffix(".sha256").write_text(
        sha256(destino.read_bytes()).hexdigest() + "  " + destino.name + "\n", encoding="ascii")
    print(f"Pacote validado: {destino} ({len(conteudos)} arquivos e manifesto)")


if __name__ == "__main__":
    main()
