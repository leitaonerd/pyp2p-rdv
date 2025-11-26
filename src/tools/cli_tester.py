#!/usr/bin/env python3

import logging
import sys
import os

src_path = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(src_path))

try:
    from client.cli import CommandLineInterface
    from client.peer_table import PeerTable
    from client.message_router import MessageRouter
    from client.state import ClientRuntimeState, PeerInfo
except ImportError as e:
    print(f"Erro de importação: {e}")
    print("Diretório atual:", os.getcwd())
    print("Diretório do script:", os.path.dirname(__file__))
    sys.exit(1)


class MockP2PClient:
    def __init__(self):
        self.connections = {}
        self.settings = self._create_mock_settings()
        self._create_mock_connections()
    
    def _create_mock_settings(self):
        from client.config import ClientSettings
        return ClientSettings()

    def _create_mock_connections(self):
        self.connections = {
            "alice@CIC": MockConnection("alice@CIC", True, 0.089, 15),
            "bob@CIC": MockConnection("bob@CIC", False, 0.125, 8),
            "charlie@REDES": MockConnection("charlie@REDES", True, 0.350, 3),
        }
    
    def get_connection_metrics(self):
        total_connections = len(self.connections)

        total_rtt = 0
        count_rtt = 0
        healthy_connections = 0
        
        connections_detail = {}
        for peer_id, conn in self.connections.items():
            metrics = conn.get_metrics()
            connections_detail[peer_id] = metrics
            
            if metrics["avg_rtt"] > 0:
                total_rtt += metrics["avg_rtt"]
                count_rtt += 1
                healthy_connections += 1
        
        avg_rtt = total_rtt / count_rtt if count_rtt > 0 else 0
        
        return {
            "total_connections": total_connections,
            "connections": connections_detail,
            "summary": {
                "avg_rtt": avg_rtt,
                "healthy_connections": healthy_connections
            }
        }
    
    def shutdown(self):
        print("P2PClient shutdown chamado")


class MockConnection:
    def __init__(self, peer_id, is_outbound, avg_rtt, rtt_samples):
        self.peer_id = peer_id
        self.is_outbound = is_outbound
        self.avg_rtt = avg_rtt
        self.rtt_samples = rtt_samples
        self.active = True
    
    def get_metrics(self):
        return {
            "peer_id": self.peer_id,
            "is_outbound": self.is_outbound,
            "avg_rtt": self.avg_rtt,
            "rtt_samples": self.rtt_samples,
            "active": self.active
        }


def setup_test_environment():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    peer_table = PeerTable()
    test_peers = [
        PeerInfo("alice@CIC", "192.168.1.10", 8000, "CONNECTED", "CIC"),
        PeerInfo("bob@CIC", "192.168.1.11", 8001, "CONNECTED", "CIC"),
        PeerInfo("charlie@REDES", "192.168.1.12", 8002, "CONNECTED", "REDES"),
        PeerInfo("diana@CIC", "192.168.1.13", 8003, "STALE", "CIC"),
        PeerInfo("eve@SEC", "192.168.1.14", 8004, "FRESH", "SEC"),
    ]
    
    for peer in test_peers:
        peer_table.upsert_peer(peer)
    
    state = ClientRuntimeState()
    router = MessageRouter(peer_table, state)
    mock_client = MockP2PClient()
    
    cli = CommandLineInterface(router, peer_table, mock_client)
    return cli


def main():
    print("=== TESTE COMANDOS ===")
    print("-" * 50)
    
    cli = setup_test_environment()
    
    print("\n1. Testando /peers:")
    cli._cmd_peers([])
    
    print("\n2. Testando /conn:")
    cli._cmd_conn()
    
    print("\n3. Testando /rtt:")
    cli._cmd_rtt()
    
    print("\n4. Testando /help:")
    cli._cmd_help()

if __name__ == "__main__":
    main()