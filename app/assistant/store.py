"""Assistant-only persistence and cross-worker atomic trial limits."""
import hashlib
import json
import time
from datetime import datetime, timezone
from app.neo4j_client import session

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()

class LimitError(Exception):
    pass

class Neo4jStore:
    def __init__(self):
        self.initialized = False

    def initialize(self):
        if not self.initialized:
            with session() as db:
                db.run("CREATE CONSTRAINT maerii_assistant_key IF NOT EXISTS FOR (n:AssistantRecord) REQUIRE n.key IS UNIQUE").consume()
                db.run("MERGE (n:AssistantRecord {key:'_lock'}) ON CREATE SET n.counter=0").consume()
            self.initialized = True

    def get(self, key):
        self.initialize()
        with session() as db:
            r = db.run("MATCH (n:AssistantRecord {key:$key}) WHERE n.expires > $now RETURN n.payload AS value", key=key, now=time.time()).single()
        return json.loads(r["value"]) if r else None

    def put(self, key, value, ttl=86400):
        self.initialize()
        with session() as db:
            db.run("MERGE (n:AssistantRecord {key:$key}) SET n.payload=$value,n.expires=$expires", key=key, value=json.dumps(value, ensure_ascii=False), expires=time.time()+ttl).consume()

    def delete(self, key):
        with session() as db:
            db.run("MATCH (n:AssistantRecord {key:$key}) DELETE n", key=key).consume()

    def reserve(self, scope, task, settings, chars=0, lease=None):
        """Reserve before calling. Failures stay counted; not a billing guarantee."""
        self.initialize()
        now = time.time()
        key = "usage:" + datetime.now(timezone.utc).strftime("%Y-%m-%d")
        def run(tx):
            tx.run("MATCH (n:AssistantRecord {key:'_lock'}) SET n.counter=n.counter+1").consume()
            if lease and tx.run("MATCH (n:AssistantRecord {key:$key}) WHERE n.expires>$now RETURN n.key", key="lease:"+lease, now=now).single():
                raise LimitError("busy")
            r = tx.run("MATCH (n:AssistantRecord {key:$key}) RETURN n.payload AS value", key=key).single()
            state = json.loads(r["value"]) if r else {"calls":0,"characters":0,"users":{}}
            user = state["users"].setdefault(scope, {"calls":0,"generations":0,"audio":0,"minute":[]})
            user["minute"] = [x for x in user["minute"] if x > now-60]
            if task == "request":
                if len(user["minute"]) >= 30 or user["calls"] >= 300:
                    raise LimitError("request_limit")
                user["calls"] += 1
                user["minute"].append(now)
            else:
                gen_times = [x for x in user.get("generation_times", []) if x > now-60]
                if state["calls"] >= settings.global_daily_calls or state["characters"] + chars > settings.daily_sarvam_chars:
                    raise LimitError("global_trial_limit")
                if task == "gemini" and (user["generations"] >= settings.daily_limit or len(gen_times) >= 3):
                    raise LimitError("generation_limit")
                if task == "speech" and user["audio"] >= 20:
                    raise LimitError("audio_limit")
                state["calls"] += 1
                state["characters"] += chars
                if task == "gemini":
                    user["generations"] += 1
                    user["generation_times"] = gen_times + [now]
                if task == "speech":
                    user["audio"] += 1
            tx.run("MERGE (n:AssistantRecord {key:$key}) SET n.payload=$v,n.expires=$expiry", key=key, v=json.dumps(state), expiry=now+172800).consume()
            if lease:
                tx.run("MERGE (n:AssistantRecord {key:$key}) SET n.expires=$expiry", key="lease:"+lease, expiry=now+120).consume()
        with session() as db:
            db.execute_write(run)

    def release(self, lease):
        self.delete("lease:"+lease)

    def cleanup(self):
        with session() as db:
            db.run("MATCH (n:AssistantRecord) WHERE n.key <> '_lock' AND n.expires < $now DELETE n", now=time.time()).consume()
