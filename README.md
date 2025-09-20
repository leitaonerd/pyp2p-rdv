# PyP2P - Projeto de Programação P2P

Este é um projeto de programação para a disciplina de Redes de Computadores, do Departamento de Ciências da Computação da Universidade de Brasília. Objetivo desta página é descrever os protocolos de camada de aplicação implementados pelo Servidor Rendezvous e os Clientes P2P que implementam uma aplicação de Chat P2P e *Peer Relay*.

## Rendezvous - Protocolo de Aplicação do Servidor Rendezvous

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

1. O cliente se conecta ao servidor rendezvous (TCP/8888 por padrão).  
2. Envia um **REGISTER** para se anunciar.  
3. Usa **DISCOVER** para consultar peers de um namespace.  
4. Pode **UNREGISTER** ao sair.  
5. Se o TTL expirar, o registro desaparece automaticamente.  
