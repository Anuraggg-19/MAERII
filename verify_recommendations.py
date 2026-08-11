import json
import sys
import os

# Append current directory so we can import app modules
sys.path.append(os.getcwd())

from app.product_service import _LLMClient
from app.recommendation_service import generate_recommendations, get_cached_product_categories

# A dummy market context since we just want to test the recommendation generation
mc = {
    'market_summary': {'demand_score': 80, 'avg_price': 100},
    'top_products': []
}

# The MFPs to verify (103 = Buransh, 109 = Kokum)
mfps_to_test = [103, 109]

print("=====================================================")
print(" VERIFYING CONSTRAINT-AWARE RECOMMENDATION ALGORITHM ")
print("=====================================================")

for mfp_id in mfps_to_test:
    print(f"\n[+] Testing MFP ID {mfp_id}")
    
    # Make sure we have cached categories, if not skip
    cats = get_cached_product_categories(mfp_id)
    if not cats:
        print(f"    -> No cached categories for {mfp_id}, skipping.")
        continue
        
    try:
        # Config A: Beginner / Low Budget / Quick turnaround
        print("    -> Generating Config A (Beginner | Low Budget | Quick Turnaround)...")
        res_a = generate_recommendations(
            mfp_id=mfp_id,
            artisan_skill_level='Beginner',
            budget_constraint='Low',
            production_time='Quick turnaround',
            region_context='All listed regions',
            cultural_motifs=None,
            market_context=mc
        )
        prods_a = set([r['product_name'] for r in res_a['recommendations']])
        
        # Config B: Advanced / High Budget / Long-term
        print("    -> Generating Config B (Advanced | High Budget | Long-term)...")
        res_b = generate_recommendations(
            mfp_id=mfp_id,
            artisan_skill_level='Advanced',
            budget_constraint='High',
            production_time='Long-term',
            region_context='All listed regions',
            cultural_motifs=None,
            market_context=mc
        )
        prods_b = set([r['product_name'] for r in res_b['recommendations']])
        
        print("\n    [RESULTS]")
        print(f"    Config A Products: {', '.join(prods_a)}")
        print(f"    Config B Products: {', '.join(prods_b)}")
        
        overlap = prods_a.intersection(prods_b)
        if len(overlap) == 0:
            print(f"\n    [SUCCESS] Zero overlap! The recommendations for MFP {mfp_id} are completely distinct based on constraints.")
        else:
            print(f"\n    [WARNING] Overlap detected: {overlap}")
            
    except Exception as e:
        print(f"    ERROR generating for {mfp_id}: {e}")
