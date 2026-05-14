def upper_short_disease_codes(disease_codes: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(short_disease_code(code).upper() for code in disease_codes)

def short_disease_codes(disease_codes: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(short_disease_code(code) for code in disease_codes)


def short_disease_code(code: str) -> str:
    if code in ("mm", "fl", "bc", "cll"):
        return code
    if code == "multiple myeloma":
        return "mm"
    if code == "follicular lymphoma":
        return "fl"
    if code == "breast cancer":
        return "bc"
    if code == "chronic lymphocytic leukemia":
        return "cll"
    raise ValueError(f"Unknown disease code: '{code}'")
