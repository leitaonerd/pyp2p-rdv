"""Client runtime package for the PyP2P peer implementation.

The modules inside this package are intentionally lightweight skeletons:
- ``config`` carrega parâmetros e descreve como tratar segredos/overrides.
- ``p2p_client`` orquestra registro, descoberta, CLI e shutdown limpo.
- ``rendezvous_connection`` encapsula as chamadas ao servidor rendezvous.
- ``peer_connection`` contém as operações de socket e handshake HELLO.
- ``peer_server`` aceita conexões inbound e aplica o handshake HELLO/HELLO_OK.
- ``message_router`` centraliza o envio/roteamento (SEND, PUB, BYE, ACK).
- ``keep_alive`` gerencia PING/PONG e métricas de RTT.
- ``peer_table`` e ``state`` modelam o estado compartilhado entre módulos.
- ``cli`` expõe a interface interativa.

Cada módulo inclui comentários/TODOs com as funcionalidades que ainda
precisam ser implementadas de acordo com a especificação oficial.
"""
