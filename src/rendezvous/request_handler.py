import json
from models import PeerRecord
from datetime import datetime, timezone
import logging

log = logging.getLogger("Handler")

class RequestHandler:
    def __init__(self, peer_db):
        self.peer_db = peer_db

    def handle(self, request, client_ip, observed_port=None):
        cmd = request.command
        args = request.args
        
        if cmd == "REGISTER":
            namespace = request.args.get("namespace")
            name = request.args.get("name")
            port = request.args.get("port")
            ttl = request.args.get("ttl", 7200)
            
            log.info(
                "REGISTER from ip=%s obs_port=%s ns=%r name=%r port=%r ttl=%r",
                client_ip, observed_port, namespace, name, port, ttl
            )
            
            
            # TTL clamp (1 .. 86400)
            try:
                ttl = int(ttl)
                if ttl < 1 or ttl > 86400:
                    ttl = max(1, min(ttl, 86400))
            except (ValueError, TypeError):
                log.warning("REGISTER invalid (ttl)")
                return json.dumps({"status": "ERROR", "error": "bad_ttl"})
            
            #lets validate required fields
            if not isinstance(namespace, str) or not namespace or len(namespace) > 64:
                log.warning("REGISTER invalid (namespace)")
                return json.dumps({"status": "ERROR", "error": "bad_namespace"})
            try:
                port = int(port)
                if not (1 <= port <= 65535):
                    raise ValueError()
            except (ValueError, TypeError):
                log.warning("REGISTER invalid (port)")
                return json.dumps({"status": "ERROR", "error": "bad_port"})
            
            try:
                peer = PeerRecord(
                    ip=client_ip,
                    port=int(args.get("port")),
                    name=args.get("name"),
                    namespace=args["namespace"],
                    ttl=ttl,
                    timestamp=datetime.now(timezone.utc),
                    observed_ip=client_ip,
                    observed_port=observed_port
                )
                self.peer_db.add_peer(peer)
                
                log.info("REGISTER OK: %s:%d ns=%s ttl=%d", peer.ip, peer.port, peer.namespace, peer.ttl)
                
                return json.dumps({
                    "status": "OK",
                    "ttl": peer.ttl,
                    "observed_ip": peer.observed_ip,       
                    "observed_port": peer.observed_port    
                })  
                          
            except Exception as e:
                log.exception("REGISTER failed")
                return json.dumps({"status": "ERROR", "message": str(e)})

            
        elif cmd == "DISCOVER":
            namespace = args.get("namespace")
            peers = self.peer_db.get_peers(namespace)
            
            peer_list = [{
                "ip": p.ip,
                "port": p.port,
                "name": p.name,
                "namespace": p.namespace,
                "ttl": p.ttl,
                "observed_ip": p.observed_ip,
                "observed_port": p.observed_port
            } for p in peers]
            
            log.info("DISCOVER ns=%r -> %d peer(s)", namespace, len(peer_list)) 
            
            return json.dumps({"status": "OK", "peers": peer_list})
        
        elif cmd == "UNREGISTER":
            try:
                namespace = args.get("namespace")
                self.peer_db.remove_peer(client_ip, namespace)
                
                log.info("UNREGISTER ip=%s ns=%r OK", client_ip, namespace)

                return json.dumps({"status": "OK"})
            
            except Exception as e:
                log.exception("UNREGISTER failed")
                return json.dumps({"status": "ERROR", "message": str(e)})

        log.warning("Unknown command: %s", cmd)
        return json.dumps({"status": "ERROR", "message": "Unknown command"})    

