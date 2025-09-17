# Trabalho de Programação — **Chat P2P**

# Sumário

1. [Resumo](#resumo)
2. [Arquitetura P2P: Conceitos, Características e Atuadores](#arquitetura-p2p-conceitos-características-e-atuadores)  
3. [1) Objetivo](#1-objetivo)  
4. [2) Identidade, nomes e escopo](#2-identidade-nomes-e-escopo)  
5. [3) Transporte, codificação e limites](#3-transporte-codificação-e-limites)  
6. [4) Integração com o Servidor Rendezvous](#4-integração-com-o-servidor-rendezvous)  
   - [4.1 REGISTER](#41-register-peer--rendezvous)  
   - [4.2 DISCOVER](#42-discover-peer--rendezvous)  
   - [4.3 UNREGISTER](#43-unregister-peer--rendezvous)  
7. [5) Conexões entre peers](#5-conexões-entre-peers)  
8. [6) Mensagens e roteamento (relay P2P)](#6-mensagens-e-roteamento-relay-p2p)  
9. [7) Tratamento de erros](#7-tratamento-de-erros)  
10. [8) Interface de usuário (CLI)](#8-interface-de-usuário-cli)  
11. [9) Arquitetura (sugestão de módulos)](#9-arquitetura-sugestão-de-módulos)  
12. [10) Observabilidade (mínimo)](#10-observabilidade-mínimo)  
13. [11) Critérios de correção (funcional)](#11-critérios-de-correção-funcional)  
14. [12) Cenários mínimos de teste](#12-cenários-mínimos-de-teste)  
15. [13) Checklist de funcionalidades (para o aluno)](#13-checklist-de-funcionalidades-para-o-aluno)  
16. [Apêndice — Protocolo de Aplicação do Servidor Rendezvous](#apêndice--protocolo-de-aplicação-do-servidor-rendezvous)  

---

## Resumo

> Este trabalho tem como objetivo proporcionar ao aluno o desenvolvimento de conceitos relacionados à arquitetura distribuída de comunicação P2P. Para isso, o aluno deverá implementar uma aplicação cliente de **Chat P2P** que se registra em um **Servidor Rendezvous**, descobre peers, mantém **conexões TCP persistentes (keep-alive)** com peers acessíveis e, quando não houver caminho direto (por exemplo, devido a NAT), **encaminha mensagens por meio de outros peers** (relay P2P).  
> O professor disponibilizou um servidor Rendezvous operacional, acessível online, que implementa o protocolo de aplicação para interação com rendezvous descrito neste documento. Esse servidor deve ser utilizado para registrar peers e obter informações sobre as redes P2P existentes. Ressalta-se que o servidor Rendezvous **não exerce papéis especiais**: sua função é exclusivamente registrar e listar peers. **Qualquer peer acessível pode atuar como relay**.


## Arquitetura P2P: Conceitos, Características e Atuadores

A **arquitetura peer-to-peer (P2P)** constitui um modelo de comunicação distribuída no qual cada nó da rede, denominado *peer*, exerce simultaneamente as funções de cliente e servidor. Diferentemente do paradigma cliente-servidor, em que existe uma entidade central responsável por fornecer serviços, no modelo P2P a interação ocorre de forma descentralizada, com múltiplos pontos de origem e destino. Esse modelo tornou-se amplamente utilizado em aplicações de compartilhamento de arquivos, redes de sobreposição (*overlay networks*), sistemas de mensageria e ambientes colaborativos.

### Características Principais

1. **Descentralização**  
   A inexistência de uma autoridade central reduz o risco de ponto único de falha e distribui a responsabilidade entre os peers. Essa característica aumenta a autonomia da rede e dificulta a censura ou controle centralizado.

2. **Escalabilidade**  
   O aumento no número de participantes contribui positivamente para a capacidade global da rede. Cada peer adicional introduz novos recursos de conectividade e processamento, tornando o sistema naturalmente escalável.

3. **Resiliência**  
   A arquitetura P2P é intrinsecamente tolerante a falhas. A saída de um peer não compromete o funcionamento da rede, uma vez que outros peers podem assumir o encaminhamento ou a redistribuição dos recursos.

4. **Distribuição de Recursos**  
   Dados e serviços são fragmentados e replicados entre diferentes peers. Esse mecanismo evita sobrecarga em um único ponto e promove redundância, o que contribui para maior disponibilidade e desempenho.

5. **Heterogeneidade**  
   Os peers podem apresentar capacidades heterogêneas em termos de largura de banda, poder de processamento e tempo de disponibilidade. Apesar disso, todos podem colaborar de acordo com suas possibilidades, reforçando a flexibilidade do modelo.

6. **Dinamicidade**  
   A rede P2P é marcada por intensa variação na participação dos peers (*churn*). Protocolos e aplicações P2P devem, portanto, lidar com a entrada e saída frequente de nós, preservando a consistência e a utilidade da rede.

### Atores em Uma Redes P2P

No contexto da arquitetura P2P, os atuadores correspondem aos papéis ou funções desempenhadas pelos peers para sustentar o funcionamento da rede:

1. **Peers de Origem e Destino**  
   Responsáveis pela emissão e recepção final de mensagens ou dados. Em um sistema de chat, por exemplo, representam os usuários que trocam mensagens diretamente.

2. **Peers de Encaminhamento (*Relay Peers*)**  
   Fundamentais quando não existe rota direta entre origem e destino, especialmente em cenários com NAT ou firewalls. Esses peers atuam como nós de encaminhamento na camada de aplicação, propagando mensagens até o destino.

3. **Peers de Descoberta**  
   Participam dos mecanismos de identificação e localização de outros nós. No trabalho proposto, **servidor Rendezvous** é o "ponto de encontro" inicial dos peers, responsável por registrar e listar peers ativos. Posteriormente, a descoberta passa a ser descentralizada via mensagens de controle do tipo `WHO_HAS`.

4. **Peers de Observabilidade**  
   Monitoram o estado da rede, incluindo métricas como tempo de resposta (RTT), disponibilidade de rotas e falhas de encaminhamento. Essas informações auxiliam na tomada de decisão sobre o roteamento de mensagens.

### Considerações Finais

A arquitetura P2P representa um paradigma **colaborativo, escalável e resiliente**, no qual cada peer pode assumir diferentes papéis de acordo com sua posição e conectividade na rede. Para que esse modelo funcione de maneira eficiente, é necessário o suporte a mecanismos de **descoberta de peers, encaminhamento de mensagens, tolerância a falhas e atualização dinâmica da topologia**.  

No contexto deste trabalho de programação, a implementação de um cliente P2P permitirá ao estudante vivenciar esses conceitos na prática, ao interagir com o servidor Rendezvous, estabelecer conexões diretas, desempenhar o papel de relay quando necessário e encaminhar mensagens respeitando restrições de tempo de vida (*time-to-live*, TTL) e deduplicação.



---

## 1) Objetivo

- Exercitar conceitos de **arquitetura P2P** e **roteamento na camada de aplicação**.
- Entregar um **cliente único** que:
  1. Interaja via **CLI** (interface textual).
  2. Faça **REGISTER/DISCOVER/UNREGISTER** no Rendezvous.
  3. Construa e mantenha **túneis TCP** com peers acessíveis.
  4. Envie/receba mensagens **unicast**, por **namespace** e **broadcast global**.
  5. **Encaminhe** mensagens para peers inalcançáveis diretamente (relay P2P).
  6. Exponha **observabilidade mínima** (rotas, vizinhos, RTT, erros).

---

## 2) Identidade, nomes e escopo

- **namespace**: agrupador lógico (ex.: `UnB`, `Giga`).
- **name**: identificador único dentro do namespace.
- **peer_id** = `name@namespace` (ex.: `alice@UnB`).  
  > Nota: o Rendezvous **não retorna peer_id diretamente**; o cliente deve compor a string usando `name@namespace`.
- **Escopos de envio**:
  - **Unicast**: para um `peer_id` específico.
  - **Namespace-cast**: para todos do `#namespace`.
  - **Broadcast global**: para `*` (todos os peers conhecidos).

---

## 3) Transporte, codificação e limites

- **Transporte entre peers**: TCP (TLS recomendado).
- **Codificação**: **JSON UTF-8**, **delimitado por `\n`** (uma mensagem por linha).
- **Tamanho máximo por mensagem**: **32 KiB** (32768 bytes).
  - Excedeu → responder `ERROR` com `error:"line_too_long"` e `limit:32768`.
- **Keep-alive**: `PING` a cada **30 s**; desconectar se **3 PINGs** sem `PONG`.
- **TTL padrão (roteamento entre peers)**: **8**.

---

## 4) Integração com o Servidor Rendezvous

O Rendezvous apenas registra e lista peers (sem papéis especiais).  
Cada requisição deve conter o campo `"type"`, e não `"op"`.

### 4.1 `REGISTER` (peer → rendezvous)

**Requisição**
```json
{
  "type": "REGISTER",
  "namespace": "UnB",
  "name": "alice",
  "port": 7070,
  "ttl": 7200
}
```
> Campo `port` é obrigatório.  
> Campo `ttl` é opcional; se omitido, o servidor assume **7200 s** (2 horas).

**Resposta (OK)**
```json
{
  "status": "OK",
  "ttl": 7200,
  "observed_ip": "203.0.113.7",
  "observed_port": 45678
}
```
> O campo `peer_id` **não é retornado** pelo servidor, mas pode ser reconstruído pelo cliente como `name@namespace`.

### 4.2 `DISCOVER` (peer → rendezvous)

**Requisição**
```json
{ "type": "DISCOVER", "namespace": "UnB" }
```

**Resposta (OK)**
```json
{
  "status": "OK",
  "peers": [
    {
      "ip": "203.0.113.7",
      "port": 7070,
      "name": "alice",
      "namespace": "UnB",
      "ttl": 7200,
      "expires_in": 7199,
      "observed_ip": "203.0.113.7",
      "observed_port": 45678
    }
  ]
}
```

**Erros (`DISCOVER`)**  
> O servidor atual só retorna erros genéricos (`bad_namespace`, `invalid_json`, etc.).  
> Não há suporte a `rate_limited` ou `server_busy`.

### 4.3 `UNREGISTER` (peer → rendezvous)

**Requisição**
```json
{ "type": "UNREGISTER", "namespace": "UnB", "name": "alice", "port": 7070 }
```

**Resposta (OK)**
```json
{ "status": "OK" }
```

---

## 5) Conexões entre peers

*(mesma definição anterior, sem alterações — handshake HELLO, PING/PONG, etc.)*

---

## 6) Mensagens e roteamento (relay P2P)

*(mantém como na versão anterior: SEND, PUB, WHO_HAS, etc.)*

---

## 7) Tratamento de erros

**Formato**
```json
{ "status":"ERROR", "error":"<string>", "detail":"<opcional>", "limit":32768 }
```

**Códigos do servidor rendezvous** (já implementados):
- `bad_name`
- `bad_namespace`
- `bad_port`
- `bad_ttl`
- `invalid_json`
- `missing_type`
- `line_too_long`

**Códigos adicionais (camada P2P cliente ↔ cliente)**:
- `ttl_expired`
- `no_route`
- `over_quota`
- `busy`
- `unauthorized`
- `bad_format`

---

## 8) Interface de usuário (CLI)

*(sem mudanças — comandos `/peers`, `/connect`, `/msg`, etc.)*

---

## 9) Arquitetura (sugestão de módulos)

*(sem mudanças — rendezvous_client.py, p2p_transport.py, etc.)*

---

## 10) Observabilidade (mínimo)

*(sem mudanças — /routes, logs, métricas opcionais)*

---

## 11) Critérios de correção (funcional)

1. **REGISTER/DISCOVER/UNREGISTER** funcionando + lista de peers **atualizada** automaticamente.  
2. **Conexões TCP**: aceitar e abrir; `HELLO` e **keep-alive** `PING/PONG`.  
3. **Mensageria**: unicast com `ACK`; namespace-cast/broadcast com deduplicação + TTL.  
4. **Relay P2P**: `WHO_HAS`/`WHO_HAS_HIT`, **cache de rota** e entrega via vizinho.  
5. **Erros/limites**: tratamento de `no_route`, `ttl_expired`, `line_too_long`, etc.  
6. **Observabilidade**: `/routes`, logs mínimos e (se implementado) métricas.

---

## 12) Cenários mínimos de teste

*(mantém os mesmos: direto, NAT moderado, stress)*

---

## 13) Checklist de funcionalidades (para o aluno)

- [ ] CLI com `/peers`, `/connect`, `/msg` (`@peer`, `#namespace`, `*`), `/routes`, `/watch`.  
- [ ] `REGISTER/DISCOVER/UNREGISTER` + atualização automática da lista.  
- [ ] Servidor e cliente TCP entre peers; `HELLO/HELLO_OK`; `PING/PONG`.  
- [ ] Envio `SEND` (unicast) com `ACK` opcional.  
- [ ] `PUB` para `#namespace` e `*` com TTL + deduplicação.  
- [ ] `WHO_HAS` / `WHO_HAS_HIT` para descoberta de rota + **cache**.  
- [ ] Encaminhamento com **TTL**, **deduplicação** e **limites de fila**.  
- [ ] Tratamento de **erros** conforme tabela.  
- [ ] Logs e `/routes` com vizinhos/rotas/RTT.

---

### Apêndice — Protocolo de Aplicação do Servidor Rendezvous

#### Visão Geral

O **servidor rendezvous** atua como um ponto central de encontro para peers em uma rede P2P.  

- Cada **peer** deve **registrar-se** no servidor para ficar visível.  
- Peers podem **descobrir** outros participantes em uma determinada sala (**namespace**).  
- Peers podem também **remover** seu registro (**unregister**).  
- Todos os registros têm um **tempo de vida (TTL)** em segundos. Expirado esse tempo, o registro é descartado automaticamente.  

A comunicação é feita sobre **TCP**. Cada **conexão aceita apenas um comando (uma linha JSON)** e é encerrada após a resposta.

---

#### Formato das mensagens

- Cada mensagem (requisição ou resposta) é um objeto **JSON válido**, enviado em **uma única linha** terminada por `\n`.  
- O servidor impõe um limite de **32 KB por linha**.  
- Se a linha for vazia ou apenas espaços, o servidor responde com um erro.  

---

#### Comandos aceitos

##### 1. `REGISTER`

Registra (ou atualiza) um peer no servidor.

**Campos obrigatórios:**
- `type`: `"REGISTER"`
- `namespace`: string (até 64 caracteres)  
- `name`: string (até 64 caracteres)  
- `port`: inteiro (1–65535)  

**Campos opcionais:**
- `ttl`: inteiro em segundos (1–86400). Se omitido, assume **7200 (2h)**.

**Exemplo de requisição:**
```json
{ "status":"ERROR", "error":"line_too_long", "limit":32768 }
```

**Sem rota (camada P2P)**  
```json
{ "type":"ERROR", "code":"no_route", "ref":"m123", "detail":"carol@UnB not reachable" }
```

**Possíveis erros:**
```json
{ "status": "ERROR", "error": "bad_name" }
{ "status": "ERROR", "error": "bad_namespace" }
{ "status": "ERROR", "error": "bad_port" }
{ "status": "ERROR", "error": "bad_ttl" }
```

---

##### 2. `DISCOVER`

Retorna a lista de peers registrados em um namespace.

**Campos:**
- `type`: `"DISCOVER"`
- `namespace`: string (opcional).  
  - Se omitido, retorna todos os peers de todos os namespaces.
  - `namespace` inexistente, o servidor retorna uma lista vazia.

**Exemplo de requisição:**
```json
{ "type": "DISCOVER", "namespace": "room1" }
```

**Resposta:**
```json
{
  "status": "OK",
  "peers": [
    {
      "ip": "203.0.113.45",
      "port": 4000,
      "name": "peerA",
      "namespace": "room1",
      "ttl": 60,
      "expires_in": 42,
      "observed_ip": "203.0.113.45",
      "observed_port": 54321
    }
  ]
}
```

**Requisição para `namespace` inexistente**
```json
{ "type": "DISCOVER", "namespace": "room1" }
```

**Resposta:**
```json
{"status": "OK", "peers": []}
```

---

##### 3. `UNREGISTER`

Remove peers previamente registrados.

**Campos obrigatórios:**
- `type`: `"UNREGISTER"`
- `namespace`: string 

**Campos opcionais:**
- `name`: string  
- `port`: inteiro  

**Exemplo de requisição:**
```json
{ "type": "UNREGISTER", "namespace": "room1", "name": "peerA", "port": 4000 }
```

**Resposta de sucesso:**
```json
{ "status": "OK" }
```

**Erros possíveis:**
```json
{ "status": "ERROR", "error": "bad_port (abc)" }
```
---

##### 4. Mensagens de Erro Genéricas

- Linha vazia ou só espaços:
```json
{ "status": "ERROR", "message": "Empty request line" }
```

- Linha muito longa (> 32768 bytes):
```json
{ "status": "ERROR", "error": "line_too_long", "limit": 32768 }
```

- Timeout de inatividade:
```json
{ "status": "ERROR", "message": "Timeout: no data received, closing connection" }
```

- Comando desconhecido:
```json
{ "status": "ERROR", "message": "Unknown command" }
```

---

#### Resumo do Ciclo de Uso

1. O cliente se conecta ao servidor rendezvous (TCP/5000 por padrão).  
2. Envia um **REGISTER** para se anunciar.  
3. Usa **DISCOVER** para consultar peers de um namespace.  
4. Pode **UNREGISTER** ao sair.  
5. Se o TTL expirar, o registro desaparece automaticamente.  