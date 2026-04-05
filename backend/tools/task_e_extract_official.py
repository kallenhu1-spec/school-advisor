#!/usr/bin/env python3
import argparse
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional, Tuple

from pypdf import PdfReader


UA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def fetch_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers=UA_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def absolutize(base_url: str, href: str) -> str:
    return urllib.parse.urljoin(base_url, href.strip())


def parse_pdf_urls_from_html(page_url: str, html: str) -> list[str]:
    urls = set()
    for m in re.finditer(r'href=["\']([^"\']+\.pdf[^"\']*)["\']', html, flags=re.I):
        urls.add(absolutize(page_url, m.group(1)))
    # fallback: plain URL appearing in scripts
    for m in re.finditer(r'(https?://[^\s"\']+\.pdf)', html, flags=re.I):
        urls.add(m.group(1))
    return sorted(urls)


def extract_text_from_pdf_bytes(data: bytes) -> str:
    from io import BytesIO

    reader = PdfReader(BytesIO(data))
    texts = []
    for p in reader.pages:
        try:
            texts.append(p.extract_text() or "")
        except Exception:
            texts.append("")
    return "\n".join(texts)


def infer_school_name(text: str, pdf_url: str) -> str:
    patterns = [
        r"民办小学分类计划名称[：:]\s*([^\n\r]+)",
        r"分类计划名称[：:]\s*([^\n\r]+)",
        r"学校名称[：:]\s*([^\n\r]+)",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            return re.sub(r"\s+", "", m.group(1)).strip()
    name_from_url = Path(urllib.parse.urlparse(pdf_url).path).name
    name_from_url = re.sub(r"\.pdf.*$", "", name_from_url, flags=re.I)
    return name_from_url[:80]


def infer_admission_count(text: str) -> Tuple[Optional[int], str]:
    # Most official random-list PDFs enumerate admitted students as 第N号
    nums = [int(x) for x in re.findall(r"第\s*([0-9]{1,4})\s*号", text)]
    if nums:
        return max(nums), "max_第N号"

    # Some PDFs use serial numbers in table rows: 1 张三 ...
    row_nums = [int(x) for x in re.findall(r"(?:^|\n)\s*([0-9]{1,4})\s+[^\n]{1,20}", text)]
    if row_nums:
        # filter obvious page numbers
        row_nums = [x for x in row_nums if x < 5000]
    if row_nums:
        return max(row_nums), "max_row_serial"

    if "全部录取" in text:
        return None, "all_admitted_no_serial"
    return None, "not_found"


def main():
    ap = argparse.ArgumentParser(description="Task E: extract official district PDF school/admission records")
    ap.add_argument("--index", default="data/curation/official_pdf_index_2025.json")
    ap.add_argument("--output", default="data/curation/official_admission_extract_2025.jsonl")
    ap.add_argument("--download-dir", default="data/curation/pdfs_2025")
    args = ap.parse_args()

    index_path = Path(args.index)
    out_path = Path(args.output)
    dl_dir = Path(args.download_dir)
    dl_dir.mkdir(parents=True, exist_ok=True)

    idx = json.loads(index_path.read_text(encoding="utf-8"))
    items = idx.get("items") or []
    rows = []
    seen = set()

    for it in items:
        district = str(it.get("district") or "").strip()
        page_url = str(it.get("pageUrl") or "").strip()
        pdf_urls = set()
        direct_pdf = str(it.get("pdfUrl") or "").strip()
        if direct_pdf:
            pdf_urls.add(direct_pdf)
        page_error = None
        if page_url:
            try:
                html = fetch_text(page_url)
                for u in parse_pdf_urls_from_html(page_url, html):
                    pdf_urls.add(u)
            except Exception as e:
                page_error = str(e)
        if not pdf_urls:
            rows.append(
                {
                    "district": district,
                    "schoolName": "",
                    "admission2025": None,
                    "pdfUrl": "",
                    "pageHint": page_url,
                    "reviewerNote": f"no_pdf_discovered:{page_error or 'no_pdf_link_found'}",
                    "extractionStatus": "blocked_or_pending",
                }
            )
            continue
        for pdf_url in sorted(pdf_urls):
            try:
                data = fetch_bytes(pdf_url)
                fname = re.sub(r"[^a-zA-Z0-9._-]+", "_", Path(urllib.parse.urlparse(pdf_url).path).name or "doc.pdf")
                local = dl_dir / fname
                local.write_bytes(data)
                text = extract_text_from_pdf_bytes(data)
                school_name = infer_school_name(text, pdf_url)
                admission, how = infer_admission_count(text)
                key = (district, school_name, pdf_url)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(
                    {
                        "district": district,
                        "schoolName": school_name,
                        "admission2025": admission,
                        "pdfUrl": pdf_url,
                        "pageHint": page_url,
                        "reviewerNote": f"auto_extract:{how}",
                        "extractionStatus": "extracted" if admission is not None else "needs_manual_review",
                    }
                )
            except Exception as e:
                rows.append(
                    {
                        "district": district,
                        "schoolName": "",
                        "admission2025": None,
                        "pdfUrl": pdf_url,
                        "pageHint": page_url,
                        "reviewerNote": f"download_or_parse_failed:{e}",
                        "extractionStatus": "failed",
                    }
                )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(
        json.dumps(
            {
                "ok": True,
                "index": str(index_path),
                "output": str(out_path),
                "rows": len(rows),
                "extracted": len([x for x in rows if x.get("extractionStatus") == "extracted"]),
                "needs_manual_review": len([x for x in rows if x.get("extractionStatus") == "needs_manual_review"]),
                "failed": len([x for x in rows if x.get("extractionStatus") == "failed"]),
                "blocked_or_pending": len([x for x in rows if x.get("extractionStatus") == "blocked_or_pending"]),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
