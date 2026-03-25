#!/usr/bin/env python3
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE_HTML = ROOT / "index.html"
OUT_JSON = ROOT / "data" / "seed.json"


def extract_js_literal(text: str, var_name: str) -> str:
    needle = f"var {var_name}="
    start = text.find(needle)
    if start < 0:
        raise ValueError(f"未找到变量: {var_name}")
    i = start + len(needle)
    while i < len(text) and text[i].isspace():
        i += 1
    if i >= len(text):
        raise ValueError(f"变量内容为空: {var_name}")

    opener = text[i]
    if opener not in "[{":
        raise ValueError(f"{var_name} 不是对象/数组字面量")
    closer = "]" if opener == "[" else "}"
    depth = 0
    in_str = False
    esc = False
    quote = ""

    j = i
    while j < len(text):
        ch = text[j]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                in_str = False
        else:
            if ch in ("'", '"'):
                in_str = True
                quote = ch
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    return text[i : j + 1]
        j += 1
    raise ValueError(f"变量字面量未闭合: {var_name}")


def main() -> None:
    raw = SOURCE_HTML.read_text(encoding="utf-8")
    sd = json.loads(extract_js_literal(raw, "SD"))
    tf = json.loads(extract_js_literal(raw, "TF"))
    pr = json.loads(extract_js_literal(raw, "PR"))
    dn = json.loads(extract_js_literal(raw, "DN"))

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps({"SD": sd, "TF": tf, "PR": pr, "DN": dn}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"ok: {OUT_JSON}")


if __name__ == "__main__":
    main()
