# PecinhasTransportes — guia de entrega

Trabalho de Implementação de Bancos de Dados NoSQL, estudo de caso 04.

## Conteúdo

- `README.md`: instalação e execução local no Windows.
- `PLANEJAMENTO.md` e `MODELAGEM.md`: decisões, regras e divisão dos dados.
- `src/` e `app.py`: aplicação Python/Streamlit e integração direta com os bancos.
- `compose.yaml`: MongoDB, Redis e Neo4j locais, com volumes persistentes.
- `scripts/`: configuração, carga inicial, verificação, testes e empacotamento.
- `tests/`: testes de domínio, serviços, interface e integração real.
- `docs/RESULTADO_TESTES.json`: resultado da execução de testes que acompanha a entrega.

## Primeira execução em outro computador

Extraia o ZIP inteiro e abra o PowerShell na pasta que contém `app.py`. Instale os pré-requisitos indicados no README e abra o Docker Desktop. Execute:

```powershell
.\scripts\configurar.ps1
.\scripts\iniciar.ps1
```

O configurador gera as credenciais locais; nenhum arquivo `.env` do autor acompanha a entrega. O endereço da interface é `http://127.0.0.1:8501/`.

Para verificar a instalação, em outro terminal:

```powershell
.\scripts\testar.ps1 -Integracao
```

A carga inicial é reproduzida pelos scripts, sem precisar de uma cópia dos volumes do autor. Repetir a inicialização preserva os dados existentes. Os testes usam dados próprios; não reinicialize volumes para fazer a demonstração.

## Envio e reprodução


O código e os documentos técnicos deste repositório compõem a entrega pública. O ZIP gerado pelo script também exclui os materiais privados de apresentação. A publicação em um repositório ou o envio à instituição deve ser feito no destino escolhido pelo grupo. Autoria, integrantes e dados da turma precisam ser preenchidos pelo grupo; não foram inventados.

O pacote não contém ambiente virtual, credenciais, logs privados, volumes dos bancos ou arquivos alheios ao projeto. A lista de arquivos e seus hashes está em `MANIFESTO_SHA256.json` dentro do ZIP.

Para gerar novamente:

```powershell
.\.venv\Scripts\python.exe -m scripts.empacotar
```

O resultado fica na pasta `entrega/`.
