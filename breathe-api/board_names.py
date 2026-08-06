"""State → RT licensing board name mapping for all 50 states + DC.

Sources: AARC state licensure directory, NBRC, state board websites.
Some states license RTs through medical boards or umbrella agencies;
a few states (AK, CO, HI) do not require RT licensure at the state level.

Verify before using on official documents — board names can change.
"""

STATE_BOARD_NAMES = {
    "AL": "Alabama State Board of Respiratory Therapy",
    "AK": "Alaska Department of Commerce, Community & Economic Development",
    "AZ": "Arizona Medical Board",
    "AR": "Arkansas State Medical Board",
    "CA": "California Respiratory Care Board",
    "CO": "Colorado Department of Regulatory Agencies (DORA)",
    "CT": "Connecticut Department of Public Health",
    "DE": "Delaware Board of Medical Licensure and Discipline",
    "DC": "District of Columbia Board of Respiratory Care",
    "FL": "Florida Board of Respiratory Care",
    "GA": "Georgia State Board of Respiratory Care",
    "HI": "Hawaii Department of Commerce and Consumer Affairs",
    "ID": "Idaho State Board of Medicine",
    "IL": "Illinois Department of Financial and Professional Regulation",
    "IN": "Indiana Respiratory Care Committee",
    "IA": "Iowa Board of Respiratory Care and Polysomnography",
    "KS": "Kansas Board of Healing Arts",
    "KY": "Kentucky Board of Respiratory Care",
    "LA": "Louisiana State Board of Medical Examiners",
    "ME": "Maine Board of Respiratory Care Practitioners",
    "MD": "Maryland Board of Physicians",
    "MA": "Massachusetts Board of Registration of Respiratory Care",
    "MI": "Michigan Department of Licensing and Regulatory Affairs (LARA)",
    "MN": "Minnesota Board of Medical Practice",
    "MS": "Mississippi State Board of Health - Respiratory Care",
    "MO": "Missouri Board for Respiratory Care",
    "MT": "Montana Board of Respiratory Care Practitioners",
    "NE": "Nebraska Department of Health and Human Services",
    "NV": "Nevada State Board of Medical Examiners",
    "NH": "New Hampshire Board of Respiratory Care Practitioners",
    "NJ": "New Jersey Respiratory Care Advisory Committee",
    "NM": "New Mexico Respiratory Care Advisory Board",
    "NY": "New York State Education Department, Office of the Professions",
    "NC": "North Carolina Respiratory Care Board",
    "ND": "North Dakota Board of Respiratory Care",
    "OH": "Ohio Respiratory Care Board",
    "OK": "Oklahoma Medical Board - Respiratory Care",
    "OR": "Oregon Respiratory Therapist and Polysomnographic Technologist Licensing Board",
    "PA": "Pennsylvania State Board of Medicine",
    "RI": "Rhode Island Department of Health",
    "SC": "South Carolina Board of Medical Examiners",
    "SD": "South Dakota Board of Medical and Osteopathic Examiners",
    "TN": "Tennessee Board of Respiratory Care",
    "TX": "Texas Medical Board",
    "UT": "Utah Division of Professional Licensing (DOPL)",
    "VT": "Vermont Office of Professional Regulation",
    "VA": "Virginia Board of Medicine",
    "WA": "Washington State Department of Health",
    "WV": "West Virginia Board of Respiratory Care",
    "WI": "Wisconsin Department of Safety and Professional Services",
    "WY": "Wyoming Board of Respiratory Care",
}

DEFAULT_BOARD_NAME = "State Licensing Board"


def get_board_name(state_code: str) -> str:
    """Return the board name for a state code, with fallback."""
    return STATE_BOARD_NAMES.get(state_code.upper(), DEFAULT_BOARD_NAME)