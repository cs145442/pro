
import json
import sys

def debug_dataset(path):
    print(f"Loading {path}...")
    with open(path, 'r') as f:
        data = json.load(f)
    print(f"Loaded {len(data)} items.")
    
    case = data[0]
    print(f"First case: {case.get('id')}")
    print(f"Keys: {list(case.keys())}")
    
    if "oracle_tests" in case:
        print(f"oracle_tests type: {type(case['oracle_tests'])}")
        print(f"oracle_tests len: {len(case['oracle_tests'])}")
        print(f"oracle_tests keys: {list(case['oracle_tests'].keys())}")
    else:
        print("oracle_tests key MISSING in first case")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        debug_dataset(sys.argv[1])
    else:
        print("Usage: python debug_shadow.py <path_to_dataset>")
