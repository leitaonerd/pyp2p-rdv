# PyP2P - Projeto de Programação P2P
Este projeto foi desenvolvido para a disciplina CIC0124 - Redes de Computadores, do Departamento de Ciência da Computação da Universidade de Brasília. O objetivo deste documento é detalhar os protocolos de camada de aplicação implementados pelo Servidor Rendezvous, bem como os Clientes P2P, que juntos viabilizam uma aplicação de Chat P2P e o mecanismo de *Peer Relay*.



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

{ "type": "REGISTER", "namespace": "UnB", "name": "alice", "port": 4000, "ttl": 3600 }
```

**Resposta de sucesso:**

```json
{"status": "OK", "ttl": 3600, "ip": "45.171.103.246", "port": 4000}
```

**Possíveis erros:**

Seguem alguns exemplo possíveis de erros retornados pelo servidor para requisições `REGISTER` inválidas:

- Quando o valor do campo `name` é inválido (> 64 ou 0 caracteres):

```json
{ "status": "ERROR", "message": "bad_name" }
```

- Quando o valor do campo `namespace` é inválido (> 64 ou 0 caracteres):

```json
{ "status": "ERROR", "message": "bad_namespace" }
```

- Quando o valor do campo `ttl` não é um inteiro.

```json
{ "status": "ERROR", "message": "bad_ttl" }
```

> **Obs:** O valor do campo `ttl` deve estar entre 1 e 86400 (24 horas). Valores fora desse intervalo, o servidor assume `max(1, min(ttl, 86400))` e não retorna erro.

- Quando o valor do campo `port` é inválido (> 65535 ou < 1):

```json
{ "status": "ERROR", "message": "bad_port" }
```

---

##### 2. `DISCOVER`
Retorna a lista de peers registrados em um *namespace*. O servidor **apenas responde** às requisições dos *peers* com registros válidos (não expirados). Para maiores informações, consulte a seção [4. Proteção contra abusos](#4-proteção-contra-abusos).

**Campos:**

- `type`: `"DISCOVER"`
- `namespace`: string (opcional).  
  - Se omitido, retorna todos os peers de todos os namespaces.
  - `namespace` inexistente, o servidor retorna uma lista vazia.

**Exemplo de requisição:**

```json

{ "type": "DISCOVER", "namespace": "UnB" }
```

**Resposta:**

```json
{
  "status": "OK",
  "peers": [
    {
      "ip": "45.171.103.246",
      "port": 4000,
      "name": "alice",
      "namespace": "UnB",
      "ttl": 3600,
      "expires_in": 3527
    }
  ]
}
```

**Requisição omitindo `namespace`**

```json
{ "type": "DISCOVER" }
```

**Resposta:**

```json
{
  "status": "OK",
  "peers": [
    {
      "ip": "45.171.101.167",
      "port": 8081,
      "name": "vm_giga",
      "namespace": "CIC",
      "ttl": 7200,
      "expires_in": 5908
    },
    {
      "ip": "45.171.103.246",
      "port": 4000,
      "name": "alice",
      "namespace": "UnB",
      "ttl": 3600,
      "expires_in": 3592
    }
  ]
}
```

**Requisição para `namespace` inexistente**
```json
{ "type": "DISCOVER", "namespace": "know-without-study" }
```

**Resposta:**
```json
{"status": "OK", "peers": []}
```

**Erros possíveis:**

Seguem alguns exemplo possíveis de erros retornados pelo servidor para requisições `DISCOVER` inválidas:

- Quando o valor do campo `namespace` é inválido (> 64 ou 0 caracteres):

```json
{ "status": "ERROR", "message": "bad_namespace" }
```

- Quando o *peer* que fez a requisição (`IP`) não está registrado:

```json
{ "status": "ERROR", "message": "peer_not_registered" }
```

> **Obs:** Não é possível desregistrar um *peer* que não está registrado.

---

##### 3. `UNREGISTER`

Remove *peers* previamente registrados. O servidor **apenas responde** às requisições dos *peers* com registros válidos (não expirados). Para maiores informações, consulte a seção [4. Proteção contra abusos](#4-proteção-contra-abusos).

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

Seguem alguns exemplo possíveis de erros retornados pelo servidor para requisições `UNREGISTER` inválidas:

- Quando o valor do campo `port` não é um inteiro válido ou está fora do intervalo 1-65535:

```json
{ "status": "ERROR", "message": "bad_port (abc)" }
```

- Quando o valor do campo `namespace` é inválido (> 64 ou 0 caracteres):

```json
{ "status": "ERROR", "message": "bad_namespace" }
```

- Quando o *peer* que fez a requisição não está registrado:

```json
{ "status": "ERROR", "message": "peer_not_registered" }
```

- Quando o campo **obrigatório** `namespace` está ausente na requisição:

```json
{ "status": "ERROR", "message": "namespace_required" }
```

- Quando o *peer* que fez a requisição não corresponde ao registro (`IP`) ou algum campo informado é divergente ao registrado (`namespace`, `port` ou `name`):

```json
{ "status": "ERROR", "message": "peer_credentials_do_not_match" }
```
> **Dica:** realize o debug do código utilizando o comando **`DISCOVER`** para verificar os dados registrados do *peer*. 

- Quando o *peer* que fez a requisição (`IP`) não está registrado:

```json
{ "status": "ERROR", "message": "peer_not_registered" }
```

> **Obs:** Não é possível desregistrar um *peer* que não está registrado.

---

##### 4. Proteção contra abusos

Para evitar abusos, o servidor impõe as seguintes restrições:

- Cada *peer* pode encaminhar 50 requisições por minuto. Excedido esse limite, o servidor passa a não atender as requisições e a responder com erro e fecha a conexão. O usuário fica banido por 1 minuto. Passado esse período, o servidor passa a liberar o acesso novamente.

**Resposta exemplo para um IP bloqueado:**

```json
{
  "status": "ERROR",
  "message": "Connection from 203.0.113.42:40046 has been blocked due to excessive login attempts (limit: 50). The block will be lifted in 59 seconds."
}
```

- É obrigatório fazer o registro antes de usar DISCOVER ou UNREGISTER. Caso contrário, o servidor responde com erro e fecha a conexão. Quando o *peer* que fez a requisição (`IP`) não está registrado:

```json
{ "status": "ERROR", "message": "peer_not_registered" }
```

---

##### 5. Mensagens de Erro Genéricas

- Linha vazia ou só espaços:
```json
{ "status": "ERROR", "message": "Empty request line" }
```

- Linha muito longa (> 32768 bytes):
```json
{ "status": "ERROR", "message": "line_too_long", "limit": 32768 }
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

1. O cliente se conecta ao servidor rendezvous (IP: pyp2p.mfcaetano.cc e TCP/8080 por padrão).  
2. Envia um **REGISTER** para se anunciar.  
3. Usa **DISCOVER** para consultar peers de um namespace.  
4. Pode **UNREGISTER** ao sair.  
5. Se o TTL expirar, o registro desaparece automaticamente.  

---

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
