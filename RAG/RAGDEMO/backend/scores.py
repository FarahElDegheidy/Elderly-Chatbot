import asyncio
import json
from Intent_classifier_new import classify_query_groq

INPUT_FILE = "C:\Users\HP\VSCODE\Elderly Chatbot\RAG\RAGDEMO\backend\dataset.jsonl"
OUTPUT_FILE = "llama4_results.jsonl"

async def run_eval_from_dataset():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        test_cases = [json.loads(line) for line in f]

    results = []
    for i, case in enumerate(test_cases, 1):
        query = case.get("query", "")
        context = case.get("context", "")
        true_intent = case.get("intent", "")

        print(f"\n🧪 Query {i}: {query}")
        llama4_pred = classify_query_groq(query, context, verbose=False)

        print(f"✅ Expected: {true_intent} | 🔍 Predicted: {llama4_pred.strip()}")

        results.append({
            "query": query,
            "context": context,
            "true_intent": true_intent,
            "llama4_pred": llama4_pred.strip()
        })

    # Save results to JSONL
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n📄 Evaluation complete. Saved to {OUTPUT_FILE}")

# Run it
asyncio.run(run_eval_from_dataset())
