from core.intent_classifier import classify_intent

cases = [
    ("why is the auth broken",         "debug"),
    ("error in the ranking function",   "debug"),
    ("when did I add the voice search", "recall"),
    ("what was the lancedb fix",        "recall"),
    ("how does the context engine work","architecture"),
    ("why did we choose lancedb",       "architecture"),
    ("how to configure the daemon",     "implementation"),
    ("lancedb schema",                  "general"),
]

for query, expected in cases:
    label, _ = classify_intent(query)
    status = "OK  " if label == expected else "FAIL"
    print(f"{status}  [{label:>14}]  {query}")
