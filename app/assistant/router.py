"""New endpoints and passive response-context bridge, isolated from business logic."""
import json
import logging
import re
import secrets
from http.cookies import SimpleCookie
from urllib.parse import urlsplit
from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool
from .config import Settings, LANGUAGES
from .context import CAPTURE, TASKS, capture
from .providers import ProviderError
from .schemas import Question, AudioRequest, Feedback, Context
from .service import AssistantService
from .store import Neo4jStore, digest, LimitError

settings = Settings()
store = Neo4jStore()
service = AssistantService(store,settings)
router = APIRouter(prefix="/api/assistant",tags=["assistant"])
COOKIE = "maerii_assistant"
log = logging.getLogger(__name__)

def session_scope(request):
    if not settings.enabled:
        raise HTTPException(404,"Assistant disabled")
    origin = request.headers.get("origin")
    if origin and origin != str(request.base_url).rstrip("/"):
        raise HTTPException(403,"Cross-origin assistant request denied")
    if request.headers.get("sec-fetch-site")=="cross-site":
        raise HTTPException(403,"Cross-site assistant request denied")
    token = request.cookies.get(COOKIE,"")
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}",token):
        raise HTTPException(401,"Open the assistant to start a session")
    scope = digest(token)
    if not store.get("session:"+scope):
        raise HTTPException(401,"Assistant session expired; reopen it")
    return scope

def invoke(callback):
    try:
        return callback()
    except HTTPException:
        raise
    except PermissionError:
        raise HTTPException(403,"Context is unavailable in this assistant session") from None
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from None
    except LimitError:
        raise HTTPException(429,"Assistant limit reached or request in progress. Try again later.") from None
    except ProviderError:
        raise HTTPException(503,"Language service unavailable; text remains available") from None
    except Exception:
        log.warning("Assistant dependency unavailable",exc_info=False)
        raise HTTPException(503,"Assistant storage unavailable. Main application is unaffected.") from None

def create_session(response, token=None):
    token = token if token and re.fullmatch(r"[A-Za-z0-9_-]{43}",token) and store.get("session:"+digest(token)) else secrets.token_urlsafe(32)
    store.put("session:"+digest(token),{"active":True},settings.session_ttl)
    response.set_cookie(COOKIE,token,max_age=settings.session_ttl,httponly=True,secure=settings.secure_cookie,samesite="strict",path="/")
    response.headers["Cache-Control"] = "no-store"
    return token

@router.get("/capabilities")
def capabilities(request: Request,response: Response):
    if not settings.enabled:
        return {"enabled":False}
    def action():
        if request.headers.get("sec-fetch-site")=="cross-site":
            raise HTTPException(403,"Cross-site request denied")
        create_session(response,request.cookies.get(COOKIE))
        return {"enabled":True,"languages":LANGUAGES,"explanation":settings.ready("gemini"),"audio":settings.ready("sarvam"),
                "trial_confirmed":settings.trial_confirmed,"audio_unavailable_reason":settings.speech_unavailable_reason(),
                "translation":settings.ready("sarvam"),"language_review":"pilot_draft", "limits":{"daily_generations":settings.daily_limit}}
    return invoke(action)

@router.post("/suggestions")
def suggest(body: Question,request: Request):
    def action():
        scope=session_scope(request)
        store.reserve(scope,"request",settings)
        return service.suggestions(scope,body)
    return invoke(action)

@router.post("/answer")
def answer(body: Question,request: Request):
    def action():
        result=service.answer(session_scope(request),body)
        return {k:v for k,v in result.items() if k!="scope"}
    return invoke(action)

@router.post("/audio")
def audio(body: AudioRequest,request: Request):
    def action():
        scope=session_scope(request)
        store.reserve(scope,"request",settings)
        return {"url":"/api/assistant/audio/"+service.audio(scope,body.answer_id)}
    return invoke(action)

@router.get("/audio/{audio_id}")
def audio_file(audio_id:str,request:Request):
    def action():
        scope=session_scope(request)
        if not re.fullmatch(r"[a-f0-9]{64}",audio_id):
            raise HTTPException(404,"Audio unavailable")
        item=store.get("audio:"+audio_id)
        if not item or item["scope"]!=scope:
            raise PermissionError()
        item_answer=store.get("handle:"+item["answer_id"])
        if not item_answer or item_answer["scope"]!=scope:
            raise PermissionError()
        service.records(scope,Context(**item_answer["context"]))
        path=settings.audio_dir/(audio_id+".wav")
        if not path.is_file():
            raise HTTPException(404,"Audio expired")
        return FileResponse(path,media_type="audio/wav",headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})
    return invoke(action)

@router.post("/feedback")
def feedback(body:Feedback,request:Request):
    def action():
        scope=session_scope(request)
        store.reserve(scope,"request",settings)
        item=store.get("handle:"+body.answer_id)
        if not item or item["scope"]!=scope:
            raise PermissionError()
        store.put("feedback:"+digest([scope,body.answer_id]),{"question_id":item.get("question_id"),"helpful":body.helpful},2592000)
        return {"saved":True}
    return invoke(action)

class AssistantContextMiddleware:
    """Capture ONLY newly delivered main-workflow responses; no calls to generators.

    Enabled only by flag. Failures must never change the main response status/body.
    The context reference is bound to an HttpOnly anonymous-session cookie.
    """
    def __init__(self, app):
        self.app=app

    async def __call__(self, scope, receive, send):
        if scope["type"]!="http" or not settings.enabled:
            return await self.app(scope,receive,send)
        path=scope.get("path","")
        match=CAPTURE.fullmatch(path)
        root=path=="/" and scope["method"]=="GET"
        eligible=match and ((match[2] is None and scope["method"]=="GET") or (match[2] and scope["method"]=="POST"))
        if not root and not eligible:
            return await self.app(scope,receive,send)
        cookie=SimpleCookie()
        try:
            cookie.load(dict(scope["headers"]).get(b"cookie",b"").decode())
            token=cookie[COOKIE].value if COOKIE in cookie else None
            response=Response()
            if root:
                token=await run_in_threadpool(create_session,response,token)
            elif not token or not re.fullmatch(r"[A-Za-z0-9_-]{43}",token) or not await run_in_threadpool(store.get,"session:"+digest(token)):
                return await self.app(scope,receive,send)
        except Exception:
            return await self.app(scope,receive,send)
        start=None
        chunks=[]
        length=0
        bypass=False
        async def observe(message):
            nonlocal start,length,bypass
            if message["type"]=="http.response.start":
                start=message.copy()
                start["headers"]=list(message["headers"])
                if root:
                    start["headers"] += [(k,v) for k,v in response.raw_headers if k in (b"set-cookie",b"cache-control")]
                    await send(start)
                    bypass=True
                return
            if message["type"]!="http.response.body" or bypass:
                return await send(message)
            chunks.append(message)
            length+=len(message.get("body",b""))
            if length>2_000_000:
                await send(start)
                for chunk in chunks: await send(chunk)
                chunks.clear()
                bypass=True
                return
            if not message.get("more_body",False):
                if start["status"]==200:
                    try:
                        payload=json.loads(b"".join(c.get("body",b"") for c in chunks))
                        ref=await run_in_threadpool(capture,store,digest(token),int(match[1]),TASKS[match[2]],payload,settings.session_ttl)
                        if ref: start["headers"].append((b"x-maerii-assistant-context",ref.encode()))
                    except Exception:
                        pass
                await send(start)
                for chunk in chunks: await send(chunk)
        await self.app(scope,receive,observe)
