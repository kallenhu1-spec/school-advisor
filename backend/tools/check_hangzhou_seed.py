#!/usr/bin/env python3
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEED_PATH = ROOT / "data" / "seed_v2_city_hangzhou.json"


def canonical_name(name):
    name = str(name or "").strip()
    for prefix in ["杭州市余杭区", "杭州市"]:
        if name.startswith(prefix):
            name = name[len(prefix) :].strip()
    return re.sub(r"\s+", "", name.replace("（", "(").replace("）", ")"))


def main():
    seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    schools = seed.get("schools", [])
    district_counts = Counter()
    duplicate_keys = Counter()
    missing_basics = []
    missing_profiles = []
    private_schools = []
    private_missing_admission = []
    private_missing_tuition = []
    for school in schools:
        district_counts[school.get("district") or "unknown"] += 1
        duplicate_keys[canonical_name(school.get("officialName") or school.get("name"))] += 1
        missing = [field for field in ["officialName", "district", "type", "address", "sourceUrl", "basicInfoSourceLevel"] if not school.get(field)]
        if missing:
            missing_basics.append({"name": school.get("name"), "missing": missing})
        if not school.get("profile"):
            missing_profiles.append(school.get("name"))
        if school.get("type") == "pri":
            private_schools.append(school)
            admission = school.get("admission") if isinstance(school.get("admission"), dict) else {}
            if not admission.get("admissionUrl") or admission.get("lotteryNeeded") is None:
                private_missing_admission.append(school.get("name"))
            if not isinstance(school.get("tuition"), dict):
                private_missing_tuition.append(school.get("name"))
    print(json.dumps({
        "schoolCount": len(schools),
        "districtCounts": district_counts,
        "duplicateKeys": [key for key, count in duplicate_keys.items() if count > 1],
        "missingBasicsCount": len(missing_basics),
        "missingBasicsSample": missing_basics[:20],
        "profileMissingCount": len(missing_profiles),
        "profileMissingSample": missing_profiles[:20],
        "privateSchoolCount": len(private_schools),
        "privateAdmissionReadyCount": len(private_schools) - len(private_missing_admission),
        "privateAdmissionMissingSample": private_missing_admission[:20],
        "privateTuitionReadyCount": len(private_schools) - len(private_missing_tuition),
        "privateTuitionMissingSample": private_missing_tuition[:20],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
