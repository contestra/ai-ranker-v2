# ALS Templates - PRODUCTION VERSION

## ⚠️ CRITICAL: Do Not Modify als_templates.py

This file contains the production-calibrated ALS templates that were tested over weeks in V1.

**Key Features:**
- Unicode escape sequences (\u00fc for ü, \u20ac for €)
- Regulatory cues (MwSt, VAT) instead of weather
- Bundesportal civic keyword for Germany
- ≤350 character limit per template

**DO NOT:**
- Create alternative versions
- Modify existing templates
- Change Unicode escapes
- Alter civic keywords

**Files in this directory:**
- `als_templates.py` - **PRODUCTION VERSION** (use this)
- `als_builder.py` - Builds ALS blocks from templates
- `als_harvester.py` - Web search integration for evidence
- `country_codes.py` - Country code validation and mapping

**Related file:**
- `../als_constants.py` - ALS system prompt (calibrated, do not modify)

**Archived versions:**
Old experimental versions have been moved to `archive_old_versions/` directory.
These are kept for reference only. DO NOT USE THEM.

Last verified: August 23, 2025
Identical to V1 reference: ✅ Confirmed