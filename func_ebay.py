# title, description, variant attribute, item specifics 
import pandas as pd 
from pathlib import Path 
from openai import OpenAI 
import json, os, time, math
from typing import Dict, Any, List, Optional 
from decouple import config 
from concurrent.futures import ThreadPoolExecutor, as_completed 

# input_path = 'data/shopify_data.json'
input_path = 'data/ExportData104223.xlsx'
# models = ['gpt-4.1-mini', 'gpt-4.1-nano']
# models = ['gpt-4.1-mini']
# models = ['gpt-4o']
models = ['gpt-4.1-mini', 'gpt-4o']

system_prompt = (
    "You are an eBay listing optimizer."
    "Detect the input language and generate the output (title and description) in the same language. "
)

tools = [
  {
    "type": "function",
    "name": "optimize_for_ebay_title_description",
    "description": "Return an eBay-optimized title and a compliant HTML description.",
    "strict": True,
    "parameters": {
      "type": "object",
      "properties": {
        "ebay_title": {
          "type": "string",
          "maxLength": 80,
          "minLength": 10,
          "description": (
            "A concise, SEO-optimized eBay title that strictly follows platform rules. "
            "It must be a single line (max 80 characters), starting with the brand or product name, "
            "and include one or two key attributes such as model, size, or color. "
            "Avoid all caps (except model codes), emojis, special symbols, duplicate spaces, and promotional or shipping language. "
            "The title should read naturally and match buyer search intent."
          )
        },
        "ebay_description_html": {
          "type": "string",
          "maxLength": 4000,
          "minLength": 40,
          "description": (
            "An HTML-formatted product description that must comply with eBay's mobile and listing standards. "
            "It must begin with a short summary paragraph, followed by 4–6 bullet points that highlight the product’s key features. "
            "If three or more structured attributes are available, a specification table must be included. "
            "Only the following HTML tags are allowed: <b>, <strong>, <br>, <ol>, <ul>, <li>, <table>, <tr>, <td>, "
            "<th>, <thead>, <tbody>, <tfoot>, <caption>, <colgroup>, <col>. "
            "The use of <p> tags is not permitted. All forms of active content (e.g., <script>, <iframe>, <form>, <video>, etc.) are strictly forbidden. "
            "The description must be written in clear, user-friendly language and must not contain promotional phrases, contact details, or external links. "
            "The output must be in the same language as the input; detect and match language automatically."
          )
        }
      },
      "required": ["ebay_title", "ebay_description_html"],
      "additionalProperties": False,
    }
  }
]


def load_products(path: str, sheet: Optional[str|int]=0) -> List[Dict[str, Any]]:
    ext = Path(path).suffix.lower()

    if ext == '.json':
        with open(path, "r", encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict) and 'items' in data:
            return data['items']
        if isinstance(data, list):
            return data

    if ext in ('.xlsx', '.xls'):
        df = pd.read_excel(path, sheet_name=sheet, dtype=str)
        df = df.fillna("")  
        records: List[Dict[str, Any]] = []
        for _, row in df.iterrows():
            item = {
                "id": row.get("Sku", "").strip(),
                "name": row.get("Title", "").strip(),
                "brand": "",  # sheet không có brand, để trống cũng được
                "description": row.get("Description", "").strip(),
                "attributes": row.get("Attributes", "").strip(),  # nếu muốn giữ thêm
            }
            records.append(item)
        return records
        
    

def make_user_prompt(item: Dict[str, Any]) -> str:
    lines = []
    def add(k, v):
        if v is None: return 
        s = str(v).strip()
        if s: lines.append(f"{k}: {s}")
    
    add("Title", item.get('name'))
    if item.get('brand'):
        add("Brand", item.get('brand'))
    add("Description", item.get('description'))

    return (
        "Convert the following Shopify product into an eBay-ready Title and HTML Description. "
        "Return the result using the function `optimize_for_ebay_title_description`.\n\n"
        + "\n".join(lines)
    )

    # return "Convert this Shopify product into an eBay-ready Title & HTML Description.\n" + "\n".join(lines)


def call_once(client: OpenAI, model: str, user_prompt: str) -> Dict:
    start_t = time.perf_counter()
    try:
        resp = client.responses.create(
            model=model,
            input=[
                {'role': "system", "content": system_prompt},
                {'role': 'user', "content": user_prompt}
            ],
            tools=tools,
        )

        end_t = time.perf_counter()

        usage = getattr(resp, "usage", None) or {}
        in_tok = getattr(usage, "input_tokens", None) or usage.get("input_tokens") or 0
        out_tok = getattr(usage, "output_tokens", None) or usage.get("output_tokens") or 0
        total_tok = getattr(usage, "total_tokens", None) or usage.get("total_tokens") or (in_tok + out_tok)

        ebay_title = None
        ebay_desc = None
        for item in resp.output:
            if getattr(item, "type", None) == "function_call":
                args_str = getattr(item, "arguments", "{}")
                try:
                    args = json.loads(args_str)
                except Exception:
                    args = {}
                ebay_title = args.get("ebay_title", ebay_title)
                ebay_desc = args.get("ebay_description_html", ebay_desc)
        
        return {
            "ok": True,
            "model": model,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "total_tokens": total_tok,
            "raw": resp.model_dump() if hasattr(resp, "model_dump") else None,
            "latency_sec": end_t - start_t,
            "ebay_title": ebay_title,
            "ebay_description_html": ebay_desc,
        }
    except Exception as e:
        # time.sleep(0.7 * (2 ** attempt))
        last_err = str(e)
    end_t = time.perf_counter()
    return {"ok": False, "model": model, "error": last_err, "latency_sec": end_t - start_t}


def main():
    client = OpenAI(api_key=config('OPEN_API_KEY'))

    items = load_products(input_path)

    grand_start = time.perf_counter()

    for model in models:
        print(f"\n=== Running model: {model} on {len(items)} items ===")
        model_start = time.perf_counter()


        results = []
        total_in_tok = 0
        total_out_tok = 0
        success = 0
        fail = 0
        latencies = []

        def process_item(item: Dict[str, Any], model: str, client: OpenAI) -> Dict:
            prompt = make_user_prompt(item)
            r = call_once(client, model, prompt)
            r["input_id"] = item.get("id")
            r['shopify_title'] = item.get('name')
            r['shopify_description'] = item.get('description')
            r['shopify_brand'] = item.get('brand')
            return r

        MAX_WORKERS = 10 

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [
                executor.submit(process_item, item, model, client)
                for item in items[:20]
            ]

            for idx, future in enumerate(as_completed(futures)):
                r = future.result()
                lat = r.get("latency_sec", 0.0)
                results.append(r)
                latencies.append(lat)

                if r.get("ok"):
                    success += 1
                    total_in_tok += r.get("input_tokens", 0) or 0
                    total_out_tok += r.get("output_tokens", 0) or 0
                    print(f"[{model}] #{idx}/{len(items)} id={r['input_id']} ✓ {lat:.2f}s "
                        f"(in={r.get('input_tokens',0)}, out={r.get('output_tokens',0)})")
                else:
                    fail += 1
                    print(f"[{model}] #{idx}/{len(items)} id={r['input_id']} ✗ {lat:.2f}s ERROR: {r.get('error')}")

        # for idx, item in enumerate(items):

        #     prompt = make_user_prompt(item)
        #     r = call_once(client, model, prompt)
        #     print(f"RUNNING ITEM {idx}")
        #     r["input_id"] = item.get("id", idx)  
        #     r['shopify_title'] = item.get('name')
        #     r['shopify_description'] = item.get('description')
        #     r['shopify_brand'] = item.get('brand')
        #     results.append(r)

        #     lat = r.get("latency_sec", 0.0)
        #     latencies.append(lat)

        #     if r.get("ok"):
        #         success += 1
        #         total_in_tok += r.get("input_tokens", 0) or 0
        #         total_out_tok += r.get("output_tokens", 0) or 0
        #         print(f"[{model}] #{idx}/{len(items)} id={r['input_id']} ✓ {lat:.2f}s "
        #               f"(in={r.get('input_tokens',0)}, out={r.get('output_tokens',0)})")
        #     else:
        #         fail += 1
        #         print(f"[{model}] #{idx}/{len(items)} id={r['input_id']} ✗ {lat:.2f}s ERROR: {r.get('error')}")

            # break

        out_path = f"output/result_{model}_{time.time() * 1000}.json"
        with open(out_path, "w", encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, default=str, indent=4)
        
        print(f"✓ Wrote {out_path} ({len(results)} items)")

        model_end = time.perf_counter()
        total_time = model_end - model_start
        avg_lat = (sum(latencies) / len(latencies)) if latencies else 0.0
        ips = (len(items) / total_time) if total_time > 0 else 0.0

        print(f"\n--- Summary for {model} ---")
        print(f"Wrote: {out_path} ({len(results)} items)")
        print(f"Success: {success} | Fail: {fail}")
        print(f"Total time: {total_time:.2f}s")
        print(f"Avg latency/item: {avg_lat:.2f}s")
        print(f"Throughput: {ips:.2f} items/sec")
        print(f"Total tokens: in={total_in_tok}, out={total_out_tok}, sum={total_in_tok + total_out_tok}")
    
    grand_end = time.perf_counter()
    print(f"\n=== All models done. Grand total: {grand_end - grand_start:.2f}s ===")

if __name__ == '__main__':
    main()

# python func_ebay.py