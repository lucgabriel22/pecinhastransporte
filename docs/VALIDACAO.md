# Validação local — estudo de caso 04

Data: 26 de outubro de 2026.

## Ambiente iniciado

- Windows 10 Pro, aproximadamente 8 GB de RAM, virtualização ativa.
- Docker Desktop com WSL 2.
- MongoDB 8.0 em replica set de um nó: saudável.
- Redis 7.4: saudável.
- Neo4j 5.26 Community: saudável.
- Streamlit disponível em http://127.0.0.1:8501/ e endpoint de saúde respondendo `ok`.

As imagens foram baixadas e os dados fictícios carregados pelos scripts do projeto. A carga preservou cadastros e saldos existentes.

## Testes executados

Comando:

```powershell
.\.venv\Scripts\python.exe -m scripts.testar --integracao
```

Resultado: **50 testes executados; 0 ignorados; 0 falhas; 0 erros**.

Os 37 testes de domínio, serviços, interface e validação foram complementados por 13 testes de integração: sete específicos do Neo4j e seis cenários reais envolvendo os três bancos. Os testes de interface usam dublês restritos à suíte; os testes de integração se conectam aos servidores locais reais.

Foram verificados, entre outros:

- Menor distância de 20 km, caminho direto de 30 km e alternativa de 23 km após bloqueio.
- Exclusão de trecho/local indisponível durante a busca.
- Despacho com baixa de estoque uma única vez, inclusive ao repetir uma solicitação.
- Recebimento integral sem nova baixa e com liberação do veículo.
- Confirmação antiga sem liberar um veículo associado a outro despacho.
- Transação MongoDB abortada sem débito parcial dos lotes.
- Recebimento de evento Redis Pub/Sub por assinante conectado.
- Horários e validade das leituras de telemetria.

Os testes usam dados próprios e não apagam a demonstração. Os relatórios locais sem credenciais ficam em `.estado_local/testes.json` e `.estado_local/bancos.json`; o log da execução fica em `.logs/testes-integracao.log`.

A carga inicial também foi executada novamente sobre os bancos em uso. A comparação antes/depois confirmou preservação dos saldos, dos estados dos veículos e da quantidade de manifestos.

## Conferência no navegador

As quatro telas foram abertas na aplicação conectada aos bancos reais, sem erros de aplicação observados:

- Inventário: uma mercadoria, dois lotes com 100 e 50 unidades e quatro locais.
- Torre de controle: dois veículos disponíveis e identificação de telemetria desatualizada.
- Otimizador: grafo legível, percurso base de 20 km e alternativa de 23 km ao bloquear T2 somente na sessão.
- Despacho/recebimento: seleção de carga e veículo, documentação JSON, prévia do percurso e confirmação desabilitada quando não há itens.

Essa conferência visual não criou transportes nem alterou telemetria ou eventos na base de demonstração. A gravação do ciclo de despacho e recebimento foi validada pelos testes de integração em sua base separada.

## Consumo observado

Instantâneo dos contêineres após a suíte:

| Serviço | Memória observada | Limite configurado |
| --- | --- | --- |
| MongoDB | aproximadamente 113 MiB | 1 GiB |
| Redis | aproximadamente 9 MiB | 128 MiB |
| Neo4j | aproximadamente 704 MiB | 1 GiB |

Esse registro não inclui todo o consumo do Docker/WSL, Windows ou Streamlit e não representa teste de carga ou garantia de consumo constante.

## Acesso e nova execução

Abra http://127.0.0.1:8501/ enquanto os serviços estiverem ativos. As instruções de início, parada, recuperação e repetição dos testes estão no [README](../README.md).

## Revisão da interface — 3 de novembro de 2026

A interface recebeu a identidade PecinhasTransportes, com navegação lateral, cores azul-marinho e âmbar, cartões de indicadores, busca no inventário e nova apresentação da malha logística. As quatro telas e as tecnologias previstas no enunciado foram mantidas.

A revisão visual no navegador abrangeu inventário, torre de controle, otimizador de rotas e despacho/recebimento. Também foram conferidos o menu móvel e a organização dos formulários em uma largura de 390 pixels, sem transbordamento horizontal da página. A seleção inicial de rotas utiliza um centro de distribuição e um cliente.

A execução final de `python -m scripts.testar --integracao` passou nos 50 testes, sem falhas, com MongoDB, Redis e Neo4j conectados. Depois desse resultado, foi aplicado apenas um ajuste de CSS para manter visível o botão do menu móvel, verificado novamente no navegador. As leituras antigas de telemetria continuam identificadas como desatualizadas, sem inventar dados atuais.
