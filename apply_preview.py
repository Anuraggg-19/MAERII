import json
import sys
from pathlib import Path

def apply_preview(preview_file_path: str):
    preview_path = Path(preview_file_path)
    if not preview_path.exists():
        print(f"Error: Preview file not found at {preview_path}")
        return

    print(f"Loading preview from {preview_path}...")
    with open(preview_path, "r", encoding="utf-8") as f:
        preview_data = json.load(f)

    # 1. Load canonical datasets
    enriched_path = Path("data/enriched_mfp_data.json")
    evidence_path = Path("data/deep_enrichment_evidence.json")
    relationships_path = Path("data/material_relationships.json")

    with open(enriched_path, "r", encoding="utf-8") as f:
        working_items = json.load(f)
    
    evidence_store = {}
    if evidence_path.exists():
        with open(evidence_path, "r", encoding="utf-8") as f:
            evidence_store = json.load(f)
            
    relationship_list = []
    if relationships_path.exists():
        with open(relationships_path, "r", encoding="utf-8") as f:
            relationship_list = json.load(f)
    
    relationship_index = {edge["edge_id"]: edge for edge in relationship_list if edge.get("edge_id")}

    # 2. Apply preview data
    item_index = {item["mfp_id"]: idx for idx, item in enumerate(working_items)}
    
    items_applied = 0
    for preview_item in preview_data.get("items", []):
        mfp_id = preview_item["mfp_id"]
        
        # Attach deep enrichment block
        idx = item_index.get(mfp_id)
        if idx is not None:
            working_items[idx]["deep_enrichment"] = preview_item["deep_enrichment"]
            items_applied += 1
            
        # Add evidence
        for record in preview_item.get("evidence_records", []):
            evidence_store[record["evidence_id"]] = record
            
        # Add relationships
        for edge in preview_item.get("relationship_edges", []):
            relationship_index[edge["edge_id"]] = edge

    # 3. Save back to disk
    print(f"Saving {items_applied} items to enriched_mfp_data.json...")
    with open(enriched_path, "w", encoding="utf-8") as f:
        json.dump(working_items, f, indent=2, ensure_ascii=False)

    print(f"Saving {len(evidence_store)} evidence records...")
    with open(evidence_path, "w", encoding="utf-8") as f:
        json.dump(evidence_store, f, indent=2, ensure_ascii=False)

    print(f"Saving {len(relationship_index)} relationship edges...")
    with open(relationships_path, "w", encoding="utf-8") as f:
        json.dump(list(relationship_index.values()), f, indent=2, ensure_ascii=False)

    print("\n[OK] Preview successfully applied without hitting APIs again!")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python apply_preview.py path/to/preview.json")
    else:
        apply_preview(sys.argv[1])
