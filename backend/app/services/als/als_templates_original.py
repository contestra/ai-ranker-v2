"""
Ambient Location Signals (ALS) templates and renderer.

- Brand-neutral civic signals only (no URLs/news/retailers).
- Rendered as a compact 3–5 bullet block (≤ 350 characters).
- The ALS block MUST be sent as its own message BEFORE the naked user prompt.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
from zoneinfo import ZoneInfo
import random

MAX_CHARS = 350

@dataclass
class CountryTemplate:
    code: str
    country: str
    timezone: Optional[str] = None               # primary tz (or None if samples provided)
    timezone_samples: Optional[List[str]] = None # for multi-timezone countries
    utc_offsets: Dict[str, str] = field(default_factory=dict)
    civic_keyword: str = ""                      # non-clickable keyword (no URL), e.g., "GOV.UK"
    phrases: List[str] = field(default_factory=list)   # local-language civic phrases (rotation pool)
    formatting_example: str = ""                 # "postal • phone • currency"
    weather_stub_local: str = ""                 # empty to omit
    notes: List[str] = field(default_factory=list)

class ALSTemplates:
    """
    Static library of Ambient Blocks with a renderer.
    Last updated: 2025-08-12
    """

    TEMPLATES: Dict[str, CountryTemplate] = {
        # Germany
        "DE": CountryTemplate(
            code="DE",
            country="Germany",
            timezone="Europe/Berlin",
            utc_offsets={"summer": "+02:00", "winter": "+01:00"},
            civic_keyword="Bürgeramt",  # Changed from Bundesportal (contains 'de') to avoid leak
            phrases=[
                "Reisepass beantragen Termin",
                "Führerschein umtauschen",
                "Anmeldung Bürgeramt",
                "ELSTER Steuererklärung",
                "Kindergeld Antrag",
                "Aufenthaltstitel verlängern",
            ],
            formatting_example="10115 Berlin • +49 30 xxx xx xx • 12,90 €",
            weather_stub_local="Nationaler Wetterdienst: Berlin",
            notes=[
                "5-digit postal codes; comma decimals (12,90 €); +49 phone",
                "Orthography: Straße (ß) vs CH Strasse",
                "Date: DD.MM.YYYY",
            ],
        ),
        # Switzerland (multilingual)
        "CH": CountryTemplate(
            code="CH",
            country="Switzerland",
            timezone="Europe/Zurich",
            utc_offsets={"summer": "+02:00", "winter": "+01:00"},
            civic_keyword="Bundesverwaltung",  # Changed from ch.ch to avoid .ch leak
            phrases=[
                "Führerausweis verlängern / renouveler permis",
                "AHV / AVS Nummer",
                "e-Umzug melden",
                "Steuererklärung einreichen",
                "ID verlängern",
                "Einwohnerkontrolle",
            ],
            formatting_example="8001 Zürich • +41 44 xxx xx xx • CHF 12.90",
            weather_stub_local="Nationaler Wetterdienst: Zürich",
            notes=[
                "4-digit postal codes; CHF 12.90; +41 phone",
                "Orthography: Strasse (ss) (no ß)",
                "Multilingual: DE/FR/IT names vary",
            ],
        ),
        # United States
        "US": CountryTemplate(
            code="US",
            country="United States",
            timezone_samples=["America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles"],
            utc_offsets={"ET": "-05:00", "CT": "-06:00", "MT": "-07:00", "PT": "-08:00"},
            civic_keyword="state DMV",
            phrases=[
                "driver license renewal appointment",
                "passport application online",
                "Social Security card replacement",
                "voter registration",
                "IRS tax return filing",
                "REAL ID appointment",
                "vehicle registration",
            ],
            formatting_example="New York, NY 10001 • (212) xxx-xxxx • $12.90",
            weather_stub_local="national weather service: New York",
            notes=[
                "City, ST ZIP; $12.90; +1/(xxx) xxx-xxxx",
                "Multiple timezones (ET/CT/MT/PT)",
            ],
        ),
        # United Kingdom
        "GB": CountryTemplate(
            code="GB",
            country="United Kingdom",
            timezone="Europe/London",
            utc_offsets={"summer": "+01:00", "winter": "+00:00"},
            civic_keyword="GOV.UK",
            phrases=[
                "driving licence renewal online",
                "passport renewal",
                "council tax payment",
                "NHS GP registration",
                "National Insurance number",
                "Universal Credit claim",
                "MOT test booking",
            ],
            formatting_example="London SW1A 1AA • +44 20 xxxx xxxx • £12.90",
            weather_stub_local="national weather service: London",
            notes=[
                "UK postcodes; £12.90; +44 phone",
                "Date: DD/MM/YYYY",
            ],
        ),
        # United Arab Emirates
        "AE": CountryTemplate(
            code="AE",
            country="United Arab Emirates",
            timezone="Asia/Dubai",
            utc_offsets={"year_round": "+04:00"},
            civic_keyword="الهوية والجنسية (ICP)",
            phrases=[
                "تجديد بطاقة الهوية الإماراتية",
                "حالة تأشيرة الإقامة",
                "سداد المخالفات المرورية",
                "تسجيل عقد الإيجار",
                "تجديد الرخصة التجارية",
                "فحص اللياقة الطبية",
                "تجديد رخصة القيادة",
            ],
            formatting_example="دبي ص.ب. • +971 4 xxx xxxx • 49.00 د.إ",
            weather_stub_local="الخدمة الوطنية للأرصاد: دبي",
            notes=[
                "No nationwide postcodes; AED; +971 phone",
            ],
        ),
        # Singapore
        "SG": CountryTemplate(
            code="SG",
            country="Singapore",
            timezone="Asia/Singapore",
            utc_offsets={"year_round": "+08:00"},
            civic_keyword="ICA",
            phrases=[
                "passport appointment online",
                "Singpass login",
                "CPF statement",
                "FIN card renewal",
                "HDB BTO application",
                "MOM work pass status",
                "road tax renewal",
            ],
            formatting_example="Singapore 049315 • +65 6xxx xxxx • S$12.90",
            weather_stub_local="national weather service: Singapore",
            notes=[
                "6-digit postal; S$12.90; +65 phone",
                "Singpass casing (not SingPass)",
            ],
        ),
        # Italy
        "IT": CountryTemplate(
            code="IT",
            country="Italy",
            timezone="Europe/Rome",
            utc_offsets={"summer": "+02:00", "winter": "+01:00"},
            civic_keyword="Agenzia delle Entrate",
            phrases=[
                "codice fiscale richiesta",
                "patente rinnovo",
                "SPID attivazione",
                "ISEE compilazione",
                "certificato di residenza",
                "Carta d'identità elettronica",
            ],
            formatting_example="00100 Roma • +39 06 xxxx xxxx • 12,90 €",
            weather_stub_local="servizio meteo nazionale: Roma",
            notes=[
                "5-digit CAP; comma decimals (12,90 €); +39 phone",
                "Date: DD/MM/YYYY",
            ],
        ),
        # France
        "FR": CountryTemplate(
            code="FR",
            country="France",
            timezone="Europe/Paris",
            utc_offsets={"summer": "+02:00", "winter": "+01:00"},
            civic_keyword="Service Public",  # Changed from service-public.fr to avoid .fr leak
            phrases=[
                "Carte d'identité renouvellement",
                "passeport demande en ligne",
                "permis de conduire",
                "Carte Vitale demande",
                "FranceConnect connexion",
                "impôts déclaration",
                "acte de naissance",
            ],
            formatting_example="75001 Paris • +33 1 xx xx xx xx • 12,90 €",
            weather_stub_local="service météo national : Paris",
            notes=[
                "5-digit postal; € with comma decimals; +33 phone",
                "Date: DD/MM/YYYY",
            ],
        ),
    }

    @classmethod
    def supported_countries(cls) -> List[str]:
        return list(cls.TEMPLATES.keys())

    @classmethod
    def render_block(
        cls,
        code: str,
        now: Optional[datetime] = None,
        tz_override: Optional[str] = None,
        phrase_idx: Optional[int] = None,
        include_weather: bool = True,
        header_language: Optional[str] = None,
    ) -> str:
        """
        Render a leak-resistant ALS block for a given country code.
        - Chooses timestamp and UTC offset using the country tz (or a sample tz).
        - Picks a civic phrase (deterministic if phrase_idx provided).
        - Returns a 3–5 line block ≤ 350 chars; raises ValueError if it cannot fit.
        """
        code = code.upper()
        if code not in cls.TEMPLATES:
            raise KeyError(f"Unsupported country code: {code}")

        tpl = cls.TEMPLATES[code]

        # Timestamp + offset
        if tz_override:
            tz = ZoneInfo(tz_override)
        elif tpl.timezone:
            tz = ZoneInfo(tpl.timezone)
        elif tpl.timezone_samples:
            tz = ZoneInfo(random.choice(tpl.timezone_samples))
        else:
            tz = ZoneInfo("UTC")

        now = now or datetime.now(tz)
        stamp = now.strftime("%Y-%m-%d %H:%M")
        offset_seconds = tz.utcoffset(now)
        # offset like +HH:MM
        total_minutes = int(offset_seconds.total_seconds() // 60) if offset_seconds else 0
        sign = "+" if total_minutes >= 0 else "-"
        hh = abs(total_minutes) // 60
        mm = abs(total_minutes) % 60
        offset_str = f"{sign}{hh:02d}:{mm:02d}"

        # Phrase selection
        if not tpl.phrases:
            raise ValueError(f"No civic phrases configured for {code}")
        idx = (phrase_idx % len(tpl.phrases)) if isinstance(phrase_idx, int) else 0
        phrase = tpl.phrases[idx]

        # Header language
        header = {
            "DE": "Lokaler Kontext (nur zur Lokalisierung; nicht zitieren):",
            "CH": "Lokaler Kontext (nur zur Lokalisierung; nicht zitieren):",
            "IT": "Contesto locale (solo per la localizzazione; non citare):",
            "FR": "Contexte local (uniquement pour la localisation ; ne pas citer) :",
            "GB": "Ambient Context (localisation only; do not cite):",
            "US": "Ambient Context (localization only; do not cite):",
            "AE": "سياق محلي (لأغراض تحديد الموقع فقط؛ لا تُذكر):",
            "SG": "Ambient Context (localization only; do not cite):",
        }.get(code, "Ambient Context (localization only; do not cite):")

        if header_language:
            header = header_language

        lines = [
            f"{header}",
            f"- {stamp}, {offset_str}",
            f"- {tpl.civic_keyword} — “{phrase}”",
            f"- {tpl.formatting_example}",
        ]
        if include_weather and tpl.weather_stub_local:
            lines.append(f"- {tpl.weather_stub_local}")

        block = "\n".join(lines)

        # Validate max length
        if len(block) > MAX_CHARS:
            # Try without weather
            if include_weather and tpl.weather_stub_local:
                lines = lines[:-1]
                block = "\n".join(lines)
        if len(block) > MAX_CHARS:
            # Try trimming header to English generic
            lines[0] = "Ambient Context (localization only; do not cite):"
            block = "\n".join(lines)

        if len(block) > MAX_CHARS:
            raise ValueError(f"ALS block too long ({len(block)} chars) for {code}.")

        return block

    @classmethod
    def example_blocks(cls) -> Dict[str, str]:
        """Return one example block per supported country (deterministic phrase)."""
        out = {}
        now = datetime(2025, 8, 12, 14, 5)
        for code in cls.supported_countries():
            out[code] = cls.render_block(code, now=now, phrase_idx=0)
        return out

    @classmethod
    def last_updated(cls) -> str:
        return "2025-08-12"
