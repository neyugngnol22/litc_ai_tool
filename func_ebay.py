# title, description, variant attribute, item specifics 

from openai import OpenAI 
import json, os, time, math
from typing import Dict, Any, List  
from decouple import config 

input_path = 'data/shopify_data.json'
models = ['gpt-4.1-mini', 'gpt-4.1-nano']

system_prompt = (
    "You are an eBay listing optimizer. "
    "Rules: Title <=80 chars, one line, no spam or all-caps. "
    "Description <=4000 chars, mobile-friendly HTML with lead + bullets; "
    "Allowed tags: <b>, <strong>, <br>, <ol>, <ul>, <li>, <table>, <tr>, <td>, <th>, <thead>, <tbody>, <tfoot>, <caption>, <colgroup>, <col>. "
    "No active content (script/iframe/object/embed/applet/form/input/button/video/audio/canvas/svg/style). "
    "Return results strictly via function call."
)

tools = [
  {
    "type": "function",
    "name": "optimize_for_ebay_title_description",
    "description": "Return an eBay-optimized title (<=80 chars) and a compliant HTML description (<=4000 chars, no active content).",
    "strict": True,
    "parameters": {
      "type": "object",
      "properties": {
        "ebay_title": {
          "type": "string",
          "maxLength": 80,
          "minLength": 10,
          "description": (
            "Rules:\n"
            "- ≤ 80 characters; one line (no newline).\n"
            "- Start with brand/product; add 1–2 key details (model/size/color/material).\n"
            "- No spammy phrases (e.g., FREE, BEST DEAL, 100%, GUARANTEED, SALE), no emojis.\n"
            "- Avoid ALL-CAPS except model codes; no duplicate spaces.\n"
            "- Natural, relevant keywords only."
          )
        },
        "ebay_description_html": {
          "type": "string",
          "maxLength": 4000,
          "minLength": 40,
          "description": (
            "Rules:\n"
            "- ≤ 4000 characters; mobile-friendly HTML.\n"
            "- Structure: short lead paragraph (2–3 sentences) + 3–8 bullet points; optional simple specs table.\n"
            "- Allowed tags only: <p>, <b>, <strong>, <br>, <ol>, <ul>, <li>, <table>, <tr>, <td>, "
            "<th>, <thead>, <tbody>, <tfoot>, <caption>, <colgroup>, <col>.\n"
            "- Do NOT use active content or disallowed tags: script, iframe, object, embed, applet, form, "
            "input, button, video, audio, canvas, svg, style, link, meta.\n"
            "- Accurate, non-promotional language; no external links/contact info."
          )
        }
      },
      "required": ["ebay_title", "ebay_description_html"],
      "additionalProperties": False,
    }
  }
]


def load_products(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, dict) and 'items' in data:
        return data['items']
    if isinstance(data, list):
        return data 
    

def make_user_prompt(item: Dict[str, Any]) -> str:
    lines = []
    def add(k, v):
        if v is None: return 
        s = str(v).strip()
        if s: lines.append(f"{k}: {s}")
    
    add("Title", item.get('name'))
    add("Brand", item.get('brand'))
    add("Description", item.get('description'))

    return "Convert this Shopify product into an eBay-ready Title & HTML Description.\n" + "\n".join(lines)


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
            "ebay_title": ebay_title,
            "ebay_description_html": ebay_desc,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "total_tokens": total_tok,
            "raw": resp.model_dump() if hasattr(resp, "model_dump") else None,
            "latency_sec": end_t - start_t
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

        for idx, item in enumerate(items):
            prompt = make_user_prompt(item)
            r = call_once(client, model, prompt)
            print(f"RUNNING ITEM {idx}")
            r["input_id"] = item.get("id", idx)  
            r['shopify_title'] = item.get('name')
            r['shopify_description'] = item.get('description')
            r['shopify_brand'] = item.get('brand')
            results.append(r)

            lat = r.get("latency_sec", 0.0)
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