"""Stable question IDs; language labels are draft translations for pilot review."""
import re
from difflib import SequenceMatcher

ROWS = [
 ("What can MAERII help me do?", "MAERII मुझे कैसे मदद कर सकता है?", "MAERII मला कशी मदत करू शकते?", "help", ""),
 ("How do I get started?", "मैं शुरुआत कैसे करूँ?", "सुरुवात कशी करू?", "help", ""),
 ("How do I find a material?", "मैं सामग्री कैसे खोजूँ?", "साहित्य कसे शोधू?", "help", ""),
 ("What should I do next?", "मुझे आगे क्या करना चाहिए?", "पुढे काय करू?", "help", ""),
 ("What does this term mean?", "इस शब्द का क्या अर्थ है?", "या शब्दाचा अर्थ काय?", "help", ""),
 ("What is this material?", "यह सामग्री क्या है?", "हे साहित्य काय आहे?", "overview", "material"),
 ("What uses are recorded for this material?", "इस सामग्री के कौन से उपयोग दर्ज हैं?", "या साहित्याचे कोणते उपयोग नोंदवले आहेत?", "overview", "material"),
 ("Where is this material found?", "यह सामग्री कहाँ मिलती है?", "हे साहित्य कुठे मिळते?", "overview", "material"),
 ("What properties matter when making products from it?", "उत्पाद बनाने में कौन से गुण महत्वपूर्ण हैं?", "उत्पादने बनवताना कोणते गुण महत्त्वाचे आहेत?", "overview", "material"),
 ("Where does this information come from?", "यह जानकारी कहाँ से आई है?", "ही माहिती कुठून आली?", "help", ""),
 ("What products can I make from this material?", "इस सामग्री से कौन से उत्पाद बना सकता हूँ?", "या साहित्यापासून कोणती उत्पादने बनवू शकतो?", "categories", "categories"),
 ("What skills are needed for this product?", "इस उत्पाद के लिए कौन से कौशल चाहिए?", "या उत्पादनासाठी कोणती कौशल्ये हवीत?", "categories", "categories"),
 ("Which listed products have beginner-level difficulty?", "कौन से उत्पाद शुरुआती स्तर के हैं?", "कोणती उत्पादने नवशिक्यांसाठी आहेत?", "categories", "categories"),
 ("Show the manufacturing steps for this product.", "इस उत्पाद को बनाने के चरण दिखाएँ।", "हे उत्पादन बनवण्याच्या पायऱ्या दाखवा.", "categories", "categories"),
 ("How can I compare the listed products?", "मैं उत्पादों की तुलना कैसे करूँ?", "उत्पादनांची तुलना कशी करू?", "categories", "categories"),
 ("What price range was found?", "कौन सी मूल्य सीमा मिली?", "किंमतीची कोणती श्रेणी आढळली?", "market", "market"),
 ("How recent is the market information?", "बाजार की जानकारी कितनी हाल की है?", "बाजाराची माहिती किती अलीकडची आहे?", "market", "market"),
 ("What does the demand indicator mean?", "माँग संकेतक का क्या अर्थ है?", "मागणी निर्देशकाचा अर्थ काय?", "market", "market"),
 ("Which marketplace listings support this result?", "इस परिणाम के आधार में कौन सी बिक्री सूचियाँ हैं?", "या निकालाला आधार देणाऱ्या विक्री नोंदी कोणत्या?", "market", "market"),
 ("What do I need before getting recommendations?", "सुझाव पाने से पहले क्या चाहिए?", "शिफारशी मिळण्याआधी काय हवे?", "recommendations", ""),
 ("Why was this product recommended to me?", "मुझे इस उत्पाद का सुझाव क्यों मिला?", "मला या उत्पादनाची शिफारस का केली?", "recommendations", "recommendations"),
 ("How were my preferences used?", "मेरी प्राथमिकताओं का उपयोग कैसे हुआ?", "माझ्या पसंतीचा वापर कसा झाला?", "recommendations", "recommendations"),
 ("What costs and profit estimates are included?", "कौन सी लागत और लाभ के अनुमान शामिल हैं?", "कोणते खर्च आणि नफ्याचे अंदाज समाविष्ट आहेत?", "recommendations", "recommendations"),
 ("Explain my marketing and branding suggestions.", "मेरे विपणन और ब्रांडिंग सुझाव समझाएँ।", "माझ्या विपणन व ब्रँडिंग सूचना समजावून सांगा.", "marketing", "marketing"),
 ("Can you explain this result in simpler language?", "क्या यह परिणाम सरल भाषा में समझा सकते हैं?", "हा निकाल सोप्या भाषेत समजावून सांगाल?", "help", "material"),
]
QUESTIONS = {f"Q{i:02}": {"id":f"Q{i:02}","labels":dict(zip(("en-IN","hi-IN","mr-IN"), row[:3])),"section":row[3],"requires":row[4]} for i,row in enumerate(ROWS,1)}
ALIASES = {
 "Q01":["what is maerii", "what can you do"], "Q02":["help me get started", "how to use this website"],
 "Q03":["find a material", "search materials"], "Q04":["what next", "next step"],
 "Q11":["what can i make", "show products", "products from this material"],
 "Q12":["required skills"], "Q14":["manufacturing steps", "how is this product made"],
 "Q16":["price range", "what price was found"], "Q17":["when was market data collected", "data freshness"],
 "Q20":["how do i get recommendations"], "Q21":["why this recommendation"],
 "Q23":["explain estimated profit"], "Q25":["explain this", "simplify this result"],
}

def normalise(text):
    return re.sub(r"[^\w\s]", "", text.casefold()).strip()

def match_question(text):
    text = normalise(text)
    scores = []
    for qid,q in QUESTIONS.items():
        labels = list(q["labels"].values()) + ALIASES.get(qid, [])
        score = max(SequenceMatcher(None,text,normalise(label)).ratio() for label in labels)
        scores.append((score,qid))
    scores.sort(reverse=True)
    if scores[0][0] == 1 or (scores[0][0] >= .86 and scores[0][0]-scores[1][0] >= .10):
        return scores[0][1]
    return None

def suggestions(context, evidence, language):
    blocker = "Q02" if not context.material_id else ("Q04" if "categories" not in evidence else "Q20" if "market" not in evidence else "Q21")
    next_id = "Q11" if "categories" in evidence else "Q04"
    eligible = [q for q in QUESTIONS.values() if not q["requires"] or q["requires"] in evidence]
    def rank(q):
        return (q["section"] == context.section, q["id"] == blocker, q["id"] == next_id, q["id"] in {"Q10","Q17","Q18","Q23"}, -int(q["id"][1:]))
    eligible.sort(key=rank, reverse=True)
    entries = [{"id":q["id"],"label":q["labels"][language],"section":q["section"],"reason":"current_section" if q["section"]==context.section else "workflow_help"} for q in eligible]
    return entries
