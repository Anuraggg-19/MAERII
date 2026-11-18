"""Plain-language display only. Never change the captured evidence or infer facts."""

INTERNAL = {
    "confidence", "confidence_score", "id", "mfp_id", "run_id", "version",
    "provider", "model", "status", "cached", "cache_hit", "elapsed_seconds",
    "persistence_run_id", "fallback_used", "received_at", "created_at",
}
LABELS = {
    "scientific_name": "Scientific name", "category": "Material group",
    "current_products": "Products already recorded", "potential_products": "Possible products to explore",
    "states": "States listed in MAERII", "districts": "Districts listed in MAERII",
    "water_resistance": "Resistance to water", "workability": "Ease of working with it",
    "biodegradability": "How it breaks down naturally", "required_skills": "Skills needed",
    "manufacturing_process": "Suggested steps", "difficulty": "Skill level",
    "estimated_cost": "Estimated cost", "estimated_cost_inr": "Estimated cost (INR)",
    "unit_cost_inr": "Estimated cost per item (INR)", "selling_price_inr": "Suggested selling price per item (INR)",
    "expected_selling_price_inr": "Expected selling price (INR)", "profit_margin_percent": "Estimated profit margin (%)",
    "market_summary": "Market overview", "price_range": "Recorded price range",
    "min": "Lowest", "max": "Highest", "avg_price": "Average listed price",
    "min_price": "Lowest listed price", "max_price": "Highest listed price",
    "total_products": "Listings found", "matched_products": "Listings matched to this material",
    "demand_score": "Demand indicator (not confirmed sales)", "market_potential": "Recorded market potential",
    "recorded_constraints": "Preferences used", "artisan_skill_level": "Your skill level",
    "budget_constraint": "Your budget", "production_time": "Time available",
    "region_context": "Your region", "cultural_motifs": "Preferred local designs",
    "recommendations": "Suggested products", "product_categories": "Product groups",
    "enhancement": "Business suggestions", "material": "About this material", "graph": "Related information",
    "reasoning": "Why it was suggested", "rationale": "Why it was suggested",
    "reason": "Why it was suggested", "why_recommended": "Why it was suggested",
    "recommendation_reason": "Why it was suggested", "limitation": "Please note",
    "url": "View listing", "link": "View listing", "source": "Listed by",
}


def present(value, depth=0):
    """Readable bounded sections, without IDs, confidence scores or JSON wrappers."""
    if value is None or value == "" or value == [] or value == {} or depth > 5:
        return ""
    if isinstance(value, dict):
        title = next((value[k] for k in ("product_name", "name", "title", "category_name")
                      if isinstance(value.get(k), str) and value[k].strip()), "")
        lines = [title] if title else []
        for key, item in list(value.items())[:40]:
            if key.startswith("_") or key in INTERNAL or key in {"product_name", "name", "title", "category_name"}:
                continue
            text = present(item, depth + 1)
            if text:
                if key in {"description", "summary"}:
                    lines.append(text)
                else:
                    label = LABELS.get(key, key.replace("_", " ").capitalize())
                    lines.append(f"{label}: {text}")
        return "\n\n".join(lines)
    if isinstance(value, list):
        items = [present(item, depth + 1) for item in value[:10]]
        return "\n\n".join(items if any("\n" in item for item in items) else
                             ["- " + item for item in items if item])
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)[:600]


def names(value):
    items = value if isinstance(value, list) else [value]
    result = []
    for item in items:
        name = item.get("name") if isinstance(item, dict) else item
        if isinstance(name, str) and name.strip() and name.strip() not in result:
            result.append(name.strip())
    return ", ".join(result[:15])


def location_answer(material, graph):
    states, districts = names(graph.get("states")), names(graph.get("districts"))
    if not states and not districts:
        return ""
    name = material.get("name") or "This material"
    lines = []
    if states:
        lines.append(f"MAERII lists {name} in these states: {states}.")
    if districts:
        lines.append(f"Districts listed: {districts}.")
    else:
        lines.append("The record does not name specific districts.")
    lines.append("This is recorded location information, not a list of sellers or a guarantee that stock is available. Check availability locally before travelling or buying.")
    return "\n\n".join(lines)


def shorten(text, limit=1600):
    if len(text) <= limit:
        return text
    shortened = text[:limit].rsplit("\n\n", 1)[0]
    if not shortened:
        shortened = text[:limit].rsplit(" ", 1)[0] + "…"
    return shortened + "\n\nOpen the relevant section of MAERII for the remaining details."
