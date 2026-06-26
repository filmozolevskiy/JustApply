"""Search Region definitions and validation."""

# Curated major job-market states for the US
US_REGIONS = [
    "California",
    "New York",
    "Texas",
    "Florida",
    "Illinois",
    "Washington",
    "Pennsylvania",
    "Georgia",
    "North Carolina",
    "Virginia",
    "Massachusetts",
    "New Jersey",
    "Colorado",
]

# First-level divisions for CA, DE, GB
CA_REGIONS = [
    "Alberta",
    "British Columbia",
    "Manitoba",
    "New Brunswick",
    "Newfoundland and Labrador",
    "Nova Scotia",
    "Ontario",
    "Prince Edward Island",
    "Quebec",
    "Saskatchewan",
    "Northwest Territories",
    "Nunavut",
    "Yukon",
]

DE_REGIONS = [
    "Baden-Württemberg",
    "Bavaria",
    "Berlin",
    "Brandenburg",
    "Bremen",
    "Hamburg",
    "Hesse",
    "Lower Saxony",
    "Mecklenburg-Vorpommern",
    "North Rhine-Westphalia",
    "Rhineland-Palatinate",
    "Saarland",
    "Saxony",
    "Saxony-Anhalt",
    "Schleswig-Holstein",
    "Thuringia",
]

GB_REGIONS = [
    "England",
    "Scotland",
    "Wales",
    "Northern Ireland",
]

REGIONS_MAP = {
    "US": US_REGIONS,
    "CA": CA_REGIONS,
    "DE": DE_REGIONS,
    "GB": GB_REGIONS,
}

def is_valid_region(country: str, region: str) -> bool:
    """Check if a given region is valid for the specified country."""
    if country not in REGIONS_MAP:
        return False
    return region in REGIONS_MAP[country]
