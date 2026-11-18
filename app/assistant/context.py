"""Snapshots of responses delivered to this anonymous session, never global latest."""
import json
import re
from datetime import datetime, timezone
from .store import digest

CAPTURE = re.compile(r"^/api/materials/(\d+)(?:/(categories|market|recommend|enhance))?$")
TASKS = {None:"material","categories":"categories","market":"market","recommend":"recommendations","enhance":"marketing"}

def capture(store, scope, material_id, task, payload, ttl):
    if not isinstance(payload,dict) or payload.get("status")=="error":
        return None
    if payload.get("mfp_id",material_id) != material_id:
        return None
    # Snapshot includes the original response and version, not browser-provided text.
    version = payload.get("persistence_run_id") or payload.get("_persistence",{}).get("run_id") or digest(payload)
    ref = digest([scope,material_id,task,version,payload])
    record = {"scope":scope,"material_id":material_id,"task":task,"version":version,"payload":payload,
              "observed_at":payload.get("_persistence",{}).get("created_at"),
              "received_at":datetime.now(timezone.utc).isoformat()}
    store.put("snapshot:"+ref,record,ttl)
    return ref

def resolve(store, scope, context):
    if len(context.refs)>5:
        raise ValueError("Too many context references")
    result = {}
    for task,ref in context.refs.items():
        if task not in TASKS.values() or not re.fullmatch(r"[a-f0-9]{64}",ref):
            raise ValueError("Invalid context reference")
        record = store.get("snapshot:"+ref)
        if not record or record["scope"]!=scope or record["material_id"]!=context.material_id or record["task"]!=task:
            raise PermissionError("Context unavailable in this session")
        result[task] = record
    return result

def products(records):
    categories = records.get("categories",{}).get("payload",{}).get("product_categories",[])
    result = []
    for category in categories:
        for p in category.get("products",[]):
            if isinstance(p,dict):
                result.append(p)
    return result

def render(value, depth=0):
    """Plain text only, deterministic, bounded; labels retained from actual fields."""
    if value is None or value == "" or value == [] or value == {}:
        return ""
    if depth>3:
        return ""
    if isinstance(value,dict):
        return "\n".join(f"{k.replace('_',' ')}: {render(v,depth+1)}" for k,v in list(value.items())[:12] if not k.startswith("_") and render(v,depth+1))
    if isinstance(value,list):
        return "\n".join("• "+render(v,depth+1) for v in value[:10] if render(v,depth+1))
    return str(value)[:600]
