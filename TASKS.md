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
- Fluxo completo de envio/roteamento de SEND/ACK e PUB (incluindo geração de `msg_id`, filas de saída e tratamento de timeouts).
- BYE/BYE_OK e encerramento gracioso por peer, com limpeza coordenada das conexões.
- Reconexão automática com política de backoff e limites configuráveis.
- Observabilidade expandida: logs estruturados, métricas em tempo real e histórico de mensagens para depuração.

### Notas rápidas
- O servidor Rendezvous é fornecido pronto pelo professor; manter foco apenas no cliente (registro, discovery e conexões diretas).

---

## Status das Branches (Atualizado em 2025-11-26)

### Branch `main`
**Status: Base funcional, CLI e PING/PONG ausentes**

| Componente | Status | Descrição |
|------------|--------|-----------|
| `ClientSettings` | ✅ Completo | Carregamento de configuração via JSON |
| `RendezvousClient` | ✅ Completo | REGISTER/DISCOVER/UNREGISTER funcionais |
| `PeerTable` | ✅ Completo | Registro thread-safe de peers com status |
| `PeerServer` | ✅ Completo | Listener TCP com handshake HELLO/HELLO_OK |
| `PeerConnection` | ✅ Completo | Conexões inbound/outbound com leitura contínua |
| `P2PClient` | ✅ Completo | Orquestrador com registro, discovery worker, shutdown |
| `CommandLineInterface` | ⚠️ Stub | Loop existe mas apenas ecoa comandos |
| `MessageRouter` | ⚠️ Stub | Estrutura existe mas sem lógica de envio |
| `KeepAliveManager` | ⚠️ Stub | Thread roda mas não envia PINGs |
| PING/PONG + RTT | ❌ Ausente | Não implementado |
| SEND/ACK | ❌ Ausente | Não implementado |
| BYE/BYE_OK | ❌ Ausente | Não implementado |

### Branch `pingpong`
**Status: Adiciona PING/PONG e CLI completa — PRONTO PARA MERGE**

| Componente | Status | Descrição |
|------------|--------|-----------|
| PING/PONG + RTT | ✅ Implementado | PINGs a cada 30s, cálculo de RTT, métricas |
| CLI Completa | ✅ Implementado | Todos os comandos: `/peers`, `/msg`, `/pub`, `/conn`, `/rtt`, `/reconnect`, `/log`, `/quit`, `/help` |
| `P2PClient` melhorias | ✅ Implementado | `connect_to_peer()`, `reconcile_peer_connections()`, `get_connection_metrics()` |
| CLI Tester | ✅ Novo | Ferramenta `src/tools/cli_tester.py` para testes manuais |
| SEND/ACK real | ⚠️ Parcial | CLI prepara mensagens mas `MessageRouter` não está conectado |
| PUB broadcast | ⚠️ Parcial | CLI prepara mas não envia realmente |
| Reconexão automática | ⚠️ Stub | Método existe mas não implementado |

**Arquivos modificados em `pingpong`:**
- `src/client/cli.py` (+280 linhas) — CLI completa
- `src/client/p2p_client.py` (+74 linhas) — Métodos de conexão e métricas
- `src/client/peer_connection.py` (+87 linhas) — PING/PONG e RTT
- `src/tools/cli_tester.py` (novo) — Ferramenta de teste

**Recomendação:** Fazer merge de `pingpong` → `main` para incorporar PING/PONG e CLI.

---

### Diário de Implementação
- **2025-11-17 (Iteração 1)**: Plano em `TASKS.md` revisado com orientações extras de segurança, testes e documentação. Criado esqueleto do pacote `src/client/` (config, state, peer table, rendezvous client, conexões, roteador, keep-alive, CLI, orquestrador e entry-point) contendo comentários sobre funcionalidades pendentes.
- **2025-11-17 (Iteração 2)**: Implementados carregamento de configuração via JSON (`ClientSettings`), cliente de rendezvous com REGISTER/DISCOVER/UNREGISTER reais e integração no `P2PClient` (registro, descoberta inicial e shutdown limpo com tratamento de erros).
- **2025-11-17 (Iteração 3)**: Adicionados worker de descoberta periódica (thread dedicada) e saneamento da `PeerTable` (`mark_missing_as_stale`). `P2PClient` agora mantém sincronização contínua com o rendezvous e protege contra peers obsoletos.
- **2025-11-17 (Iteração 4)**: Criado `PeerServer` (listener TCP) com handshake HELLO/HELLO_OK básico e integração ao `P2PClient`. Servidor abre na porta configurada antes do REGISTER e encerra no shutdown. As conexões ainda são encerradas após o handshake; próxima etapa manterá os sockets para troca de mensagens.
- **2025-11-17 (Iteração 5)**: Implementado `PeerConnection` com handshake HELLO/HELLO_OK persistente, leitura contínua e envio JSON. `PeerServer` agora transfere o socket aceito para o `P2PClient`, que cria/gerencia instâncias de `PeerConnection`, registra callbacks de mensagem/fechamento e encerra todas as conexões durante o shutdown.
- **2025-11-26 (Análise de Branches)**: Relatório completo das branches `main` e `pingpong`. Branch `pingpong` contém PING/PONG com RTT e CLI completa — recomendado merge para `main`.
