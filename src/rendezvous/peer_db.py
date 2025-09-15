import json
import os
from models import PeerRecord
from datetime import datetime
import threading, tempfile
from dataclasses import asdict
import logging

log = logging.getLogger("peer_db")

class PeerDatabase:
    def __init__(self, filename="peers.json"):
        self.filename = filename
        self._lock = threading.Lock()
        self.peers = self._load()

    def _load(self):
        if not os.path.exists(self.filename):
            log.info("Peer DB file not found (%s); starting empty", self.filename)
            return []

        try:
            with open(self.filename, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except json.JSONDecodeError:
            log.error("File %s is corrupted; starting empty", self.filename)
            return []

        records = []
        for peer in raw:
            data = dict(peer)  # cópia
            ts = data.get("timestamp")

            # Converte para datetime, se vier string ou epoch
            if isinstance(ts, str):
                s = ts.strip()
                # trata "Z" (UTC) em Python < 3.11
                if s.endswith("Z"):
                    s = s[:-1] + "+00:00"
                data["timestamp"] = datetime.fromisoformat(s)
            elif isinstance(ts, (int, float)):
                data["timestamp"] = datetime.fromtimestamp(ts)
            # se já for datetime, deixa como está

            records.append(PeerRecord(**data))
            
        log.info("Loaded %d peer(s) from %s", len(records), self.filename)
        return records


    def _save(self):
        tmpf = self.filename + ".tmp"

        # prepara conteúdo serializável
        payload = []
        for p in self.peers:
            d = dict(p.__dict__)  # se for dataclass, poderia usar asdict(p)
            ts = d.get("timestamp")
            if isinstance(ts, datetime):
                d["timestamp"] = ts.isoformat()
            else:
                # se por algum motivo já for str/epoch, garante string ISO
                d["timestamp"] = datetime.fromisoformat(str(ts)).isoformat() if isinstance(ts, str) \
                                else datetime.fromtimestamp(float(ts)).isoformat()
            payload.append(d)

        with self._lock:
            with open(tmpf, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmpf, self.filename)
            
            log.info("Saved %d peer(s) into %s", len(self.peers), self.filename)

    def _sweep(self):
        before = len(self.peers)
        self.peers = [p for p in self.peers if not p.is_expired()]
        expired = before - len(self.peers)
        if expired:
            log.info("Expired %d peer(s) removed", expired)


    def add_peer(self, peer: PeerRecord):
        self._sweep()
        self.peers.append(peer)
        self._save()

    def remove_peer(self, ip, namespace):
        before = len(self.peers)
        self.peers = [p for p in self.peers if not (p.ip == ip and p.namespace == namespace)]
        removed = before - len(self.peers)
        log.info("Removed %d peer(s) ip=%s ns=%s", removed, ip, namespace)
        self._save()

        

    def get_peers(self, namespace=None):
        self._sweep()
        if namespace:
            return [p for p in self.peers if p.namespace == namespace]
        return self.peers
    
    def get_all_db(self):
        return self.peers
