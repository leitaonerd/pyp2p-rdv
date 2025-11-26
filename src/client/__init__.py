"""Client runtime package for the PyP2P peer implementation.

Módulos do cliente:
- ``config`` carrega parâmetros de arquivo JSON e variáveis de ambiente.
- ``p2p_client`` orquestra registro, descoberta, CLI e shutdown limpo.
- ``rendezvous_connection`` encapsula as chamadas ao servidor rendezvous.
- ``peer_connection`` contém as operações de socket, handshake HELLO e PING/PONG.
- ``peer_server`` aceita conexões inbound e aplica o handshake HELLO/HELLO_OK.
- ``message_router`` centraliza o envio/roteamento (SEND, PUB, BYE, ACK).
- ``peer_table`` e ``state`` modelam o estado compartilhado entre módulos.
- ``cli`` expõe a interface interativa de comandos.
"""
