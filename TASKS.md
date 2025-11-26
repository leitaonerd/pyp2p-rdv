# Plano de Trabalho — Cliente PyP2P

Este documento organiza as tarefas necessárias para implementar o cliente de chat P2P descrito na especificação `src/docs/RC202502 - PyP2p - Especificacao Trabalho.md`. Cada macroatividade está dividida em passos objetivos, com entregáveis e observações úteis.

## 1. Fundamentos e Preparação
- **1.1 Configuração de ambiente**
  - Definir versão mínima do Python e dependências.
  - Configurar `venv` + `requirements.txt` / `pyproject.toml`.
  - Criar script `make`/`invoke` opcional para rodar lint/tests.
  - Padronizar ferramentas de lint/format (ex.: `black`, `ruff` ou `flake8`).
  - Estabelecer política de armazenamento de segredos e `peer_id` (arquivo seguro, variáveis de ambiente).
- **1.2 Estrutura inicial do projeto**
  - Revisar módulos já existentes em `src/rendezvous`.
  - Criar diretórios sugeridos (p2p_client, cli, state, etc.).
  - Documentar layout no `README.md`.
- **1.3 Configuração e parâmetros**
  - Definir arquivo `config.json` ou classe `Settings`.
  - Parametrizar host/porta do rendezvous, timeouts, intervalos de discovery e keep-alive, limites de reconexão.
  - Descrever convenção para valores sensíveis (ex.: namespace padrão, credenciais) e fallback defaults.

## 2. Integração com o Servidor Rendezvous
- **2.1 Cliente HTTP básico**
  - Implementar módulo `rendezvous_connection.py` (ou adaptar `peer_db.py`).
  - Funções: `register`, `unregister`, `discover_peers`, `heartbeat` (se houver), tratamento de erros e backoff.
  - Mapear tabela de erros (HTTP e de aplicação) e política de re-autenticação.
- **2.2 Registro inicial**
  - Fluxo: carregar config → gerar `peer_id` (`name@namespace`) → enviar `REGISTER`.
  - Persistir dados de sessão (token, timestamp, TTL).
  - Validar compatibilidade de versão/`features` retornadas pelo rendezvous.
- **2.3 Descoberta contínua**
  - Agendar `DISCOVER` periódico (thread ou async task).
  - Atualizar `PeerTable` com novos peers, removendo inativos.
  - Notificar `p2p_client` sobre mudanças relevantes.
  - Cobrir com testes automatizados usando mocks ou o utilitário `src/tools/rc_tester.py`.
- **2.4 Unregister e shutdown limpo**
  - Garantir envio de `UNREGISTER` ao sair (`/quit`, CTRL+C, exceções).

## 3. Gerenciamento de Peers e Conexões TCP
- **3.1 `PeerTable` e estado**
  - Estrutura para armazenar peers conhecidos, status (`CONNECTED`, `STALE`, `FAILED`).
  - Campos: endereço IP, porta, namespace, RTT médio, tentativas de reconexão.
  - Definir limites máximos de conexões inbound/outbound e política de expulsão.
- **3.2 Handshake HELLO/HELLO_OK**
  - Implementar `peer_connection.py` com servidor TCP (aceita inbound) e cliente (outbound).
  - Sequência: abrir socket → enviar HELLO → aguardar HELLO_OK → promover conexão ativa.
  - Validar versão e recursos.
  - Registrar fallback para peers que não suportam determinadas `features` (ex.: ACK opcional).
- **3.3 Manutenção de conexões**
  - Threads/event loop para leitura contínua.
  - PING/PONG a cada 30s (configurável) com cálculo de RTT.
  - Atualizar métricas no estado e logs.
  - Validar integridade de mensagens recebidas (JSON, campos obrigatórios, payload < 32 KiB).
- **3.4 Reconexão e backoff**
  - Detectar desconexões e marcar peer como `STALE`.
  - Aplicar backoff exponencial até `max_reconnect_attempts`.
  - Comando `/reconnect` força tentativa imediata.

## 4. Roteamento e Mensageria
- **4.1 Message router**
  - Camada intermediária que recebe comandos da CLI e entrega às conexões ativas.
  - Estruturas de fila opcionais para desacoplar escrita em sockets.
  - Persistir histórico curto (ex.: últimas N mensagens/ACKs) para depuração.
- **4.2 Mensagens `SEND` com ACK**
  - Gerar `msg_id` UUID, preencher `src`, `dst`, payload.
  - Registrar mensagens pendentes; se `ACK` não chegar em 5s → log de timeout.
  - Atualizar UI/log com status entregue/erro.
  - Validar tamanho máximo do `payload` (32 KiB) antes de transmitir.
- **4.3 Mensagens `PUB`**
  - Suportar destinos `*` e `#namespace`.
  - Otimizar para evitar duplicidade ao enviar para peers de múltiplos namespaces.
- **4.4 Encerramento controlado**
  - Implementar BYE/BYE_OK ao fechar CLI ou quando peer remoto solicitar.
  - Garantir liberação de sockets e remoção do `PeerTable`.

## 5. Interface de Linha de Comando (CLI)
- **5.1 Parser e loop principal**
  - Comandos obrigatórios: `/peers`, `/msg`, `/pub *`, `/pub #ns`, `/conn`, `/rtt`, `/reconnect`, `/log`, `/quit`.
  - Fornecer auto-ajuda `/help` exibindo sintaxe.
  - Garantir que entradas do usuário não bloqueiem a thread que recebe mensagens (uso de `selectors`, asyncio ou threads dedicadas).
- **5.2 Integração com cliente**
  - CLI envia eventos para `p2p_client` (via filas, callbacks ou asyncio Queue).
  - Recepção de mensagens deve aparecer em tempo real (ex.: prefixo `[alice@CIC] mensagem`).
  - Integrar níveis de log configurados para exibir apenas mensagens relevantes na CLI.
- **5.3 UX e validações**
  - Feedback textual para sucesso/erro de comandos.
  - Tratativa para namespace inexistente, peer desconhecido, mensagens vazias.
  - Sanitização de entradas (caracteres especiais, limite de tamanho, prevenção de comandos malformados).

## 6. Observabilidade e Logs
- **6.1 Configuração de logging**
  - Logger raiz com níveis dinamicamente ajustáveis (`/log LEVEL`).
  - Formato: timestamp, módulo, nível, mensagem.
  - Prever rotação ou limite de tamanho ao gravar em arquivo.
- **6.2 Métricas utilitárias**
  - Quantidade de conexões ativas (in/out), RTT médio, número de mensagens trocadas.
  - Expor via comando `/rtt` e logs periódicos.
  - Considerar comando dedicado `/metrics` ou equivalente para depuração.
- **6.3 Persistência opcional**
  - Permitir configuração para salvar logs em arquivo (`logs/p2p.log`).

## 7. Testes e Validação
- **7.1 Testes unitários**
  - Cobrir parser de comandos, roteador de mensagens, reconexão/backoff, serialização JSON.
- **7.2 Testes de integração**
  - Scripts em `tools/` para simular sequências (`test_seq*.json`).
  - Caso necessário, mock do rendezvous local.
  - Automatizar cenários mínimos descritos na especificação e inclua no CI local.
- **7.3 Test runbook**
  - Documentar cenários mínimos descritos na especificação.
  - Registrar passos para reproduzir manualmente e critérios de sucesso.
  - Incluir testes específicos para falhas de rede (timeouts, perda de ACK, reconexões).

## 8. Documentação Final
- **8.1 Atualização do `README.md`**
  - Instruções de instalação, uso dos comandos da CLI, exemplos.
  - Incluir diagrama simples da arquitetura/conexões e tabela de compatibilidade (Python, dependências).
- **8.2 Guia de operação**
  - Explicar como configurar namespaces, discovery interval, reconexões.
  - Adicionar seção de troubleshooting com base nos riscos identificados (rendezvous indisponível, NAT, etc.).
- **8.3 Checklist de critérios de avaliação**
  - Tabela marcando cada requisito (Rendezvous, HELLO, PING, SEND, PUB, BYE, CLI, logs).

---

### Dependências e Riscos Principais
- Disponibilidade do servidor Rendezvous público — prever fallback ou simulação local.
- Tratamento de peers atrás de NAT/firewall (escopo limitado a conexões diretas).
- Sincronização entre threads/async (evitar race conditions na `PeerTable`).

### Próximos Passos Recomendados
1. Consolidar gestão de conexões TCP: reaproveitar `PeerConnection` para discagens outbound, reconciliar com a `PeerTable` (limites, retries) e implementar PING/PONG + backoff.
2. Evoluir o `MessageRouter` + CLI: comandos `/msg`, `/pub`, `/conn`, `/rtt`, `/reconnect` enviando mensagens reais (SEND/ACK, PUB) e apresentando feedback em tempo real.
3. Implementar encerramento controlado (BYE/BYE_OK) e automações de reconexão, além de registrar métricas básicas (RTT, mensagens por peer) expostas na CLI/logs.
4. Cobrir com testes (unitários + scripts em `tools/`), atualizar README/guia de operação e preparar checklists finais da RC202502.

### Funcionalidades Ainda Não Implementadas
- Testes unitários e de integração automatizados
- Persistência de logs em arquivo (opcional)
- Validação de tamanho máximo de payload antes do envio

### Notas rápidas
- O servidor Rendezvous é fornecido pronto pelo professor; manter foco apenas no cliente (registro, discovery e conexões diretas).

---

## Status Atual (Atualizado em 2025-11-26)

### Funcionalidades Implementadas ✅

| Requisito | Componente | Status | Descrição |
|-----------|------------|--------|-----------|
| **Rendezvous** | `RendezvousClient` | ✅ Completo | REGISTER/DISCOVER/UNREGISTER funcionais |
| **Configuração** | `ClientSettings` | ✅ Completo | Carregamento via JSON, peer_id, timeouts |
| **PeerTable** | `PeerTable` | ✅ Completo | Thread-safe, status, RTT, reconexão |
| **HELLO/HELLO_OK** | `PeerConnection`, `PeerServer` | ✅ Completo | Handshake bidirecional inbound/outbound |
| **PING/PONG** | `PeerConnection` | ✅ Completo | PINGs a cada 30s, cálculo de RTT |
| **SEND/ACK** | `MessageRouter` | ✅ Completo | Envio com ACK, timeout de 5s |
| **PUB** | `MessageRouter` | ✅ Completo | Broadcast (*) e namespace (#ns) |
| **BYE/BYE_OK** | `MessageRouter` | ✅ Completo | Encerramento gracioso |
| **Reconexão** | `P2PClient` | ✅ Completo | Backoff exponencial, max_attempts |
| **CLI** | `CommandLineInterface` | ✅ Completo | Todos os comandos implementados |
| **Logs** | Logging integrado | ✅ Completo | Níveis ajustáveis via `/log` |

### Comandos CLI Disponíveis

| Comando | Status | Descrição |
|---------|--------|-----------|
| `/peers [*\|#ns]` | ✅ | Lista peers conhecidos |
| `/msg <peer> <msg>` | ✅ | Mensagem direta com ACK |
| `/pub * <msg>` | ✅ | Broadcast global |
| `/pub #<ns> <msg>` | ✅ | Mensagem para namespace |
| `/conn` | ✅ | Mostra conexões ativas |
| `/rtt` | ✅ | Exibe latência por peer |
| `/reconnect` | ✅ | Força reconciliação |
| `/log <nível>` | ✅ | Ajusta nível de log |
| `/help` | ✅ | Mostra ajuda |
| `/quit` | ✅ | Encerra aplicação com BYE |

---

### Comparação com Especificação RC202502

| Critério de Avaliação | Status | Observações |
|-----------------------|--------|-------------|
| 1. Rendezvous (registro, descoberta, unregistro) | ✅ | Funcional |
| 2. Conexão TCP (HELLO/HELLO_OK, PING/PONG) | ✅ | Funcional com RTT |
| 3. Mensageria (SEND/ACK, PUB) | ✅ | Funcional com timeout |
| 4. Encerramento (BYE/BYE_OK) | ✅ | Funcional |
| 5. Reconexão automática | ✅ | Backoff exponencial |
| 6. CLI e Logs | ✅ | Todos os comandos |

### Cenários de Teste Mínimos (da especificação)

| Cenário | Status | Como Testar |
|---------|--------|-------------|
| 1. Conexão direta (SEND/PUB) | ✅ | `/msg peer@ns mensagem` |
| 2. Descoberta automática | ✅ | Inicia automaticamente |
| 3. Keep-alive (PING/PONG + RTT) | ✅ | `/rtt` para ver métricas |
| 4. Reconexão automática | ✅ | Desconectar e aguardar |
| 5. Encerramento (BYE/BYE_OK) | ✅ | `/quit` |
| 6. CLI | ✅ | Todos os comandos |

---

### Diário de Implementação
- **2025-11-17 (Iteração 1)**: Plano em `TASKS.md` revisado com orientações extras de segurança, testes e documentação. Criado esqueleto do pacote `src/client/` (config, state, peer table, rendezvous client, conexões, roteador, keep-alive, CLI, orquestrador e entry-point) contendo comentários sobre funcionalidades pendentes.
- **2025-11-17 (Iteração 2)**: Implementados carregamento de configuração via JSON (`ClientSettings`), cliente de rendezvous com REGISTER/DISCOVER/UNREGISTER reais e integração no `P2PClient` (registro, descoberta inicial e shutdown limpo com tratamento de erros).
- **2025-11-17 (Iteração 3)**: Adicionados worker de descoberta periódica (thread dedicada) e saneamento da `PeerTable` (`mark_missing_as_stale`). `P2PClient` agora mantém sincronização contínua com o rendezvous e protege contra peers obsoletos.
- **2025-11-17 (Iteração 4)**: Criado `PeerServer` (listener TCP) com handshake HELLO/HELLO_OK básico e integração ao `P2PClient`. Servidor abre na porta configurada antes do REGISTER e encerra no shutdown. As conexões ainda são encerradas após o handshake; próxima etapa manterá os sockets para troca de mensagens.
- **2025-11-17 (Iteração 5)**: Implementado `PeerConnection` com handshake HELLO/HELLO_OK persistente, leitura contínua e envio JSON. `PeerServer` agora transfere o socket aceito para o `P2PClient`, que cria/gerencia instâncias de `PeerConnection`, registra callbacks de mensagem/fechamento e encerra todas as conexões durante o shutdown.
- **2025-11-26 (Análise de Branches)**: Relatório completo das branches `main` e `pingpong`. Branch `pingpong` contém PING/PONG com RTT e CLI completa — recomendado merge para `main`.
- **2025-11-26 (Iteração 6 - Merge + Finalização)**: Merge de `pingpong` → `main` realizado. Implementadas funcionalidades restantes:
  - `MessageRouter` completo: SEND/ACK com timeout de 5s, PUB para `*` e `#namespace`, BYE/BYE_OK
  - Reconexão automática com backoff exponencial (`reconnect_backoff_base`) e limite de tentativas (`max_reconnect_attempts`)
  - CLI totalmente funcional com `/msg`, `/pub`, `/reconnect` conectados ao router
  - Callback para exibição de mensagens recebidas em tempo real
  - Envio de BYE para todos os peers durante shutdown gracioso
  - Worker de reconciliação periódica (30s)
  - Verificador de ACK timeouts em thread dedicada

## Cliente P2P - Guia de Instalação e Uso

### Requisitos

- Python 3.10 ou superior
- Conexão com a internet (para acessar o servidor Rendezvous do professor)

### Instalação

1. Clone o repositório:
```bash
git clone https://github.com/leitaonerd/pyp2p-rdv.git
cd pyp2p-rdv
```

2. (Opcional) Crie um ambiente virtual:
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

3. Não há dependências externas - o projeto usa apenas bibliotecas padrão do Python.

### Executando o Cliente

#### Método 1: Execução Direta (Recomendado)

```bash
# No diretório raiz do projeto
python -m src.client.main
```

#### Método 2: Com arquivo de configuração

Crie um arquivo `config.json`:
```json
{
    "name": "seu_nome",
    "namespace": "CIC",
    "rendezvous_host": "pyp2p.mfcaetano.cc",
    "rendezvous_port": 8080,
    "listen_port": 6000
}
```

Execute com:
```bash
python -m src.client.main --config config.json
```

#### Método 3: Com nível de log personalizado

```bash
python -m src.client.main --log-level DEBUG
```

### Configurações Disponíveis

| Parâmetro | Padrão | Descrição |
|-----------|--------|-----------|
| `name` | `alice` | Seu nome de usuário |
| `namespace` | `CIC` | Namespace/sala do chat |
| `rendezvous_host` | `pyp2p.mfcaetano.cc` | Host do servidor Rendezvous |
| `rendezvous_port` | `8080` | Porta do servidor Rendezvous |
| `listen_port` | `6000` | Porta local para receber conexões |
| `ttl_seconds` | `7200` | Tempo de vida do registro (2h) |
| `discovery_interval` | `15.0` | Intervalo de descoberta (segundos) |
| `ping_interval` | `30.0` | Intervalo de PING (segundos) |
| `max_reconnect_attempts` | `5` | Máximo de tentativas de reconexão |

### Comandos da CLI

Uma vez que o cliente esteja rodando, você verá o prompt `pyp2p>`. Os comandos disponíveis são:

| Comando | Descrição | Exemplo |
|---------|-----------|---------|
| `/peers` | Lista todos os peers conhecidos | `/peers` |
| `/peers *` | Lista todos os peers | `/peers *` |
| `/peers #ns` | Lista peers de um namespace | `/peers #CIC` |
| `/msg <peer> <msg>` | Envia mensagem direta | `/msg bob@CIC Olá!` |
| `/pub * <msg>` | Broadcast para todos | `/pub * Olá a todos!` |
| `/pub #ns <msg>` | Mensagem para namespace | `/pub #CIC Olá CIC!` |
| `/conn` | Mostra conexões ativas | `/conn` |
| `/rtt` | Mostra latência (RTT) | `/rtt` |
| `/reconnect` | Força reconexão | `/reconnect` |
| `/log <nivel>` | Ajusta nível de log | `/log DEBUG` |
| `/help` | Mostra ajuda | `/help` |
| `/quit` | Encerra o cliente | `/quit` |

### Testando a Comunicação

#### Passo 1: Inicie o cliente

```bash
python -m src.client.main
```

Você verá algo como:
```
[INFO] Inicializando cliente PyP2P para peer alice@CIC
[INFO] PeerServer escutando em 0.0.0.0:6000
[INFO] Registrado no rendezvous como X.X.X.X:6000
pyp2p>
```

#### Passo 2: Descubra outros peers

```
pyp2p> /peers
```

Se houver outros peers online, você verá a lista deles.

#### Passo 3: Conecte-se a um peer

```
pyp2p> /reconnect
```

Isso força a descoberta e tentativa de conexão com peers disponíveis.

#### Passo 4: Envie uma mensagem

```
pyp2p> /msg bob@CIC Olá Bob, tudo bem?
```

#### Passo 5: Envie broadcast

```
pyp2p> /pub * Mensagem para todos!
```

#### Passo 6: Verifique conexões e latência

```
pyp2p> /conn
pyp2p> /rtt
```

#### Passo 7: Encerre o cliente

```
pyp2p> /quit
```

### Testando com Dois Clientes Localmente

Para testar a comunicação P2P, você pode rodar dois clientes na mesma máquina com portas diferentes:

**Terminal 1:**
```bash
# Crie config1.json
echo {"name": "alice", "namespace": "CIC", "listen_port": 6001} > config1.json
python -m src.client.main --config config1.json
```

**Terminal 2:**
```bash
# Crie config2.json
echo {"name": "bob", "namespace": "CIC", "listen_port": 6002} > config2.json
python -m src.client.main --config config2.json
```

Agora ambos estão registrados no servidor Rendezvous. Use `/reconnect` em ambos para que eles se descubram e conectem, então teste com `/msg`.

### Troubleshooting

#### "Erro de rede com rendezvous"
- Verifique sua conexão com a internet
- Confirme que o servidor `pyp2p.mfcaetano.cc:8080` está acessível
- Tente: `ping pyp2p.mfcaetano.cc`

#### "Não foi possível iniciar PeerServer"
- A porta já está em uso. Altere `listen_port` no config.json

#### "Peer não encontrado"
- O peer pode estar offline ou em outro namespace
- Use `/peers` para ver peers disponíveis
- Use `/reconnect` para atualizar a lista

#### Nenhum peer aparece
- Pode não haver outros peers online no momento
- Teste com dois clientes localmente (veja seção acima)

### Logs e Debug

Para ver logs detalhados:
```bash
python -m src.client.main --log-level DEBUG
```

Ou durante a execução:
```
pyp2p> /log DEBUG
```

Níveis disponíveis: `DEBUG`, `INFO`, `WARNING`, `ERROR`

