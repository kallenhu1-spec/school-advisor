#!/usr/bin/env python3
import json
import re
from collections import OrderedDict
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
SEED_PATH = ROOT / "data" / "seed_v2_city_hangzhou.json"
CURATION_DIR = ROOT / "data" / "curation" / "hangzhou"
MASTER_LIST_PATH = CURATION_DIR / "school_master_list_hangzhou.jsonl"
DISTRICT_ORDER = ["xihu", "shangcheng", "gongshu", "binjiang", "yuhang"]

DISTRICT_SOURCES = [
    {"district": "xihu", "url": "https://www.hzxh.gov.cn/art/2023/6/9/art_1229507039_59029380.html", "source_note": "西湖区学校名录", "parser": "xihu"},
    {"district": "shangcheng", "url": "https://www.hzsc.gov.cn/art/2024/10/8/art_1229772969_59079925.html", "source_note": "上城区小学信息", "parser": "shangcheng"},
    {"district": "gongshu", "url": "https://www.gongshu.gov.cn/art/2024/8/12/art_1229493430_59081773.html", "source_note": "拱墅区教育概况", "parser": "gongshu"},
    {"district": "binjiang", "url": "https://www.hhtz.gov.cn/art/2025/5/30/art_1229879565_59076101.html", "source_note": "滨江区小学信息", "parser": "binjiang"},
    {"district": "yuhang", "url": "https://www.yuhang.gov.cn/art/2024/8/16/art_1229511761_4291290.html", "source_note": "余杭区义务教育学校名录", "parser": "yuhang"},
]

NAME_ALIAS = {
    "崇文实验学校": "崇文实验学校小学部",
    "崇文实验学校小学部": "崇文实验学校小学部",
    "杭州观成实验学校": "杭州观成实验学校小学部",
    "杭州观成实验学校小学部": "杭州观成实验学校小学部",
    "杭州二中白马湖学校": "杭州二中白马湖学校小学部",
    "杭州二中白马湖学校小学部": "杭州二中白马湖学校小学部",
    "绿城育华小学": "杭州绿城育华学校小学部",
    "杭州绿城育华学校小学部": "杭州绿城育华学校小学部",
    "绿城育华亲亲学校": "杭州余杭绿城育华亲亲学校",
    "杭州余杭绿城育华亲亲学校": "杭州余杭绿城育华亲亲学校",
    "绿城育华翡翠城学校": "杭州余杭绿城育华翡翠城学校",
    "杭州余杭绿城育华翡翠城学校": "杭州余杭绿城育华翡翠城学校",
    "新明半岛英才学校": "杭州新明半岛英才学校",
    "杭州新明半岛英才学校": "杭州新明半岛英才学校",
    "维翰学校": "杭州维翰学校",
    "杭州维翰学校": "杭州维翰学校",
    "杭州市余杭区未来科技城海创小学": "未来科技城海创小学",
}

TIER_PRIORITY = {"T1": 3, "T2": 2, "T3": 1}

PHONE_OVERRIDES = {
    "杭州二中白马湖学校小学部": {
        "phone": "86798900",
        "note": "电话来自滨江区学校官方页（杭州二中白马湖学校（公办））",
    },
    "杭州余杭区育海外国语学校": {
        "phone": "88686118",
        "note": "电话参考杭州市教育局历史学校名录页",
    },
}

OFFICIAL_URL_OVERRIDES = {
    "杭州余杭区育海外国语学校": {
        "officialUrl": "https://www.yuhang.gov.cn/art/2024/8/16/art_1229511761_4291290.html",
    }
}

ADMISSION_OVERRIDES = {
    "杭州绿城育华学校小学部": {
        "admission": {
            "admissionYear": 2025,
            "admissionUrl": "https://www.hzxh.gov.cn/art/2025/6/25/art_1229507042_59049293.html",
            "admissionSource": "official",
            "lotteryNeeded": True,
            "lotteryData": "2025年西湖区官方公告：报名人数超过招生计划数，将于6月30日进行电脑派位。",
        }
    },
    "钱塘外语学校(学院路校区)": {
        "admission": {
            "admissionYear": 2025,
            "admissionUrl": "https://www.hzxh.gov.cn/art/2025/6/25/art_1229507042_59049293.html",
            "admissionSource": "official",
            "lotteryNeeded": True,
            "lotteryData": "2025年西湖区官方公告按“杭州市钱塘外语学校（民转公学校）”统一发布，报名人数超过招生计划数，将于6月30日进行电脑派位。",
        }
    },
    "钱塘外语学校(文二路校区)": {
        "admission": {
            "admissionYear": 2025,
            "admissionUrl": "https://www.hzxh.gov.cn/art/2025/6/25/art_1229507042_59049293.html",
            "admissionSource": "official",
            "lotteryNeeded": True,
            "lotteryData": "2025年西湖区官方公告按“杭州市钱塘外语学校（民转公学校）”统一发布，报名人数超过招生计划数，将于6月30日进行电脑派位。",
        }
    },
    "云谷学校小学部": {
        "admission": {
            "admissionYear": 2025,
            "admissionUrl": "https://www.hzxh.gov.cn/art/2025/6/25/art_1229507042_59049293.html",
            "admissionSource": "official",
            "lotteryNeeded": False,
            "lotteryData": "2025年西湖区官方公告：报名人数未超过招生计划数，报名学生一次性全部录取。",
        }
    },
    "之江外语学校": {
        "admission": {
            "admissionYear": 2025,
            "admissionUrl": "https://www.hzxh.gov.cn/art/2025/6/25/art_1229507042_59049293.html",
            "admissionSource": "official",
            "lotteryNeeded": False,
            "lotteryData": "2025年西湖区官方公告按“杭州市之江外语实验学校”发布，报名人数未超过招生计划数，报名学生一次性全部录取。",
        }
    },
    "杭州上海世外学校": {
        "admission": {
            "admissionYear": 2025,
            "admissionUrl": "https://www.gongshu.gov.cn/art/2025/6/25/art_1229549346_4365521.html",
            "admissionSource": "official",
            "lotteryNeeded": True,
            "lotteryData": "2025年拱墅区官方公告：报名人数超过招生计划数，将于6月30日进行电脑派位录取。",
        }
    },
    "杭州锦绣·育才中学附属学校": {
        "admission": {
            "admissionYear": 2025,
            "admissionUrl": "https://www.gongshu.gov.cn/art/2025/6/25/art_1229549346_4365521.html",
            "admissionSource": "official",
            "lotteryNeeded": True,
            "lotteryData": "2025年拱墅区官方公告：报名人数超过招生计划数，将于6月30日进行电脑派位录取。",
        }
    },
    "杭州余杭区育海外国语学校": {
        "admission": {
            "admissionYear": 2025,
            "admissionUrl": "https://www.yuhang.gov.cn/art/2025/6/25/art_1229511764_4365508.html",
            "admissionSource": "official",
            "lotteryNeeded": True,
            "lotteryData": "2025年余杭区官方公告：报名人数超过招生计划数，将于6月30日进行电脑派位录取。",
        }
    },
    "育海外国语学校": {
        "admission": {
            "admissionYear": 2025,
            "admissionUrl": "https://www.yuhang.gov.cn/art/2025/6/25/art_1229511764_4365508.html",
            "admissionSource": "official",
            "lotteryNeeded": True,
            "lotteryData": "2025年余杭区官方公告：报名人数超过招生计划数，将于6月30日进行电脑派位录取。",
        }
    },
    "杭州蕙兰未来科技城学校": {
        "admission": {
            "admissionYear": 2025,
            "admissionUrl": "https://www.yuhang.gov.cn/art/2025/6/25/art_1229511764_4365508.html",
            "admissionSource": "official",
            "lotteryNeeded": False,
            "lotteryData": "2025年余杭区官方公告：报名资格审核通过的学生数未超过学校招生计划数，资格审核通过的学生全部录取。",
        }
    },
    "杭州英特外国语学校": {
        "admission": {
            "admissionYear": 2025,
            "admissionUrl": "https://www.yuhang.gov.cn/art/2025/6/25/art_1229511764_4365508.html",
            "admissionSource": "official",
            "lotteryNeeded": False,
            "lotteryData": "2025年余杭区官方公告：报名资格审核通过的学生数未超过学校招生计划数，资格审核通过的学生全部录取。",
        }
    },
    "杭州狄邦文理学校": {
        "admission": {
            "admissionYear": 2025,
            "admissionUrl": "https://www.yuhang.gov.cn/art/2025/6/25/art_1229511764_4365508.html",
            "admissionSource": "official",
            "lotteryNeeded": False,
            "lotteryData": "2025年余杭区官方公告：报名资格审核通过的学生数未超过学校招生计划数，资格审核通过的学生全部录取。",
        }
    },
    "狄邦文理学校": {
        "admission": {
            "admissionYear": 2025,
            "admissionUrl": "https://www.yuhang.gov.cn/art/2025/6/25/art_1229511764_4365508.html",
            "admissionSource": "official",
            "lotteryNeeded": False,
            "lotteryData": "2025年余杭区官方公告：报名资格审核通过的学生数未超过学校招生计划数，资格审核通过的学生全部录取。",
        }
    },
    "杭州市余杭区金成外国语小学": {
        "admission": {
            "admissionYear": 2025,
            "admissionUrl": "https://www.yuhang.gov.cn/art/2025/6/25/art_1229511764_4365508.html",
            "admissionSource": "official",
            "lotteryNeeded": False,
            "lotteryData": "2025年余杭区官方公告：报名资格审核通过的学生数未超过学校招生计划数，资格审核通过的学生全部录取。",
        }
    },
    "绿城育华翡翠城学校": {
        "admission": {
            "admissionYear": 2025,
            "admissionUrl": "https://www.yuhang.gov.cn/art/2025/6/25/art_1229511764_4365508.html",
            "admissionSource": "official",
            "lotteryNeeded": False,
            "lotteryData": "2025年余杭区官方公告：报名资格审核通过的学生数未超过学校招生计划数，资格审核通过的学生全部录取。",
        }
    },
    "绿城育华亲亲学校": {
        "admission": {
            "admissionYear": 2025,
            "admissionUrl": "https://www.yuhang.gov.cn/art/2025/6/25/art_1229511764_4365508.html",
            "admissionSource": "official",
            "lotteryNeeded": False,
            "lotteryData": "2025年余杭区官方公告：报名资格审核通过的学生数未超过学校招生计划数，资格审核通过的学生全部录取。",
        }
    },
    "杭州维翰学校": {
        "admission": {
            "admissionYear": 2025,
            "admissionUrl": "https://www.yuhang.gov.cn/art/2025/6/25/art_1229511764_4365508.html",
            "admissionSource": "official",
            "lotteryNeeded": False,
            "lotteryData": "2025年余杭区官方公告：报名资格审核通过的学生数未超过学校招生计划数，资格审核通过的学生全部录取。",
        }
    },
    "杭州新明半岛英才学校": {
        "admission": {
            "admissionYear": 2025,
            "admissionUrl": "https://www.yuhang.gov.cn/art/2025/6/25/art_1229511764_4365508.html",
            "admissionSource": "official",
            "lotteryNeeded": False,
            "lotteryData": "2025年余杭区官方公告：报名资格审核通过的学生数未超过学校招生计划数，资格审核通过的学生全部录取。",
        }
    },
}

TUITION_OVERRIDES = {
    "杭州狄邦文理学校": {
        "tuition": {
            "term": 78000,
            "note": "2025-2026学年小学学费；住宿费6300元/学期（5天寄宿）、9450元/学期（7天寄宿）。来源：学校2025-2026学年幼升小招生简章。",
            "sourceLevel": "official",
            "sourceUrl": "https://www.rkcshz.cn/zh/2025/06/03/10833/",
        }
    },
    "狄邦文理学校": {
        "tuition": {
            "term": 78000,
            "note": "2025-2026学年小学学费；住宿费6300元/学期（5天寄宿）、9450元/学期（7天寄宿）。来源：学校2025-2026学年幼升小招生简章。",
            "sourceLevel": "official",
            "sourceUrl": "https://www.rkcshz.cn/zh/2025/06/03/10833/",
        }
    },
}

PROFILE_FALLBACKS = {
    "崇文实验学校小学部": {
        "tag": "上城公办T2",
        "slogan": "一贯制路径省心，综合素养导向",
        "ideas": ["九年一贯", "综合能力培养", "项目学习"],
        "hw": 3,
        "stress": 2,
        "path": ["校内直升/区内公办初中"],
        "pros": ["路径相对省心", "综合活动丰富"],
        "cons": ["一贯制质量体验需看具体年级"],
        "xhs": "崇文实验学校小学部 幼升小",
        "sourceLevel": "ai-draft",
        "sourceNote": "AI总结，待补官方来源",
    },
    "杭州余杭绿城育华亲亲学校": {
        "tag": "余杭民办T2",
        "slogan": "绿城育华系余杭民办校，常被纳入品质型家庭备选",
        "ideas": ["绿城育华系", "民办备选", "社区配套"],
        "hw": 3,
        "stress": 3,
        "path": ["区内初中升学", "民办备选"],
        "pros": ["品牌辨识度较强", "适合重视稳定办学风格的家庭"],
        "cons": ["收费与校区差异待核实"],
        "xhs": "杭州余杭绿城育华亲亲学校 幼升小",
        "sourceLevel": "ai-draft",
        "sourceNote": "基于2025余杭区官方名单补齐，画像为AI总结",
    },
    "杭州余杭绿城育华翡翠城学校": {
        "tag": "余杭民办T2",
        "slogan": "绿城育华系余杭民办校，板块与社区属性明显",
        "ideas": ["绿城育华系", "社区型民办", "板块适配"],
        "hw": 3,
        "stress": 3,
        "path": ["区内初中升学", "民办备选"],
        "pros": ["适合翡翠城周边家庭", "品牌辨识度较强"],
        "cons": ["具体升学与收费待核实"],
        "xhs": "杭州余杭绿城育华翡翠城学校 幼升小",
        "sourceLevel": "ai-draft",
        "sourceNote": "基于2025余杭区官方名单补齐，画像为AI总结",
    },
    "云谷学校小学部": {
        "tag": "西湖民办T2",
        "slogan": "高关注度民办学校，适合看课程创新与成长环境的家庭",
        "ideas": ["课程创新", "校园资源较新", "家庭教育理念匹配度重要"],
        "hw": 3,
        "stress": 3,
        "path": ["民办/双语路径", "区内初中升学"],
        "pros": ["学校辨识度较高", "环境与设施关注度高"],
        "cons": ["招生细则与费用仍需逐年核实"],
        "xhs": "云谷学校小学部 幼升小",
        "sourceLevel": "ai-draft",
        "sourceNote": "学校画像为AI总结，基础信息来自西湖区学校名录",
    },
    "之江外语学校": {
        "tag": "西湖民办T3",
        "slogan": "外语特色取向明显，适合作为双语方向补充备选",
        "ideas": ["外语特色", "民办补充选项", "通勤适配重要"],
        "hw": 3,
        "stress": 3,
        "path": ["民办路径", "区内初中升学"],
        "pros": ["方向明确", "适合扩大民办备选池"],
        "cons": ["公开口碑与招生细节仍需继续补充"],
        "xhs": "之江外语学校 幼升小",
        "sourceLevel": "ai-draft",
        "sourceNote": "学校画像为AI总结，基础信息来自西湖区学校名录",
    },
    "杭州新世纪外国语学校": {
        "tag": "上城公办T2",
        "slogan": "外语特色与国际理解方向清晰，家长关注度长期稳定",
        "ideas": ["外语特色", "国际理解课程", "学校品牌辨识度较高"],
        "hw": 3,
        "stress": 3,
        "path": ["区内公办初中", "外语特色发展路径"],
        "pros": ["外语方向明确", "学校历史口碑基础较好"],
        "cons": ["转公后口径需结合最新招生细则理解"],
        "xhs": "杭州新世纪外国语学校 幼升小",
        "sourceLevel": "ai-draft",
        "sourceNote": "学校画像为AI总结，基础信息来自上城区小学信息页",
    },
    "娃哈哈小学": {
        "tag": "上城公办T2",
        "slogan": "老牌学校转公后关注度仍高，适合看教学风格与片区适配",
        "ideas": ["学校辨识度高", "中心城区学校", "家庭节奏匹配重要"],
        "hw": 3,
        "stress": 3,
        "path": ["区内公办初中", "中心城区升学路径"],
        "pros": ["品牌辨识度高", "城市核心区位优势明显"],
        "cons": ["学校口径变化后需持续关注最新招生政策"],
        "xhs": "娃哈哈小学 幼升小",
        "sourceLevel": "ai-draft",
        "sourceNote": "学校画像为AI总结，基础信息来自上城区小学信息页",
    },
}


def fetch_html(url):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urlopen(req, timeout=30).read().decode("utf-8", "ignore")


def clean_html_text(value):
    value = re.sub(r"<br\s*/?>", " / ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    value = unescape(value).replace("\xa0", " ")
    return re.sub(r"\s+", " ", value).strip()


def extract_rows(html):
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.I | re.S):
        cells = []
        for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.I | re.S):
            text = clean_html_text(cell)
            if text:
                cells.append(text)
        if len(cells) >= 2:
            rows.append(cells)
    return rows


def looks_like_primary(stage):
    return any(token in str(stage or "") for token in ["小学", "九年一贯", "十二年一贯"])


def normalize_type(value):
    text = str(value or "").strip()
    if "民办" in text:
        return "pri"
    if "公办" in text:
        return "pub"
    return ""


def strip_prefixes(name):
    name = str(name or "").strip()
    for prefix in ["杭州市余杭区", "杭州市"]:
        if name.startswith(prefix):
            return name[len(prefix) :].strip()
    return name


def campus_base_name(name):
    name = str(name or "").strip()
    if not name.endswith("校区"):
        return name
    for token in ["小学部", "小学", "学校"]:
        idx = name.find(token)
        if idx != -1:
            return name[: idx + len(token)]
    return name


def canonical_name(name):
    name = strip_prefixes(name)
    name = campus_base_name(name)
    name = name.replace("（", "(").replace("）", ")")
    name = name.replace("(小学部)", "小学部")
    name = name.replace(" ", "")
    return NAME_ALIAS.get(name, name)


def build_display_name(official_name):
    alias = NAME_ALIAS.get(canonical_name(official_name))
    if alias:
        return alias
    short_name = strip_prefixes(official_name)
    short_name = campus_base_name(short_name)
    return short_name or official_name


def merge_join(values):
    ordered = OrderedDict()
    for value in values:
        for chunk in str(value or "").split(" / "):
            text = chunk.strip()
            if text:
                ordered[text] = True
    return " / ".join(ordered.keys())


def parse_xihu(rows, source):
    schools = []
    for row in rows:
        if len(row) < 5 or row[0] == "学校（校区）" or not looks_like_primary(row[1]):
            continue
        schools.append({"district": source["district"], "officialName": campus_base_name(row[0]), "address": row[3], "phone": row[4], "type": normalize_type(row[2]), "schoolStage": row[1], "sourceUrl": source["url"], "basicInfoSourceLevel": "official", "basicInfoSourceNote": source["source_note"]})
    return schools


def parse_shangcheng(rows, source):
    schools = []
    for row in rows:
        if len(row) < 7 or row[0] == "序号" or not row[0].isdigit() or not looks_like_primary(row[2]):
            continue
        schools.append({"district": source["district"], "officialName": row[1], "address": row[4], "phone": row[6], "type": normalize_type(row[3]), "schoolStage": row[2], "sourceUrl": source["url"], "basicInfoSourceLevel": "official", "basicInfoSourceNote": source["source_note"]})
    return schools


def parse_gongshu(rows, source):
    schools = []
    for row in rows:
        if len(row) < 6 or row[0] == "序号" or not row[0].isdigit() or not looks_like_primary(row[4]):
            continue
        schools.append({"district": source["district"], "officialName": row[1], "address": row[2], "phone": row[3], "type": normalize_type(row[5]), "schoolStage": row[4], "sourceUrl": source["url"], "basicInfoSourceLevel": "official", "basicInfoSourceNote": source["source_note"]})
    return schools


def parse_binjiang(rows, source):
    schools = []
    for row in rows:
        if len(row) < 7 or row[0] == "学校名称":
            continue
        schools.append({"district": source["district"], "officialName": row[0], "address": row[2], "phone": row[3], "type": normalize_type(row[1]), "schoolStage": "小学", "sourceUrl": source["url"], "basicInfoSourceLevel": "official", "basicInfoSourceNote": source["source_note"]})
    return schools


def parse_yuhang(rows, source):
    schools = []
    for row in rows:
        if len(row) < 6 or row[0] == "序号" or not row[0].isdigit() or not looks_like_primary(row[3]):
            continue
        schools.append({"district": source["district"], "officialName": row[1], "address": row[2], "phone": row[5], "type": normalize_type(row[4]), "schoolStage": row[3], "sourceUrl": source["url"], "basicInfoSourceLevel": "official", "basicInfoSourceNote": source["source_note"]})
    return schools


PARSERS = {"xihu": parse_xihu, "shangcheng": parse_shangcheng, "gongshu": parse_gongshu, "binjiang": parse_binjiang, "yuhang": parse_yuhang}


def aggregate_official_rows():
    aggregated = OrderedDict()
    seen_rows = set()
    for source in DISTRICT_SOURCES:
        rows = extract_rows(fetch_html(source["url"]))
        for school in PARSERS[source["parser"]](rows, source):
            row_key = (
                school["district"],
                canonical_name(school["officialName"]),
                school.get("address"),
                school.get("phone"),
                school.get("type"),
                school.get("schoolStage"),
            )
            if row_key in seen_rows:
                continue
            seen_rows.add(row_key)
            key = canonical_name(school["officialName"])
            current = aggregated.get(key)
            if current is None:
                aggregated[key] = dict(school)
                continue
            current["address"] = merge_join([current.get("address"), school.get("address")])
            current["phone"] = merge_join([current.get("phone"), school.get("phone")])
            current["basicInfoSourceNote"] = merge_join([current.get("basicInfoSourceNote"), school.get("basicInfoSourceNote")])
            if school.get("type"):
                current["type"] = school["type"]
            if school.get("schoolStage"):
                current["schoolStage"] = merge_join([current.get("schoolStage"), school.get("schoolStage")])
    return aggregated


def load_existing_seed():
    return json.loads(SEED_PATH.read_text(encoding="utf-8"))


def tier_rank(tier):
    return TIER_PRIORITY.get(str(tier or "").upper(), 0)


def deep_merge(base, override):
    out = json.loads(json.dumps(base, ensure_ascii=False))
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def apply_curated_overrides(school):
    canonical_key = canonical_name(school.get("name") or school.get("officialName"))
    phone_override = PHONE_OVERRIDES.get(school.get("name")) or PHONE_OVERRIDES.get(canonical_key)
    if phone_override and not school.get("phone"):
        school["phone"] = phone_override["phone"]
        school["basicInfoSourceNote"] = merge_join([school.get("basicInfoSourceNote"), phone_override["note"]])
    official_url_override = OFFICIAL_URL_OVERRIDES.get(school.get("name")) or OFFICIAL_URL_OVERRIDES.get(canonical_key)
    if official_url_override and not school.get("officialUrl"):
        school["officialUrl"] = official_url_override["officialUrl"]
    admission_override = ADMISSION_OVERRIDES.get(school.get("name")) or ADMISSION_OVERRIDES.get(canonical_key)
    if admission_override:
        school = deep_merge(school, admission_override)
    tuition_override = TUITION_OVERRIDES.get(school.get("name")) or TUITION_OVERRIDES.get(canonical_key)
    if tuition_override:
        school = deep_merge(school, tuition_override)
    school.setdefault("links", {"map": None, "xhs": f"{school['name']} 幼升小", "dianping": None})
    if not school["links"].get("xhs"):
        school["links"]["xhs"] = f"{school['name']} 幼升小"
    fallback_profile = PROFILE_FALLBACKS.get(canonical_name(school["name"])) or PROFILE_FALLBACKS.get(canonical_name(school["officialName"]))
    if fallback_profile and not school.get("profile"):
        school["profile"] = fallback_profile
        if not school["links"].get("xhs") and fallback_profile.get("xhs"):
            school["links"]["xhs"] = fallback_profile["xhs"]
    return school


def merge_seed(existing_seed, official_rows):
    existing_map = {}
    for school in existing_seed.get("schools", []):
        key = canonical_name(school.get("name") or school.get("officialName"))
        if key:
            existing_map[key] = school

    merged = []
    for key, official in official_rows.items():
        current = existing_map.pop(key, None)
        if current:
            school = json.loads(json.dumps(current, ensure_ascii=False))
        else:
            display_name = build_display_name(official["officialName"])
            school = {
                "name": display_name,
                "officialName": official["officialName"],
                "district": official["district"],
                "type": official["type"] or "pub",
                "tier": "T3",
                "lat": None,
                "lng": None,
                "desc": "基础信息已按官方目录校准，学校画像待补充",
                "links": {"map": None, "xhs": f"{display_name} 幼升小", "dianping": None},
            }
        school["officialName"] = official["officialName"]
        school["name"] = school.get("name") or build_display_name(official["officialName"])
        school["district"] = official["district"]
        school["type"] = official["type"] or school.get("type") or "pub"
        school["address"] = official["address"]
        school["phone"] = official["phone"]
        school["sourceUrl"] = official["sourceUrl"]
        school["basicInfoSourceLevel"] = official["basicInfoSourceLevel"]
        school["basicInfoSourceNote"] = official["basicInfoSourceNote"]
        school["officialUrl"] = school.get("officialUrl") or official["sourceUrl"]
        merged.append(apply_curated_overrides(school))

    merged.extend(existing_map.values())
    merged = [apply_curated_overrides(school) for school in merged]
    merged.sort(key=lambda s: (DISTRICT_ORDER.index(s.get("district")) if s.get("district") in DISTRICT_ORDER else 99, -tier_rank(s.get("tier")), canonical_name(s.get("officialName") or s.get("name"))))
    existing_seed["generatedAt"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    existing_seed["dataNote"] = "杭州学校基础信息已按区政府学校名录、区教育局学校页和学校官网批量校准；已优先补充民办学校的2025招生口径与可核实学费；学校画像统一标注为AI总结，不将未核实信息伪装成官方事实。"
    existing_seed["schools"] = merged
    return existing_seed


def write_master_list(official_rows):
    CURATION_DIR.mkdir(parents=True, exist_ok=True)
    with MASTER_LIST_PATH.open("w", encoding="utf-8") as f:
        for school in official_rows.values():
            row = dict(school)
            row["name"] = build_display_name(row["officialName"])
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main():
    official_rows = aggregate_official_rows()
    seed = merge_seed(load_existing_seed(), official_rows)
    write_master_list(official_rows)
    SEED_PATH.write_text(json.dumps(seed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"schoolCount": len(seed["schools"]), "masterListPath": str(MASTER_LIST_PATH.relative_to(ROOT)), "seedPath": str(SEED_PATH.relative_to(ROOT))}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
