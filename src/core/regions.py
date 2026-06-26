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

PER_REGION_LIMIT_MIN = 25
PER_REGION_LIMIT_MAX = 1000
PER_REGION_LIMIT_DEFAULT = 200


def is_valid_region(country: str, region: str) -> bool:
    """Check if a given region is valid for the specified country."""
    if country not in REGIONS_MAP:
        return False
    return region in REGIONS_MAP[country]


def clamp_per_region_limit(value: int) -> int:
    """Clamp Per-Region Limit to the allowed Bright Data range."""
    return max(PER_REGION_LIMIT_MIN, min(PER_REGION_LIMIT_MAX, value))


def validate_search_regions(
    countries: list[str],
    search_regions: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Validate Search Regions for selected countries; return normalized pairs."""
    normalized_countries = [c.strip().upper() for c in countries if c.strip()]
    if not normalized_countries:
        normalized_countries = ["US"]

    regions_by_country: dict[str, list[str]] = {c: [] for c in normalized_countries}
    normalized_pairs: list[tuple[str, str]] = []

    for country, region in search_regions:
        country_upper = country.strip().upper()
        region_name = region.strip()
        if region_name.lower() == "remote":
            raise ValueError('"Remote" is not a valid Search Region')
        if not is_valid_region(country_upper, region_name):
            raise ValueError(f'Unknown region "{region_name}" for country {country_upper}')
        if country_upper not in normalized_countries:
            raise ValueError(
                f'Region "{region_name}" specified for unselected country {country_upper}'
            )
        regions_by_country[country_upper].append(region_name)
        normalized_pairs.append((country_upper, region_name))

    for country in normalized_countries:
        if not regions_by_country.get(country):
            raise ValueError(f"Country {country} requires at least one Search Region")

    return normalized_pairs
