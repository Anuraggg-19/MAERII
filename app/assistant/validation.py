import json
import re
import unicodedata
from .providers import ProviderError

def numbers(text):
    # Normalise Devanagari numerals before comparison; punctuation retained.
    text = "".join(str(unicodedata.digit(c)) if c.isdigit() else c for c in text)
    return set(re.findall(r"\d+(?:[.,]\d+)*",text))

def validate_explanation(result, evidence):
    if not isinstance(result,dict) or result.get("answerable") is not True:
        raise ProviderError("insufficient_evidence")
    text = result.get("text")
    refs = result.get("citations")
    if not isinstance(text,str) or not text.strip() or len(text)>1900 or not isinstance(refs,list) or not refs:
        raise ProviderError("invalid_explanation")
    if any(not isinstance(r,str) or r not in evidence for r in refs):
        raise ProviderError("unsupported_reference")
    source = json.dumps(evidence,ensure_ascii=False)
    if numbers(text)-numbers(source) or re.search(r"https?://|<script|javascript:",text,re.I):
        raise ProviderError("unsupported_claim")
    return text, refs

def validate_translation(source, translated):
    if numbers(source) != numbers(translated):
        raise ProviderError("changed_numbers")
    if re.search(r"<script|javascript:",translated,re.I):
        raise ProviderError("invalid_translation")
    return translated
