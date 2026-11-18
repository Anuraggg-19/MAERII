import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse
from .answers import build
from .catalogue import QUESTIONS, match_question, suggestions
from .config import VERSION
from .content import tr, GLOSSARY
from .context import resolve, render
from .providers import Providers, ProviderError
from .store import digest, LimitError
from .validation import validate_explanation, validate_translation

EXPLAIN = {"Q09","Q21","Q22","Q23","Q24","Q25"}

class AssistantService:
    def __init__(self, store, settings, providers=None):
        self.store, self.settings = store, settings
        self.providers = providers or Providers(settings)

    def records(self, scope, context):
        return resolve(self.store,scope,context)

    def suggestions(self, scope, request):
        records = self.records(scope,request.context)
        all_questions = suggestions(request.context,records,request.language)
        return {"suggestions":all_questions[:5],"more":all_questions[5:],"context":request.context.model_dump()}

    def provider_call(self, scope, task, key, callback, chars=0):
        # A second cache check inside the lease closes the cache-miss race.
        result_key = "provider:" + task + ":" + key
        cached = self.store.get(result_key) if task != "speech" else None
        if cached is not None:
            return cached["value"]
        self.store.reserve(scope,task,self.settings,chars=chars,lease=key)
        try:
            cached = self.store.get(result_key) if task != "speech" else None
            if cached is not None:
                return cached["value"]
            value = callback()
            if task != "speech":
                self.store.put(result_key,{"value":value},self.settings.answer_ttl)
            # Usage record contains counts only, no prompts or keys.
            self.store.put("call:"+digest([scope,key,time.time_ns()]),{"task":task,"characters":chars,"completed":True},172800)
            return value
        finally:
            self.store.release(key)

    def localise(self, scope, text, language):
        if language=="en-IN":
            return text, "en-IN", []
        key = digest([VERSION,"translation",scope,text,language,self.settings.translation_model])
        cached = self.store.get("translation:"+key)
        if cached:
            return cached["text"],language,[]
        if not self.settings.ready("sarvam"):
            return text,"en-IN",[tr("translation",language)]
        try:
            # Protect material aliases and units with stable markers. Validate all markers.
            protected = {}
            pattern = r"https?://\S+|\b(?:Rangeeni lac|Kusmi lac|mahua|kokum|shellac|lac|kg|INR|MSP|MFP)\b"
            def shield(match):
                marker = f"ZXTERM{len(protected)}XZ"
                protected[marker] = match.group()
                return marker
            source = re.sub(pattern,shield,text,flags=re.I)
            def translate():
                output = self.providers.translate(source,language)
                for marker,original in protected.items():
                    if output.count(marker)!=1:
                        raise ProviderError("changed_term")
                    output = output.replace(marker,original)
                return validate_translation(text,output)
            translated = self.provider_call(scope,"translation",key,translate,len(source))
            self.store.put("translation:"+key,{"text":translated},self.settings.answer_ttl)
            return translated,language,[]
        except (ProviderError,LimitError):
            return text,"en-IN",[tr("translation",language)]

    def answer(self, scope, request):
        self.store.reserve(scope,"request",self.settings)
        if bool(request.question_id)==bool(request.text):
            raise ValueError("Supply exactly one question ID or text")
        if request.question_id and request.question_id not in QUESTIONS:
            raise ValueError("Unknown question")
        records = self.records(scope,request.context)
        qid = request.question_id or match_question(request.text)
        canonical = request.model_dump()
        if qid:
            canonical.update(question_id=qid,text=None)
        key = digest([VERSION,scope,canonical,{k:v["version"] for k,v in records.items()},self.settings.gemini_model,self.settings.translation_model])
        cached = self.store.get("answer:"+key)
        if cached:
            return {**cached,"cache_hit":True}
        status, choices, action = "answered", [], None
        lang = request.language
        text_lang = lang
        mode = "template"
        warnings = []
        if qid:
            required = QUESTIONS[qid]["requires"]
            if required and required not in records:
                text,status = tr("missing",lang),"missing_evidence"
            else:
                text,text_lang,status,choices,action = build(qid,request,records)
                mode = "data" if text_lang=="en-IN" and qid not in {"Q01","Q02","Q03","Q04","Q10","Q15","Q18","Q20"} else "template"
        else:
            # Known glossary retrieval first, followed by conservative domain screening.
            query = request.text.casefold()
            glossary = next((v for term,v in GLOSSARY.items() if re.search(r"(?<!\w)"+re.escape(term)+r"(?!\w)",query)),None)
            if glossary:
                text,text_lang,mode = glossary,"en-IN","data"
            else:
                text,status = tr("scope",lang),"out_of_scope"
            name = records.get("material",{}).get("payload",{}).get("material",{}).get("name","")
            domain = bool(records) and (bool(name) and name.casefold() in query or any(w in query for w in ("material","product","market","recommend","सामग्री","उत्पाद","बाजार","साहित्य","शिफारस")))
            forbidden = any(w in query for w in ("ignore instructions","system prompt","api key","password","javascript","politics","president"))
            if domain and not forbidden:
                mode,status = "custom","answered"
                text = tr("unavailable",lang)
            elif not glossary:
                status = "needs_clarification" if len(query.split())<4 else "out_of_scope"
                text = tr("clarify" if status=="needs_clarification" else "scope",lang)
        references = [{"id":task,"type":"application_record", "version":r["version"],"observed_at":r.get("observed_at"),"received_at":r["received_at"],"label":"Stored information; may include estimates/generated suggestions"} for task,r in records.items()]
        if status=="answered" and records and (qid in EXPLAIN or mode=="custom"):
            if self.settings.ready("gemini"):
                evidence = {task:render(r["payload"])[:3000] for task,r in records.items()}
                try:
                    question = request.text or QUESTIONS[qid]["labels"]["en-IN"]
                    question += "\nSelected product: " + (request.context.product or "not selected")
                    def explain():
                        output,usage = self.providers.explain(question,evidence)
                        validated = validate_explanation(output,evidence)
                        self.store.put("tokens:"+key,{"usage":usage,"model":self.settings.gemini_model},172800)
                        return validated
                    text,cites = self.provider_call(scope,"gemini",key,explain)
                    text_lang,mode = "en-IN","gemini"
                    references = [r for r in references if r["id"] in cites]
                except (ProviderError,LimitError):
                    warnings.append(tr("unavailable",lang))
                    if mode=="custom": status="provider_unavailable"
            else:
                warnings.append(tr("unavailable",lang))
                if mode=="custom": status="provider_unavailable"
        if text_lang=="en-IN" and lang!="en-IN":
            text,text_lang,translation_warnings = self.localise(scope,text,lang)
            warnings += translation_warnings
        result = {"answer_id":key,"question_id":qid,"text":text,"language":text_lang,"requested_language":lang,
                  "status":status,"mode":mode,"cache_hit":False,"references":references,"warnings":warnings,
                  "choices":choices,"action":action,"context":request.context.model_dump(),
                  "audio_available":self.settings.ready("sarvam") and len(text)<=2500,
                  "audio_unavailable_reason":self.settings.speech_unavailable_reason() or ("answer_too_long" if len(text)>2500 else None),
                  "scope":scope}
        # Keep an authorisation handle even for fallback, but do not cache transient failures.
        self.store.put("handle:"+key,result,self.settings.answer_ttl)
        if status=="answered" and not warnings:
            self.store.put("answer:"+key,result,self.settings.answer_ttl)
        return result

    def audio(self, scope, answer_id):
        answer = self.store.get("handle:"+answer_id)
        if not answer or answer["scope"]!=scope:
            raise PermissionError("Answer unavailable")
        # Recheck all source handles, so expired/revoked context cannot serve old audio.
        from .schemas import Context
        self.records(scope,Context(**answer["context"]))
        key = digest([VERSION,scope,answer["text"],answer["language"],self.settings.speech_model,self.settings.voice])
        record = self.store.get("audio:"+key)
        path = self.settings.audio_dir / (key+".wav")
        if record and path.is_file():
            return key
        if not self.settings.ready("sarvam"):
            raise ProviderError("speech_unavailable")
        def generate():
            if self.store.get("audio:"+key) and path.is_file():
                return
            binary = self.providers.speech(answer["text"],answer["language"])
            path.parent.mkdir(parents=True,exist_ok=True)
            temporary = path.with_suffix(".part")
            temporary.write_bytes(binary)
            temporary.replace(path)
            self.store.put("audio:"+key,{"scope":scope,"answer_id":answer_id},self.settings.answer_ttl)
        self.provider_call(scope,"speech",key,generate,len(answer["text"]))
        return key
