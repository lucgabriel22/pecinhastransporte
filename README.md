# PecinhasTransportes — sistema logístico com bancos de dados NoSQL

Aplicação acadêmica do estudo de caso 04: inventário e lotes, telemetria de frota, otimização de percursos e despacho/recebimento integral. Python e Streamlit conectam-se diretamente a MongoDB, Redis e Neo4j. Todos os registros da demonstração são fictícios.

A interface PecinhasTransportes utiliza identidade visual em azul profundo e âmbar, navegação numerada entre as quatro áreas, indicadores derivados dos bancos e visualização esquemática da rede. Os estilos e os gráficos são locais; a interface não exige bibliotecas adicionais.

## Situação do ambiente

O projeto foi validado localmente com Docker Desktop, WSL 2 e os três bancos reais. O resultado que acompanha o pacote, com data exata e contagem dos testes, está em [RESULTADO_TESTES.json](docs/RESULTADO_TESTES.json). O funcionamento após reiniciar depende de iniciar novamente os serviços. Veja também [a validação](docs/VALIDACAO.md).

O sistema foi preparado e iniciado no Windows 10 Pro local, com aproximadamente 8 GB de RAM. Docker Desktop utiliza WSL 2 para executar os bancos Linux. O consumo observado na verificação está registrado na validação; não representa um teste de carga.

## Acessar e iniciar novamente

Com o sistema em execução, abra [localhost:8501](http://localhost:8501).

Após uma nova reinicialização do Windows, abra o PowerShell na pasta deste projeto e execute:

```powershell
.\scripts\continuar_apos_reinicio.ps1
```

Esse comando abre o Docker Desktop, aguarda seu mecanismo, prepara as dependências ausentes, inicia os bancos, carrega os dados que faltarem e abre o Streamlit em [localhost:8501](http://localhost:8501).

Se o Windows bloquear a execução de scripts locais, use uma política limitada a esse processo, sem alterar a política permanente do computador:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\continuar_apos_reinicio.ps1
```

Caso o Docker peça uma atualização do WSL, conclua a atualização na janela do Docker e execute o comando novamente. O script não reinicia o computador automaticamente.

Nas execuções seguintes, com Docker pronto:

```powershell
.\scripts\iniciar.ps1
```

Para preparar uma nova cópia do projeto:

```powershell
.\scripts\configurar.ps1
.\scripts\iniciar.ps1
```

O configurador usa Python 3.12 em `.venv` e cria `.env` com senha Neo4j local aleatória. Ele preserva uma configuração existente. A senha não é impressa no terminal e `.env` está excluído do controle de versão.

## Dados e demonstração

O comando `scripts.inicializar` cria coleções com validação, índices MongoDB, restrições Neo4j, a malha e os cadastros fictícios. Repetir a carga preserva saldos, manifestos e estados existentes. Manifestos em transporte são reconciliados no Redis sem nova baixa de estoque; conflitos são apresentados para conferência.

- **Inventário e lotes:** cadastre mercadorias e lotes e consulte especificações e auditoria. A demonstração usa quantidades inteiras de unidades.
- **Torre de controle:** envie GPS, velocidade e temperatura pelo simulador. A tela consulta o Redis a cada 5 segundos; após 30 segundos sem leitura nova, apresenta o dado como desatualizado. Botões publicam eventos de desvio e acidente em Redis Pub/Sub.
- **Otimizador de rotas:** compare o percurso com menos trechos e aquele com menos quilômetros. Simule bloqueios de trecho ou local sem apagar a malha.
- **Despacho e recebimento:** confira o percurso, selecione lotes/quantidades e veículo e confirme o despacho. O estoque da origem baixa nesse momento. Confirme o recebimento integral para devolver o veículo à disponibilidade.

Na malha fictícia, o percurso de menor distância tem **20 km**, enquanto o caminho direto tem um trecho e **30 km**. Bloquear T2 ou o Transbordo A muda a melhor distância para **23 km**. Um nó `Rota` representa o percurso completo; as relações `TRECHO` representam suas partes e possuem sentido explícito.

Documentação de carga e especificações são objetos JSON livres. Não há integração com sistema fiscal nem inferência automática de acidentes a partir dos sensores.

## Organização

```text
app.py                     Entrada Streamlit
src/configuracao.py        Configuração local e variáveis de ambiente
src/bootstrap.py           Clientes reais e composição dos serviços
src/dominio.py             Validações e identificadores
src/repositorios/          Comandos MongoDB, Redis e Neo4j
src/servicos/              Fluxos e recuperação entre bancos
src/interface/             Quatro telas e grafo SVG
src/dados_demo.py           Carga fictícia identificada
scripts/                   Preparação, início, carga e verificação
tests/                     Testes unitários, interface e integração real
compose.yaml               Três bancos e volumes persistentes locais
requirements.txt           Dependências Python diretas fixadas
```

As únicas dependências Python diretas são Streamlit e os clientes de MongoDB, Redis e Neo4j; bibliotecas trazidas internamente por eles são instaladas pelo gerenciador de dependências. A visualização do grafo usa SVG gerado com a biblioteca padrão.

## Consistência e recuperação

MongoDB roda em replica set de um nó para permitir transação entre baixa dos lotes, manifesto e auditoria. Isso garante atomicidade nesses documentos MongoDB; não cria uma transação distribuída com Redis ou Neo4j.

Uma identificação de manifesto é preservada para repetir o despacho sem nova baixa. Quando o resultado de uma gravação é incerto, a interface mantém a solicitação para consulta/repetição. Os botões de sincronização recuperam o estado Redis de um despacho ou recebimento já confirmado. Uma confirmação antiga não libera um veículo associado a um manifesto posterior.

O manifesto mantém uma cópia do percurso e das distâncias utilizadas. A consulta ao Neo4j continua refletindo a malha atual. O cálculo por soma dos caminhos é adequado à pequena malha de demonstração e pode crescer exponencialmente em grafos maiores.

Pub/Sub distribui eventos para assinantes conectados. O histórico no MongoDB registra o evento e a publicação; não garante reenvio nem prova que um assinante recebeu uma mensagem. A torre distingue os eventos recebidos do histórico documental.

## Verificar e testar

```powershell
# Somente preparar os bancos, sem iniciar a interface
.\scripts\iniciar.ps1 -SomenteBancos

# Verificar conexões reais
.\.venv\Scripts\python.exe -m scripts.verificar

# Testes sem exigir bancos
.\scripts\testar.ps1

# Testes com os três bancos reais
.\scripts\testar.ps1 -Integracao
```

Os testes de integração usam uma base MongoDB separada e um prefixo Redis exclusivo. No Neo4j, compartilham a malha de demonstração e registram rotas de teste próprias. Não apagam dados. O comando com `-Integracao` retorna falha se os bancos não estiverem disponíveis, em vez de declarar a verificação concluída.

Para testes de interface, os dublês ficam somente dentro de `tests/`; a aplicação sempre usa os clientes dos bancos reais.

## Parar os serviços

Encerre o Streamlit com `Ctrl+C` no terminal e pare os bancos:

```powershell
.\scripts\parar.ps1
```

Os volumes persistentes são mantidos. As portas dos bancos são publicadas apenas em `127.0.0.1` para uso local. Este Compose é destinado à demonstração local.

## Referências do projeto
- [Guia do pacote de entrega](docs/ENTREGA.md)

- [Planejamento](PLANEJAMENTO.md)
- [Modelagem](MODELAGEM.md)
- [Instalação do Docker Desktop no Windows](https://docs.docker.com/desktop/setup/install/windows-install/)
- [Instalação do WSL](https://learn.microsoft.com/en-us/windows/wsl/install)
- [Conexão direta a replica set em ambiente de desenvolvimento](https://www.mongodb.com/docs/manual/reference/connection-string-options/#replica-set-option)
