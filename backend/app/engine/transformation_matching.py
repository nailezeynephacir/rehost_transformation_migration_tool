from typing import Any, Dict, List, Optional, Tuple

from .parser import mask_comments, normalize_function_signature

# Aramayı boşluksuz ve yorumsuz kod üzerinde yaparız (normalize_code_text). 
# Değişikliği ise pozisyon haritası sayesinde gerçek kaynak kod üzerinde yaparız. (normalize_code_with_positions)

def is_identifier_character(character: str) -> bool:
    # C/C++ identifiers may contain letters, digits, and underscores.
    return character == "_" or character.isalnum()


def normalize_code_text(text: str) -> str:
    # Ignore comments and insignificant whitespace while preserving identifier boundaries and literal contents.
    normalized_text, _ = normalize_code_with_positions(text)

    return normalized_text


def normalize_code_with_positions(text: str) -> Tuple[str, List[int]]:
    # Normalize source code while keeping a mapping back to the original character positions.
    # Whitespace between identifiers is represented by a single space so separate tokens such as "int x" cannot become "intx".
    # Whitespace inside string and character literals is preserved.
    masked_text = mask_comments(text)

    normalized_characters = []
    original_positions = []

    state = "NORMAL"
    pending_whitespace = False
    index = 0

    while index < len(masked_text):
        character = masked_text[index]

        if state == "NORMAL":
            if character.isspace():
                pending_whitespace = True
                index += 1
                continue

            if (pending_whitespace
                and normalized_characters
                and is_identifier_character(normalized_characters[-1])
                and is_identifier_character(character)
            ):
                normalized_characters.append(" ")
                original_positions.append(index)

            pending_whitespace = False

            normalized_characters.append(character)
            original_positions.append(index)

            if character == '"':
                state = "STRING"
            elif character == "'":
                state = "CHAR"

            index += 1
            continue

        # Preserve everything inside string and character literals, including whitespace.
        normalized_characters.append(character)
        original_positions.append(index)

        if character == "\\" and index + 1 < len(masked_text):
            index += 1
            normalized_characters.append(masked_text[index])
            original_positions.append(index)

        elif (state == "STRING" and character == '"'):
            state = "NORMAL"

        elif (state == "CHAR" and character == "'"):
            state = "NORMAL"

        index += 1

    return "".join(normalized_characters), original_positions


def has_identifier_boundaries(normalized_source: str, normalized_target: str, match_start: int,) -> bool:
    # Prevent an identifier from matching inside a longer identifier.
    match_end = match_start + len(normalized_target)

    if (is_identifier_character(normalized_target[0])
        and match_start > 0
        and is_identifier_character(normalized_source[match_start - 1])):
        return False

    if (is_identifier_character(normalized_target[-1])
        and match_end < len(normalized_source)
        and is_identifier_character(normalized_source[match_end])):
        return False

    return True

def find_normalized_matches(source_text: str, target_text: str) -> List[Dict[str, Any]]:
    # Find every normalized occurrence of target_text in source_text.
    # Each result contains the real start and end character positions from the original source text.
    normalized_source, source_positions = (normalize_code_with_positions(source_text))

    normalized_target = normalize_code_text(target_text)

    if not normalized_target:
        return []

    matches = []
    search_start = 0

    while True:
        normalized_start = normalized_source.find(normalized_target, search_start,)

        if normalized_start == -1:
            break

        if not has_identifier_boundaries(normalized_source, normalized_target, normalized_start,):
            search_start = normalized_start + 1
            continue

        normalized_end = normalized_start + len(normalized_target)

        source_start = source_positions[normalized_start]
        source_end = source_positions[normalized_end - 1] + 1

        matches.append(
            {
                "start": source_start,
                "end": source_end,
                "matched_text": source_text[source_start:source_end],
            }
        )

        # Move one normalized character forward so all possible occurrences can be detected.
        search_start = normalized_start + 1

    return matches


def move_matches_to_source_positions(matches: List[Dict[str, Any]], region_start: int, source_text: str) -> List[Dict[str, Any]]:
    # Convert positions relative to a search region into positions relative to the complete source file.
    # Region olarak baktığımız için tüm dosyadaki yerlerini bulmamız gerekiyor sonrasında.
    adjusted_matches = []

    for match in matches:
        source_start = (region_start + match["start"])
        source_end = (region_start + match["end"])

        adjusted_matches.append(
            {
                "start": source_start,
                "end": source_end,
                "matched_text": source_text[source_start:source_end],
            }
        )

    return adjusted_matches


def find_matches_in_regions(source_text: str, regions: List[Dict[str, Any]], target_text: str) -> List[Dict[str, Any]]:
    # Search each region independently so text from separate source sections cannot be joined into one accidental match.
    matches = []

    for region in regions:
        local_matches = find_normalized_matches(region["text"],target_text)

        matches.extend(move_matches_to_source_positions(local_matches,region["start"],source_text))

    return matches


def find_matching_function(functions: List[Dict[str, Any]], function_name: str, function_signature: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    # First find functions with the expected name.
    same_name_functions = [function for function in functions if function["name"] == function_name]

    if not same_name_functions:
        return (None, "A function with the expected name was not found.")

    # Then require the normalized signature to remain unchanged.
    expected_signature = (normalize_function_signature(function_signature))

    matching_functions = [function
        for function in same_name_functions
        if (normalize_function_signature(function["signature"])== expected_signature)
    ]

    if len(matching_functions) == 1:
        return matching_functions[0], None

    if len(matching_functions) > 1:
        return (None, "More than one function with the expected name and signature was found.")

    found_signatures = [normalize_function_signature(function["signature"]) for function in same_name_functions]

    return (None,
        ("The function name was found, but its signature has changed. "
            f"Expected signature: {expected_signature}. "
            f"Found signature(s): {', '.join(found_signatures)}."
        )
    )


def build_non_function_regions(source_text: str, functions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # Build separate source regions outside function definitions.
    # Keeping the regions separate prevents code before and after a function from being treated as one continuous piece of code.
    regions = []
    region_start = 0

    for function in sorted(functions, key=lambda item: item["start"]
    ):
        region_end = function["start"]

        if region_start < region_end:
            regions.append(
                {
                    "start": region_start,
                    "end": region_end,
                    "text": source_text[region_start:region_end],
                }
            )

        region_start = function["end"]

    if region_start < len(source_text):
        regions.append(
            {
                "start": region_start,
                "end": len(source_text),
                "text": source_text[region_start:],
            }
        )

    return regions


def count_normalized_occurrences(regions: List[Dict[str, Any]], target_text: str,) -> int:
    # Use the same boundary-aware matching logic as the application stage.
    return sum(
        len(find_normalized_matches(region["text"], target_text))
        for region in regions
    )
