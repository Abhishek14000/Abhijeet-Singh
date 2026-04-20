#!/usr/bin/env python3
"""
MASTER COMMAND — Kundali PDF → JSON Converter
Usage:
    python3 kundali_pdf_to_json.py <input.pdf> [output.json]

Converts any AstroSage-style kundali PDF into a structured JSON file
that matches the schema defined in kundali_rebuilt.json.
"""

import sys
import re
import json
from datetime import datetime
import pdfplumber

# ── Constants ──────────────────────────────────────────────────────────────────

ZODIAC_SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

SIGN_INDEX = {s.lower(): i + 1 for i, s in enumerate(ZODIAC_SIGNS)}
# Extra aliases found in PDFs
SIGN_ALIASES = {
    "scorpion": "Scorpio",
    "capricornus": "Capricorn",
    "aquarious": "Aquarius",
    "aquarius": "Aquarius",
}

PLANET_NORM = {
    "asc": "ASC", "ascendant": "ASC", "lagna": "ASC",
    "sun": "Sun", "su": "Sun",
    "moon": "Moon", "mo": "Moon", "mon": "Moon",
    "mars": "Mars", "ma": "Mars", "mar": "Mars",
    "mercury": "Mercury", "merc": "Mercury", "mer": "Mercury", "me": "Mercury",
    "jupiter": "Jupiter", "jupt": "Jupiter", "jupi": "Jupiter", "jup": "Jupiter", "ju": "Jupiter",
    "venus": "Venus", "venu": "Venus", "ven": "Venus", "ve": "Venus",
    "saturn": "Saturn", "satn": "Saturn", "satu": "Saturn", "sat": "Saturn", "sa": "Saturn",
    "rahu": "Rahu", "rah": "Rahu", "ra": "Rahu",
    "ketu": "Ketu", "ket": "Ketu", "ke": "Ketu",
}

VIMSH_PLANET_NORM = {
    "RAH": "Rahu", "JUP": "Jupiter", "SAT": "Saturn", "MER": "Mercury",
    "KET": "Ketu", "VEN": "Venus", "SUN": "Sun", "MON": "Moon", "MAR": "Mars",
}

VIMSH_YEARS = {
    "Sun": 6, "Moon": 10, "Mars": 7, "Rahu": 18, "Jupiter": 16,
    "Saturn": 19, "Mercury": 17, "Ketu": 7, "Venus": 20,
}

YOGINI_FULL = {
    "Pi": "Pingala", "Dh": "Dhanya", "Br": "Bhramari", "Ba": "Bhadrika",
    "Ul": "Ulka", "Si": "Siddha", "Sn": "Sankata", "Ma": "Mangala",
}

YOGINI_YEARS = {
    "Mangala": 1, "Pingala": 2, "Dhanya": 3, "Bhramari": 4,
    "Bhadrika": 5, "Ulka": 6, "Siddha": 7, "Sankata": 8,
}

MONTH_MAP = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "jun": "06", "jul": "07", "aug": "08", "sep": "09",
    "oct": "10", "nov": "11", "dec": "12",
}

# Canonical nakshatra names (handles PDF abbreviations & merged spellings)
NAKSHATRA_NORM = {
    "aswini": "Ashwini", "ashwini": "Ashwini", "asvini": "Ashwini",
    "bharani": "Bharani",
    "krittika": "Krittika", "kritika": "Krittika",
    "rohini": "Rohini",
    "mrigasira": "Mrigasira", "mrigashira": "Mrigasira",
    "ardra": "Ardra",
    "punarvasu": "Punarvasu",
    "pushya": "Pushya",
    "ashlesha": "Ashlesha", "aslesha": "Ashlesha",
    "magha": "Magha",
    "purvaphalguni": "Purva Phalguni", "purvaphal": "Purva Phalguni",
    "purvaphalgini": "Purva Phalguni",
    "uttaraphalguni": "Uttara Phalguni", "uttaraphal": "Uttara Phalguni",
    "uttarphalguni": "Uttara Phalguni",
    "hasta": "Hasta",
    "chitra": "Chitra", "chitta": "Chitra",
    "swati": "Swati",
    "vishakha": "Vishakha",
    "anuradha": "Anuradha",
    "jyeshtha": "Jyeshtha", "jyestha": "Jyeshtha",
    "mula": "Mula", "moola": "Mula",
    "purvashadha": "Purva Ashadha", "purvaashadha": "Purva Ashadha",
    "uttarashadha": "Uttara Ashadha", "uttaraashadha": "Uttara Ashadha",
    "sravana": "Sravana", "shravana": "Sravana",
    "dhanishta": "Dhanishta", "dhanishtha": "Dhanishta",
    "satabisha": "Satabisha", "satabhisha": "Satabisha",
    "purvabhadra": "Purva Bhadrapada", "purvabhadrapada": "Purva Bhadrapada",
    "uttarabhadra": "Uttara Bhadrapada", "uttarabhadrapada": "Uttara Bhadrapada",
    "revati": "Revati",
}


def normalize_nakshatra(raw):
    """Normalize nakshatra name to canonical form."""
    if not raw:
        return raw
    key = re.sub(r"\s+", "", raw.lower())  # strip all spaces for lookup
    if key in NAKSHATRA_NORM:
        return NAKSHATRA_NORM[key]
    # Try partial prefix match
    for k, v in NAKSHATRA_NORM.items():
        if key.startswith(k[:6]) and len(key) >= 4:
            return v
    return raw

# ── Utility helpers ────────────────────────────────────────────────────────────

def dms_to_decimal(dms_str):
    """Convert 'DD-MM-SS' or 'DD-MM-SS.S' to decimal degrees."""
    parts = re.split(r"[-:]", dms_str.strip())
    try:
        d, m, s = float(parts[0]), float(parts[1]), float(parts[2]) if len(parts) > 2 else 0.0
        return round(d + m / 60 + s / 3600, 6)
    except (ValueError, IndexError):
        return None


def normalize_sign(raw):
    if raw is None:
        return None
    r = raw.strip().lower()
    if r in SIGN_ALIASES:
        r = SIGN_ALIASES[r].lower()
    for s in ZODIAC_SIGNS:
        if r == s.lower():
            return s
    for s in ZODIAC_SIGNS:
        if r.startswith(s.lower()[:4]):
            return s
    return raw.strip().title()


def compute_house(planet_sign, lagna_sign):
    """Return house number 1–12 from planet sign and lagna sign."""
    ps = normalize_sign(planet_sign)
    ls = normalize_sign(lagna_sign)
    pi = SIGN_INDEX.get(ps.lower()) if ps else None
    li = SIGN_INDEX.get(ls.lower()) if ls else None
    if pi and li:
        return (pi - li) % 12 + 1
    return None


def _expand_2digit_year(y2):
    """
    Expand a 2-digit year string to 4-digit.
    Convention: year '99' maps to 1999 (pre-birth period in most kundali PDFs);
    all other 2-digit years (00-98) map to 2000-2098.
    """
    n = int(y2)
    return f"19{y2}" if n == 99 else f"20{y2}"


def parse_date_text(raw):
    """
    Parse dates like 'June 07, 2000', 'July 22, 2002',
    'January 09,\\n2003', '3/ 9/00', '26/ 1/10'.
    Returns 'DD/MM/YYYY'.
    """
    if not raw:
        return None
    raw = raw.replace("\n", " ").strip()

    # Short format: ' 3/ 9/00' or '26/ 1/10' or '3/9/2000'
    m = re.match(r"^\s*(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{2,4})\s*$", raw)
    if m:
        d, mo, y = m.group(1).zfill(2), m.group(2).zfill(2), m.group(3)
        y = _expand_2digit_year(y) if len(y) == 2 else y
        return f"{d}/{mo}/{y}"

    # 'Month DD, YYYY' or 'Month\nDD, YYYY'
    m = re.match(
        r"([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})",
        raw, re.IGNORECASE,
    )
    if m:
        mon_num = MONTH_MAP.get(m.group(1).lower()[:3])
        if mon_num:
            return f"{m.group(2).zfill(2)}/{mon_num}/{m.group(3)}"

    return None


def clean_text(t):
    """Remove doubled characters from OCR artefacts like 'AAbbhhiisshheekk'."""
    if t and re.search(r"(.)\1{2,}", t):
        # Every character repeated twice: un-double
        try:
            result = ""
            i = 0
            while i < len(t):
                if i + 1 < len(t) and t[i] == t[i + 1]:
                    result += t[i]
                    i += 2
                else:
                    result += t[i]
                    i += 1
            return result.strip()
        except Exception:
            return t
    return t


def flatten_cell(v):
    """Return stripped string from a table cell (may be None or multi-line)."""
    if v is None:
        return ""
    return str(v).replace("\n", " ").strip()

# ── Extraction functions ───────────────────────────────────────────────────────

def extract_basic_details(pages_text, pages_tables):
    """Extract basic_details block."""
    details = {
        "name": None, "lagna": None, "rasi": None, "nakshatra": None,
        "nakshatra_pada": None, "nakshatra_lord": None,
        "date_of_birth": None, "time_of_birth": None, "place": None,
        "timezone": None, "latitude": None, "longitude": None,
    }

    # Scan all table rows for key→value pairs
    kv = {}
    for tables in pages_tables:
        for table in tables:
            for row in table:
                if row and len(row) >= 2:
                    k = flatten_cell(row[0]).lower()
                    v = flatten_cell(row[1])
                    if k and v:
                        kv[k] = v

    def get(*keys):
        for k in keys:
            if k in kv:
                return kv[k]
        return None

    details["name"] = get("name")
    details["date_of_birth"] = get("date of birth", "date")
    details["time_of_birth"] = get("time of birth")
    details["place"] = get("place of birth", "place")
    details["timezone"] = get("time zone")
    details["latitude"] = get("latitude")
    details["longitude"] = get("longitude")

    # Fallback: scan raw text of page 1 & 2
    for text in pages_text[:3]:
        if not text:
            continue
        text = clean_text(text)

        def scan(pattern, group=1):
            m = re.search(pattern, text, re.IGNORECASE)
            return m.group(group).strip() if m else None

        if not details["name"]:
            details["name"] = scan(r"Name\s+([A-Za-z ]+?)(?:\s{2,}|\n)")
        if not details["date_of_birth"]:
            details["date_of_birth"] = scan(
                r"Date\s*(?:of\s*Birth)?\s*[:\-]?\s*([\d]+\s*[:/]\s*[\d]+\s*[:/]\s*[\d]+)"
            )
        if not details["time_of_birth"]:
            details["time_of_birth"] = scan(
                r"Time\s*(?:of\s*Birth)?\s*[:\-]?\s*([\d]+\s*[:/]\s*[\d]+\s*[:/]\s*[\d]+)"
            )
        if not details["place"]:
            details["place"] = scan(r"Place\s*(?:of\s*Birth)?\s*[:\-]?\s*([A-Za-z ]+?)(?:\s{2,}|\n)")
        if not details["lagna"]:
            details["lagna"] = scan(r"Lagna\s+([A-Za-z]+)")
        if not details["rasi"]:
            details["rasi"] = scan(r"Rasi\s+([A-Za-z]+)")
        if not details["nakshatra"]:
            m = re.search(r"Nakshatra[-\s]*Pada\s+(\w+)\s+(\d)", text, re.IGNORECASE)
            if m:
                details["nakshatra"] = m.group(1).strip()
                details["nakshatra_pada"] = int(m.group(2))
        if not details["nakshatra_lord"]:
            details["nakshatra_lord"] = scan(r"Nakshatra\s+Lord\s+([A-Za-z]+)")
        if not details["timezone"]:
            details["timezone"] = scan(r"Time\s*Zone\s+([0-9.]+)")
        if not details["latitude"]:
            details["latitude"] = scan(r"Latitude\s+([\d\s:NnSs]+?)(?:\n|$)")
        if not details["longitude"]:
            details["longitude"] = scan(r"Longitude\s+([\d\s:EeWw]+?)(?:\n|$)")

    # Normalize nakshatra_pada to int
    if details["nakshatra_pada"] is not None:
        try:
            details["nakshatra_pada"] = int(details["nakshatra_pada"])
        except (ValueError, TypeError):
            details["nakshatra_pada"] = None

    # Normalize nakshatra_lord abbreviation to full planet name
    if details["nakshatra_lord"]:
        nl = details["nakshatra_lord"].strip()
        details["nakshatra_lord"] = PLANET_NORM.get(nl.lower(), nl)

    # Normalize date_of_birth / time_of_birth: collapse spaces around separators
    for key in ("date_of_birth", "time_of_birth"):
        if details[key]:
            details[key] = re.sub(r"\s*([:/])\s*", r"\1", details[key]).strip()

    return details


def extract_planets(pages_text, pages_tables, lagna_sign):
    """Extract planetary positions."""
    planets = {}
    header_keywords = {"planets", "sign", "latitude", "nakshatra", "pada"}

    for tables in pages_tables:
        for table in tables:
            if not table or len(table) < 3:
                continue
            # Find the actual header row (may not be row 0)
            header_idx = None
            for ri, row in enumerate(table):
                if not row:
                    continue
                cells = [flatten_cell(c).lower() for c in row]
                if sum(1 for c in cells if c in header_keywords) >= 3:
                    header_idx = ri
                    break
            if header_idx is None:
                continue

            header = [flatten_cell(c).lower() for c in (table[header_idx] or [])]
            try:
                ci_planet = next(i for i, h in enumerate(header) if "planet" in h)
                ci_sign = next(i for i, h in enumerate(header) if "sign" in h)
                ci_lat = next(i for i, h in enumerate(header) if "lat" in h)
                ci_nak = next(i for i, h in enumerate(header) if "nak" in h)
                ci_pada = next(i for i, h in enumerate(header) if "pada" in h)
            except StopIteration:
                continue

            for row in table[header_idx + 1:]:
                if not row:
                    continue
                raw_name = flatten_cell(row[ci_planet] if ci_planet < len(row) else None)
                if not raw_name:
                    continue
                # Normalize planet name (strip retrograde markers)
                base = re.sub(r"\s*\[.*?\]|\s*\(.*?\)", "", raw_name).strip()
                planet = PLANET_NORM.get(base.lower())
                if not planet:
                    continue

                sign_raw = flatten_cell(row[ci_sign] if ci_sign < len(row) else None)
                sign = normalize_sign(sign_raw)
                lat_raw = flatten_cell(row[ci_lat] if ci_lat < len(row) else None)
                degree = dms_to_decimal(lat_raw) if lat_raw else None
                nak_raw = flatten_cell(row[ci_nak] if ci_nak < len(row) else None)
                nakshatra = normalize_nakshatra(nak_raw) if nak_raw else None
                pada_raw = flatten_cell(row[ci_pada] if ci_pada < len(row) else None)
                try:
                    pada = int(pada_raw) if pada_raw else None
                except ValueError:
                    pada = None

                planets[planet] = {
                    "sign": sign,
                    "degree": degree,
                    "nakshatra": nakshatra,
                    "pada": pada,
                    "nakshatra_lord": None,
                    "house": compute_house(sign, lagna_sign),
                }

    return planets


def extract_ashtakavarga(pages_text, pages_tables):
    """Extract Ashtakavarga table (only from pages containing the table header)."""
    akv = {}
    planet_rows = {"sun", "moon", "mars", "merc", "mercury", "jupt", "jupiter",
                   "venu", "venus", "satn", "saturn", "total"}

    for text, tables in zip(pages_text, pages_tables):
        if not text or ("ashtakavarga" not in text.lower() and "ashtakvarga" not in text.lower()):
            continue

        for table in tables:
            if not table or len(table) < 3:
                continue
            # Find a row that looks like the numeric header: 'Sign No', '1', '2', ... '12'
            header_idx = None
            for ri, row in enumerate(table):
                if not row:
                    continue
                cells = [flatten_cell(c) for c in row]
                nums = [c for c in cells if re.match(r"^\d+$", c)]
                if len(nums) >= 12:
                    header_idx = ri
                    break
                if any("sign" in c.lower() for c in cells) and len(row) >= 12:
                    header_idx = ri
                    break
            if header_idx is None:
                continue

            for row in table[header_idx + 1:]:
                if not row:
                    continue
                first = flatten_cell(row[0]).lower()
                if not first:
                    continue
                if not any(first.startswith(p[:3]) for p in planet_rows):
                    continue
                norm = PLANET_NORM.get(first.split()[0]) or first.split()[0].capitalize()
                if "total" in first:
                    norm = "Total"
                # Deduplicate: skip if already captured
                if norm in akv:
                    continue
                values = []
                for cell in row[1:]:
                    v = flatten_cell(cell)
                    try:
                        values.append(int(v))
                    except ValueError:
                        break
                if len(values) == 12:
                    akv[norm] = values

    return akv if akv else None


def extract_vimshottari(pages_text, pages_tables):
    """Extract top-level Vimshottari Dasha periods."""
    dasha = []
    # Pattern in text: "RAH -18 Years\n3/ 9/00 - 26/ 1/10"
    # or table cells: "RAH -18 Years\n3/ 9/00 - 26/ 1/10"
    seen = set()

    for tables in pages_tables:
        for table in tables:
            if not table:
                continue
            for row in table:
                cell0 = flatten_cell(row[0] if row else None)
                if not cell0:
                    continue
                # Match "RAH -18 Years 3/ 9/00 - 26/ 1/10" or similar
                m = re.match(
                    r"([A-Z]{2,3})\s*[-–]\s*(\d+)\s*Years?\s*"
                    r"(\d{1,2}/\s*\d{1,2}/\d{2,4})\s*[-–]\s*(\d{1,2}/\s*\d{1,2}/\d{2,4})",
                    cell0,
                )
                if not m:
                    # Try without year line (multi-line split by \n already flattened)
                    m = re.match(
                        r"([A-Z]{2,3})\s*[-–]\s*(\d+)\s*Years?",
                        cell0,
                    )
                    if not m:
                        continue
                    abbr, years = m.group(1), int(m.group(2))
                    planet = VIMSH_PLANET_NORM.get(abbr)
                    if not planet or planet in seen:
                        continue
                    # Dates not found yet — handled in text scan below
                    dasha.append({"planet": planet, "years": years, "start": None, "end": None})
                    seen.add(planet)
                else:
                    abbr, years = m.group(1), int(m.group(2))
                    planet = VIMSH_PLANET_NORM.get(abbr)
                    if not planet or planet in seen:
                        continue
                    start = parse_date_text(m.group(3).replace(" ", ""))
                    end = parse_date_text(m.group(4).replace(" ", ""))
                    dasha.append({"planet": planet, "years": years, "start": start, "end": end})
                    seen.add(planet)

    # Text-based fallback
    pattern = re.compile(
        r"([A-Z]{2,3})\s*[-–]\s*(\d+)\s*Years?\s*"
        r"(\d{1,2}/\s*\d{1,2}/\d{2,4})\s*[-–]\s*(\d{1,2}/\s*\d{1,2}/\d{2,4})",
        re.MULTILINE,
    )
    for text in pages_text:
        if not text:
            continue
        for m in pattern.finditer(text):
            abbr = m.group(1)
            planet = VIMSH_PLANET_NORM.get(abbr)
            if not planet or planet in seen:
                continue
            years = int(m.group(2))
            start = parse_date_text(m.group(3).replace(" ", ""))
            end = parse_date_text(m.group(4).replace(" ", ""))
            dasha.append({"planet": planet, "years": years, "start": start, "end": end})
            seen.add(planet)

    # Fill missing dates by chaining durations if possible
    _fill_missing_dasha_dates(dasha)
    # Ensure dates are monotonically increasing (2-digit year wrap-around fix)
    _fix_monotonic_dates(dasha)

    return dasha if dasha else None


def _date_to_tuple(date_str):
    """Parse 'DD/MM/YYYY' to (YYYY, MM, DD) tuple for comparison."""
    if not date_str:
        return None
    try:
        parts = date_str.split("/")
        return (int(parts[2]), int(parts[1]), int(parts[0]))
    except (IndexError, ValueError):
        return None


def _bump_year_100(date_str):
    """Add 100 years to a 'DD/MM/YYYY' date string."""
    if not date_str:
        return date_str
    try:
        d, m, y = date_str.split("/")
        return f"{d}/{m}/{int(y) + 100}"
    except (ValueError, AttributeError):
        return date_str


def _fix_monotonic_dates(dasha):
    """
    Correct dates that went backwards due to 2-digit year wrap-around.
    Iterates entries and bumps dates by +100 years if they precede the previous date.
    """
    prev = None
    for entry in dasha:
        for key in ("start", "end"):
            t = _date_to_tuple(entry[key])
            if t and prev and t < prev:
                entry[key] = _bump_year_100(entry[key])
                t = _date_to_tuple(entry[key])
            if t:
                prev = t


def _fill_missing_dasha_dates(dasha):
    """Best-effort: chain start/end across entries if only some are missing."""
    for i, entry in enumerate(dasha):
        if entry["end"] and not entry.get("start"):
            if i > 0 and dasha[i - 1].get("end"):
                entry["start"] = dasha[i - 1]["end"]
        if entry["start"] and not entry.get("end"):
            if i + 1 < len(dasha) and dasha[i + 1].get("start"):
                entry["end"] = dasha[i + 1]["start"]


def extract_yogini(pages_text, pages_tables):
    """Extract top-level Yogini Dasha periods (only from Yogini Dasha pages)."""
    dasha = []
    seen = set()

    for page_idx, (text, tables) in enumerate(zip(pages_text, pages_tables)):
        if not text or "yogini" not in text.lower():
            continue

        for table in tables:
            if not table:
                continue
            cell0 = flatten_cell(table[0][0] if table and table[0] else None)
            if not cell0:
                continue
            m = re.match(r"([A-Za-z]{2,3})\s+(\d+)\s+Years?", cell0)
            if not m:
                continue
            abbr = m.group(1)
            # Capitalize first two chars for YOGINI_FULL lookup (e.g. "Pi", "Dh")
            yogini_full = YOGINI_FULL.get(abbr[:2].title())
            if not yogini_full:
                continue
            years = int(m.group(2))
            # Validate: Yogini years must be 1-8
            if years not in YOGINI_YEARS.values():
                continue

            start_date = None
            end_date = None
            for row in table[1:]:
                if not row:
                    continue
                key = flatten_cell(row[0]).strip().lower()
                val = flatten_cell(row[1]).strip() if len(row) > 1 else ""
                if key == "from":
                    start_date = parse_date_text(val)
                elif key == "to":
                    end_date = parse_date_text(val)

            key = (yogini_full, start_date)
            if key in seen:
                continue
            seen.add(key)
            dasha.append({"yogini": yogini_full, "years": years, "start": start_date, "end": end_date})

    return dasha if dasha else None


def extract_sadesati(pages_text, pages_tables):
    """Extract Sade Sati table (only from pages containing 'Sadesati Report')."""
    entries = []
    valid_signs = {s.lower() for s in ZODIAC_SIGNS}

    for page_idx, (text, tables) in enumerate(zip(pages_text, pages_tables)):
        # Only process Sade Sati pages
        if not text or ("sadesati" not in text.lower() and "sade sati" not in text.lower()):
            continue

        for table in tables:
            if not table or len(table) < 2:
                continue
            header = [flatten_cell(c).lower() for c in (table[0] or [])]
            if not any("sade" in h or "panoti" in h or "s.n" in h for h in header):
                continue

            # Determine column indices
            def col(keywords):
                for kw in keywords:
                    for i, h in enumerate(header):
                        if kw in h:
                            return i
                return None

            ci_type = col(["sade", "panoti"]) or 1
            ci_rashi = col(["rashi", "rasi"]) or 2
            ci_start = col(["start"]) or 3
            ci_end = col(["end"]) or 4
            ci_phase = col(["phase"]) or 5

            for row in table[1:]:
                if not row or len(row) < 3:
                    continue

                def safe_get(idx):
                    return flatten_cell(row[idx]) if idx < len(row) else ""

                type_raw = safe_get(ci_type)
                rashi_raw = safe_get(ci_rashi)

                if not type_raw or not rashi_raw:
                    continue
                # Skip header-repeat rows
                if type_raw.lower() in ("sade sati/ panoti", "sade sati/\npanoti", "type"):
                    continue
                # Validate rashi: must be a known zodiac sign
                rashi = normalize_sign(rashi_raw)
                if not rashi or rashi.lower() not in valid_signs:
                    continue

                start_raw = safe_get(ci_start)
                end_raw = safe_get(ci_end)
                phase_raw = safe_get(ci_phase)

                entry_type = "Sade Sati" if "sade" in type_raw.lower() else "Small Panoti"
                start = parse_date_text(start_raw)
                end = parse_date_text(end_raw)
                phase = phase_raw.strip() if phase_raw and phase_raw.strip() else None

                entries.append({
                    "type": entry_type,
                    "rashi": rashi,
                    "start": start,
                    "end": end,
                    "phase": phase,
                })

    return entries if entries else None


def detect_kalsarpa(pages_text):
    """Return False if Kalsarpa Yoga is absent, True if present, else None."""
    for text in pages_text:
        if not text:
            continue
        # Search raw text (do NOT clean_text — it mangles normal body content)
        tl = text.lower()
        if "kalsarpa" not in tl and "kalsarp" not in tl:
            continue
        # Check for explicit "free from" result line first
        if re.search(r"free\s+from\s+kalsarpa", tl):
            return False
        if re.search(r"result\s*:\s*[^.]*free", tl):
            return False
        if re.search(r"no\s+kalsarpa", tl):
            return False
        # Check for positive presence (explicit "result" line only)
        if re.search(r"result\s*:\s*[^.]*present", tl):
            return True
    return None

# ── Main orchestration ─────────────────────────────────────────────────────────

def pdf_to_kundali_json(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        pages_text = []
        pages_tables = []
        for page in pdf.pages:
            pages_text.append(page.extract_text() or "")
            pages_tables.append(page.extract_tables() or [])

    # 1. Basic details
    basic = extract_basic_details(pages_text, pages_tables)
    lagna_sign = basic.get("lagna")

    # 2. Planets
    planets = extract_planets(pages_text, pages_tables, lagna_sign)

    # 3. Ashtakavarga
    ashtakavarga = extract_ashtakavarga(pages_text, pages_tables)

    # 4. Vimshottari Dasha
    vimshottari = extract_vimshottari(pages_text, pages_tables)

    # 5. Yogini Dasha
    yogini = extract_yogini(pages_text, pages_tables)

    # 6. Sade Sati
    sadesati = extract_sadesati(pages_text, pages_tables)

    # 7. Kalsarpa
    kalsarpa = detect_kalsarpa(pages_text)

    result = {
        "basic_details": basic,
        "planets": planets,
        "Ashtakavarga": ashtakavarga,
        "Vimshottari_Dasha": vimshottari,
        "Yogini_Dasha": yogini,
        "SadeSati": sadesati,
        "Kalsarpa": kalsarpa,
    }
    return result


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 kundali_pdf_to_json.py <input.pdf> [output.json]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else pdf_path.replace(".pdf", ".json")

    data = pdf_to_kundali_json(pdf_path)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"✓ Saved: {output_path}")


if __name__ == "__main__":
    main()
