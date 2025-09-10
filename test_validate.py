import json
import re, time 
import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from bs4 import BeautifulSoup
except ImportError:
    raise SystemExit("Please install BeautifulSoup4: pip install beautifulsoup4")

EMOJI_RE = re.compile(
    "["                       # common emoji ranges
    "\U0001F300-\U0001F5FF"   # symbols & pictographs
    "\U0001F600-\U0001F64F"   # emoticons
    "\U0001F680-\U0001F6FF"   # transport & map
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "\u2600-\u27BF"           # misc symbols
    "]",
    flags=re.UNICODE
)

SPAM_RE = re.compile(
    r"(?:FREE|BEST\s*DEAL|TOP\s*RATED|100%|GUARANTEED|CLICK|SALE!?|CHEAP|HOT\s*DEAL|DON'?T\s*MISS)",
    flags=re.IGNORECASE
)

DISALLOWED_TAGS = {
    "script","iframe","object","embed","applet","form","input","button","video","audio",
    "canvas","svg","style","link","meta"
}
ALLOWED_TAGS = {
    "b","strong","br","ol","ul","li","table","tr","td","th","thead","tbody","tfoot",
    "caption","colgroup","col"
}
# BeautifulSoup may insert html/body; ignore them in checks:
NEUTRAL_TAGS = {"html","body"}

def normalize_whitespace(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

def is_all_caps(s: str) -> bool:
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return False
    upper = sum(1 for c in letters if c.isupper())
    return (upper / len(letters)) >= 0.9

def validate_title(title: Optional[str], brand: Optional[str]=None) -> Dict[str, Any]:
    checks: Dict[str, Any] = {
        "present": bool(title),
        "length_le_80": False,
        "length_ge_10": False,
        "one_line": False,
        "no_double_spaces": False,
        "no_emoji": False,
        "no_spam_words": False,
        "not_all_caps": False,
        "starts_with_brand": "not_evaluated"
    }
    violations: List[str] = []

    if not title:
        return {"pass": False, "checks": checks, "violations": ["missing_title"]}

    t = title
    checks["length_le_80"] = len(t) <= 80
    checks["length_ge_10"] = len(t.strip()) >= 10
    checks["one_line"] = ("\n" not in t and "\r" not in t)
    checks["no_double_spaces"] = ("  " not in t)
    checks["no_emoji"] = not EMOJI_RE.search(t)
    checks["no_spam_words"] = not SPAM_RE.search(t)
    checks["not_all_caps"] = not is_all_caps(t)

    if brand:
        # title should start with brand or contain brand early (first 12 chars)
        tb = t.lower().lstrip()
        br = brand.lower().strip()
        starts = tb.startswith(br)
        early = tb.find(br) != -1 and tb.find(br) <= 12
        checks["starts_with_brand"] = bool(starts or early)

    # collect violations
    for key, ok in checks.items():
        if ok is False:
            violations.append(key)

    title_ok = all(v is True or v == "not_evaluated" for v in checks.values())
    return {"pass": title_ok, "checks": checks, "violations": violations}

def get_all_tags(soup: BeautifulSoup) -> List[str]:
    return [tag.name for tag in soup.find_all()]

def count_bullets(soup: BeautifulSoup) -> int:
    # count first UL bullets; if multiple ULs, sum all <li>
    return len(soup.find_all("li"))

def first_paragraph_len(soup: BeautifulSoup) -> int:
    p = soup.find("p")
    if not p:
        return 0
    text = normalize_whitespace(p.get_text(" "))
    return len(text)

def has_disallowed_tags(soup: BeautifulSoup) -> List[str]:
    present = set()
    for tag in soup.find_all():
        name = tag.name.lower()
        if name in DISALLOWED_TAGS:
            present.add(name)
    return sorted(present)

def only_allowed_tags(soup: BeautifulSoup) -> List[str]:
    bad = set()
    for tag in soup.find_all():
        name = tag.name.lower()
        if name in NEUTRAL_TAGS:
            continue
        if name not in ALLOWED_TAGS:
            bad.add(name)
    return sorted(bad)

def contains_external_links(text: str) -> bool:
    # crude detection: http(s):// or email
    if re.search(r"https?://", text, flags=re.IGNORECASE):
        return True
    if re.search(r"\b[\w\.-]+@[\w\.-]+\.\w{2,}\b", text):
        return True
    return False

def validate_description(html: Optional[str]) -> Dict[str, Any]:
    checks: Dict[str, Any] = {
        "present": bool(html),
        "length_40_to_4000": False,
        "lead_paragraph_ok": False,
        "bullet_count_3_to_8": False,
        "no_disallowed_tags": False,
        "only_allowed_tags": False,
        "no_external_links": False
    }
    violations: List[str] = []

    if not html:
        return {"pass": False, "checks": checks, "violations": ["missing_description"]}

    h = html.strip()
    checks["length_40_to_4000"] = 40 <= len(h) <= 4000

    soup = BeautifulSoup(h, "html.parser")
    p_len = first_paragraph_len(soup)
    checks["lead_paragraph_ok"] = p_len >= 40  # bạn có thể chỉnh 30–300 tùy ý

    li_count = count_bullets(soup)
    checks["bullet_count_3_to_8"] = 3 <= li_count <= 8

    disallowed = has_disallowed_tags(soup)
    checks["no_disallowed_tags"] = len(disallowed) == 0

    bad_tags = only_allowed_tags(soup)
    checks["only_allowed_tags"] = len(bad_tags) == 0

    checks["no_external_links"] = not contains_external_links(h)

    for key, ok in checks.items():
        if ok is False:
            violations.append(key)
    desc_ok = all(v is True for v in checks.values())
    details = {
        "pass": desc_ok,
        "checks": checks,
        "violations": violations,
        "found_disallowed_tags": disallowed,
        "found_non_whitelisted_tags": bad_tags,
        "lead_paragraph_length": p_len,
        "bullet_count": li_count
    }
    return details

def load_brand_map(products_path: Optional[Path]) -> Dict[str, str]:
    """Map input_id -> brand if you provide Shopify products file."""
    mapping: Dict[str, str] = {}
    if not products_path:
        return mapping
    data = json.loads(Path(products_path).read_text(encoding="utf-8"))
    items: List[Dict[str, Any]]
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        items = data["items"]
    elif isinstance(data, list):
        items = data
    else:
        return mapping
    for it in items:
        _id = it.get("id") or it.get("sku") or it.get("handle")
        brand = it.get("brand") or it.get("vendor")
        if _id and brand:
            mapping[str(_id)] = str(brand)
    return mapping

def main():
    ap = argparse.ArgumentParser(description="Validate eBay title/description results JSON.")
    ap.add_argument("input", help="Path to results JSON (list of items like your sample).")
    ap.add_argument("-o", "--output", help="Path to save validation JSON.", default=None)
    ap.add_argument("--products", help="(Optional) Shopify products JSON to map input_id -> brand.", default=None)
    args = ap.parse_args()

    input_path = Path(args.input)
    
    if args.output:
        out_path = Path(args.output)
    else:
        out_dir = Path("test")
        out_dir.mkdir(parents=True, exist_ok=True)  
        out_path = out_dir / f"{input_path.stem}_validated_{time.time() * 1000}{input_path.suffix}"

        brand_map = load_brand_map(Path(args.products)) if args.products else {}

        raw = json.loads(input_path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise SystemExit("Input must be a JSON list (like your sample).")

    validated = []
    for row in raw:
        input_id = str(row.get("input_id") or "")
        brand = brand_map.get(input_id)
        title = row.get("ebay_title") or ""
        desc  = row.get("ebay_description_html") or ""

        title_report = validate_title(title, brand=brand)
        desc_report  = validate_description(desc)

        overall = bool(title_report["pass"] and desc_report["pass"])
        validated.append({
            "input_id": input_id,
            "model": row.get("model"),
            "ok_original": row.get("ok"),
            "overall_pass": overall,
            "title": {
                "value": title,
                **title_report
            },
            "description": {
                "length": len(desc),
                "value_preview": (desc[:160] + "…") if len(desc) > 160 else desc,
                **desc_report
            },
            "tokens": {
                "input_tokens": row.get("input_tokens"),
                "output_tokens": row.get("output_tokens"),
                "total_tokens": row.get("total_tokens")
            }
        })

    out_path.write_text(json.dumps(validated, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Wrote {out_path} ({len(validated)} rows)")

if __name__ == "__main__":
    main()

# python test_validate.py output/result_gpt-4.1-mini_1757470771701.1294.json
# python test_validate.py output/result_gpt-4.1-nano_1757471188303.1316.
# python test_validate.py output/result_gpt-4.1-mini_1757493896251.0146.json
# python test_validate.py output/result_gpt-4.1-mini_1757494328929.34.json