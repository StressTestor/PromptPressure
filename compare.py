import json
import argparse
import sys
from typing import List, Dict, Any
from statistics import mean

def load_results(filepath: str) -> Dict[str, Any]:
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
            # Index by 'id' or 'prompt' if 'id' is missing
            return {str(item.get("id", item.get("prompt"))): item for item in data}
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        sys.exit(1)

def calculate_diff(base: Dict[str, Any], candidate: Dict[str, Any]):
    common_ids = set(base.keys()) & set(candidate.keys())
    only_base = set(base.keys()) - set(candidate.keys())
    only_candidate = set(candidate.keys()) - set(base.keys())

    latency_diffs = []
    response_len_diffs = []
    score_diffs = [] # Placeholder if we had standardized scores

    for pid in common_ids:
        b_item = base[pid]
        c_item = candidate[pid]
        
        # Calculate latency diff (assuming 'latency' or similar field exist implicitly or parsed)
        # Note: run_eval.py output doesn't explicitly guarantee a 'latency' field in JSON yet, 
        # but does have 'response' and 'success'. 
        
        b_resp = b_item.get("response", "")
        c_resp = c_item.get("response", "")
        
        response_len_diffs.append(len(c_resp) - len(b_resp))

    return {
        "common_count": len(common_ids),
        "only_base_count": len(only_base),
        "only_candidate_count": len(only_candidate),
        "avg_len_diff": mean(response_len_diffs) if response_len_diffs else 0
    }

def main():
    parser = argparse.ArgumentParser(description="Compare two PromptPressure evaluation JSON files.")
    parser.add_argument("base_file", help="Path to the baseline results JSON")
    parser.add_argument("candidate_file", help="Path to the candidate results JSON")
    args = parser.parse_args()

    base_results = load_results(args.base_file)
    cand_results = load_results(args.candidate_file)

    diff = calculate_diff(base_results, cand_results)

    print(f"--- Comparison Report ---")
    print(f"Baseline:  {args.base_file} ({len(base_results)} items)")
    print(f"Candidate: {args.candidate_file} ({len(cand_results)} items)")
    print(f"Common Items: {diff['common_count']}")
    
    if diff['only_base_count'] > 0:
        print(f"Items only in Baseline: {diff['only_base_count']}")
    if diff['only_candidate_count'] > 0:
        print(f"Items only in Candidate: {diff['only_candidate_count']}")
    
    print(f"\nAverage Response Length Diff: {diff['avg_len_diff']:+.2f} chars")

    # Add more sophisticated logic here (e.g. semantic similarity check)

if __name__ == "__main__":
    main()
