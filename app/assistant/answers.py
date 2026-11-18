from .content import tr, GLOSSARY
from .context import products
from .presentation import present, location_answer, shorten

def build(qid, request, records):
    """Return template/localised text OR English data, never generate intelligence."""
    lang = request.language
    data = {k:v["payload"] for k,v in records.items()}
    material = data.get("material",{}).get("material",{})
    graph = data.get("material",{}).get("graph",{})
    choices = []
    action = None
    status = "answered"
    template = {"Q01":"welcome","Q02":"start","Q03":"find","Q10":"provenance","Q15":"compare","Q18":"demand","Q20":"prerequisites"}.get(qid)
    if qid=="Q04":
        template = "start" if not request.context.material_id else "prerequisites"
    if template:
        action = "search" if qid in {"Q02","Q03"} else "categories" if qid in {"Q04","Q15"} else "recommendations" if qid=="Q20" else None
        return tr(template,lang), lang, status, choices, action
    if qid=="Q05":
        term = (request.term or "").casefold().strip()
        if term not in GLOSSARY:
            return tr("term",lang),lang,"needs_clarification",list(GLOSSARY),None
        return GLOSSARY[term],"en-IN",status,[],None
    value = None
    if qid=="Q06": value = {k:material.get(k) for k in ("name","scientific_name","description","category")}
    if qid=="Q07": value = {k:graph.get(k) for k in ("current_products","potential_products")}
    if qid=="Q08": value = {k:graph.get(k) for k in ("states","districts")}
    if qid=="Q09": value = {k:material.get(k) for k in ("strength","flexibility","texture","water_resistance","workability","biodegradability")}
    listed = products(records)
    if qid in {"Q11","Q13"}:
        value = [{"name":p.get("name"),"difficulty":p.get("difficulty"),"estimated_cost":p.get("estimated_cost")} for p in listed if qid=="Q11" or str(p.get("difficulty","")).casefold() in {"easy","beginner","low"}]
    if qid in {"Q12","Q14"}:
        product = next((p for p in listed if p.get("name")==request.context.product),None)
        if not product:
            return tr("choose",lang),lang,"needs_clarification",[p["name"] for p in listed if p.get("name")],None
        value = product.get("required_skills" if qid=="Q12" else "manufacturing_process")
    market = data.get("market",{})
    if qid=="Q16":
        summary = market.get("market_summary",{})
        value = summary
    if qid=="Q17" and "market" in records:
        r = records["market"]
        return ("Observation date: "+str(r.get("observed_at") or "unknown")+". Received by this assistant: "+r["received_at"]+". Receipt date is not a verified market observation date."),"en-IN",status,[],None
    if qid=="Q19":
        value = [{k:p.get(k) for k in ("title","name","product_name","price","source","url","link")} for p in market.get("top_products",[])[:5]]
    if qid in {"Q21","Q22","Q23"}:
        rec = data.get("recommendations",{})
        items = rec.get("recommendations",[])
        chosen = next((p for p in items if p.get("product_name")==request.context.product),None)
        if qid!="Q22" and not chosen:
            return tr("choose",lang),lang,"needs_clarification",[p["product_name"] for p in items if p.get("product_name")],None
        if qid=="Q22":
            value = {"recorded_constraints":rec.get("constraints"),"fallback_used":rec.get("fallback_used"),"provider":rec.get("provider"),"limitation":"The exact influence of each preference is not recorded; I cannot infer it."}
        elif qid=="Q21":
            value = {k:chosen.get(k) for k in ("product_name","reasoning","rationale","reason","demand_score","market_potential","difficulty","why_recommended","recommendation_reason")}
        else:
            value = {k:v for k,v in chosen.items() if any(t in k for t in ("cost","profit","margin","price","financial"))}
    if qid=="Q24": value = data.get("marketing",{}).get("enhancement")
    if qid=="Q25":
        task = request.context.section
        if task=="overview": task="material"
        value = data.get(task)
    text = location_answer(material, graph) if qid == "Q08" else present(value)
    if not text:
        return tr("missing",lang),lang,"missing_evidence",[],action
    intro = {
        "Q06": "Here is what MAERII records about this material:",
        "Q07": "These are the recorded uses and possible products:",
        "Q09": "These properties describe what the material is like:",
        "Q11": "Here are the products listed for this material:",
        "Q12": "For the product you selected, these skills are listed:",
        "Q13": "These products are marked as easier to make:",
        "Q14": "Here are the suggested steps for the product you selected:",
        "Q16": "Here is a summary of the market listings you loaded:",
        "Q19": "Here are some of the listings behind the market results:",
        "Q21": "Here is the recorded reason for this suggestion:",
        "Q22": "These are the preferences recorded with your recommendations:",
        "Q23": "Here are the recorded financial estimates for your selected product:",
        "Q24": "Here are the business suggestions for your selected product:",
        "Q25": "Here are the main details from the section you are viewing:",
    }.get(qid)
    if intro:
        text = intro + "\n\n" + text
    text = shorten(text)
    caution = {
        "Q11": "Costs are estimates. Check local costs before investing.",
        "Q13": "Easy does not mean risk-free. Get practical training before starting.",
        "Q14": "These are suggestions, not a verified safety procedure. Ask a trained practitioner before trying them.",
        "Q16": "Online listings show asking prices, not confirmed sales. Check the quantity and date before comparing prices.",
        "Q19": "These are online listings, not verified suppliers or proof of sales.",
        "Q23": "These are estimates, not guaranteed earnings. Confirm costs, quantity and selling price locally.",
        "Q24": "These are suggestions to review, not proven sales results.",
    }.get(qid)
    if caution:
        text += "\n\n" + caution
    return text,"en-IN",status,choices,action
