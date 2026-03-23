from __future__ import annotations

from zoneinfo import ZoneInfo

PROJECT_NAME = "Wireman Tracker"
TIMEZONE_NAME = "America/Los_Angeles"
TIMEZONE = ZoneInfo(TIMEZONE_NAME)
REQUEST_TIMEOUT_SECONDS = 30
BROWSER_VIRTUAL_TIME_BUDGET_MS = 12_000
KEEP_EXPIRED_DAYS = 30
MAX_DESCRIPTION_CHARS = 2_400

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

SOURCE_URLS = {
    "cei": "https://www.cei.com/careers/current-openings",
    "emcor": "https://emcorgroup.com/careers/trade-apprenticeships",
    "bergelectric": "https://www.bergelectric.com/careers/",
    "primeelectric": "https://www.primeelectric.com/careers/",
    "oeg": "https://oeg.us.com/careers/",
    "mortenson": "https://www.mortenson.com/careers/data-center",
    "turner": "https://www.turnerconstruction.com/careers/labor-and-skilled-trade-professionals",
    "kiewit": "https://join.kiewit.com/union-craft-us/",
}

OEG_BOARD_URL = (
    "https://everus.rec.pro.ukg.net/MDU1500MDUC/JobBoard/"
    "fa8383b2-655f-4d78-9141-678949d846e1/?q=&o=postedDateDesc&w=&wc=&we=&wpst="
)

EMCOR_QUERY_TERMS = [
    "apprentice",
    "electrical apprentice",
    "electrician",
    "wireman",
    "low voltage",
]

BERGELECTRIC_QUERY_TERMS = [
    "apprentice",
    "electrical apprentice",
    "electrician",
    "wireman",
    "helper",
]

MORTENSON_QUERY_TERMS = [
    "apprentice",
    "electrical apprentice",
    "electric",
    "low voltage",
    "mission critical",
]

TURNER_QUERY_TERMS = [
    "apprentice",
    "electric",
    "wireman",
    "inside wireman",
]

PRIORITY_HUBS = {
    "Hillsboro, OR": ("hillsboro",),
    "Prineville, OR": ("prineville",),
    "Boardman, OR": ("boardman",),
    "Quincy, WA": ("quincy",),
    "Ashburn, VA": ("ashburn",),
    "Columbus, OH": ("columbus",),
    "Plain City, OH": ("plain city",),
    "Monroe, OH": ("monroe",),
    "Dallas-Fort Worth, TX": ("dallas", "fort worth"),
    "Austin, TX": ("austin",),
    "San Antonio, TX": ("san antonio",),
    "Phoenix, AZ": ("phoenix",),
}

REGIONAL_HUBS = {
    "Portland, OR": ("portland, or", "us-or-portland"),
    "Beaverton, OR": ("beaverton",),
    "Tualatin, OR": ("tualatin",),
    "Vancouver, WA": ("vancouver, wa", "us-wa-vancouver"),
    "Seattle, WA": ("seattle, wa", "us-wa-seattle"),
    "Bellevue, WA": ("bellevue",),
    "Tacoma, WA": ("tacoma",),
    "Hermiston, OR": ("hermiston",),
    "Umatilla, OR": ("umatilla",),
    "The Dalles, OR": ("the dalles",),
    "Salem, OR": ("salem, or", "us-or-salem"),
    "Eugene, OR": ("eugene",),
    "San Jose, CA": ("san jose",),
    "Santa Clara, CA": ("santa clara",),
    "Sacramento, CA": ("sacramento",),
    "Dublin, CA": ("dublin, ca",),
}

RELOCATION_SIGNALS = (
    "relocation assistance",
    "relocation package",
    "relocation support",
    "relocation available",
    "relocation offered",
    "relocation reimbursement",
    "relocation benefits",
    "relocation bonus",
)

WEST_COAST_LOCATION_MARKERS = (
    "us-or-",
    "oregon",
    ", or",
    "or, united states",
    "us-wa-",
    "washington",
    ", wa",
    "wa, united states",
    "us-ca-",
    "california",
    ", ca",
    "ca, united states",
)

STRONG_TITLE_SIGNALS = {
    "inside wireman": 85,
    "electrical apprentice": 80,
    "electrician apprentice": 80,
    "apprentice electrician": 80,
    "wireman apprentice": 76,
    "low voltage integration technician / apprentice": 55,
    "low voltage technician / apprentice": 48,
    "electrical helper": 42,
}

TITLE_SIGNALS = {
    "apprentice": 26,
    "electrician": 24,
    "electrical": 18,
    "electric": 12,
    "low voltage": 16,
    "fiber": 8,
    "controls": 8,
}

DESCRIPTION_SIGNALS = {
    "apprenticeship": 22,
    "inside wireman": 28,
    "electrician": 14,
    "electrical": 10,
    "low voltage": 10,
    "fiber optic": 8,
    "mission critical": 24,
    "data center": 18,
    "critical facilities": 18,
    "hyperscale": 14,
    "colocation": 12,
}

SOURCE_CONTEXT_SIGNALS = {
    "data center": 24,
    "mission critical": 20,
    "modular": 6,
}

NEGATIVE_TITLE_SIGNALS = {
    "intern": -55,
    "internship": -55,
    "template": -65,
    "manager": -48,
    "superintendent": -55,
    "director": -50,
    "engineer": -35,
    "estimator": -42,
    "buyer": -34,
    "controller": -38,
    "accountant": -42,
    "designer": -28,
    "developer": -25,
    "recruiter": -42,
    "sourcer": -42,
    "hr": -40,
    "human resources": -40,
    "safety": -45,
    "coordinator": -22,
    "project manager": -48,
    "project engineer": -30,
    "laborer": -55,
    "carpenter": -55,
    "millwright": -55,
    "fitter": -55,
    "pipefitter": -60,
    "welder": -55,
    "mechanic": -48,
    "production worker": -55,
    "journeyman": -45,
    "journeyperson": -45,
    "civil": -36,
    "commissioning": -22,
    "marshal": -30,
}

NEGATIVE_DESCRIPTION_SIGNALS = {
    "salary range": -8,
    "engineering": -12,
    "project management": -18,
}
