from typing import Any, Dict, List, Optional, Tuple

from parser import mask_comments


def normalize_code_text(text: str) -> str:
    # Ignore comments and whitespace differences while comparing code.
    #
    # Strings and character literals are preserved because their contents
    # may affect program behavior.
    text_without_comments = mask_comments(
        text
    )

    return "".join(
        text_without_comments.split()
    )


def normalize_code_with_positions(
    text: str
) -> Tuple[str, List[int]]:
    # Normalize source code while keeping a mapping back to the
    # original character positions.
    #
    # Comments and whitespace are ignored during comparison.
    # Strings and character literals are preserved.
    masked_text = mask_comments(
        text
    )

    normalized_characters = []
    original_positions = []

    for index, character in enumerate(
        masked_text
    ):
        if character.isspace():
            continue

        normalized_characters.append(
            character
        )

        original_positions.append(
            index
        )

    return (
        "".join(normalized_characters),
        original_positions
    )


def find_normalized_matches(
    source_text: str,
    target_text: str
) -> List[Dict[str, Any]]:
    # Find every normalized occurrence of target_text in source_text.
    #
    # Each result contains the real start and end character positions
    # from the original source text.
    normalized_source, source_positions = (
        normalize_code_with_positions(
            source_text
        )
    )

    normalized_target = normalize_code_text(
        target_text
    )

    if not normalized_target:
        return []

    matches = []
    search_start = 0

    while True:
        normalized_start = normalized_source.find(
            normalized_target,
            search_start
        )

        if normalized_start == -1:
            break

        normalized_end = (
            normalized_start
            + len(normalized_target)
        )

        source_start = source_positions[
            normalized_start
        ]

        source_end = (
            source_positions[
                normalized_end - 1
            ]
            + 1
        )

        matches.append(
            {
                "start": source_start,
                "end": source_end,
                "matched_text": source_text[
                    source_start:source_end
                ],
            }
        )

        # Move one normalized character forward so all possible
        # occurrences can be detected.
        search_start = normalized_start + 1

    return matches


def move_matches_to_source_positions(
    matches: List[Dict[str, Any]],
    region_start: int,
    source_text: str
) -> List[Dict[str, Any]]:
    # Convert positions relative to a search region into positions
    # relative to the complete source file.
    adjusted_matches = []

    for match in matches:
        source_start = (
            region_start
            + match["start"]
        )

        source_end = (
            region_start
            + match["end"]
        )

        adjusted_matches.append(
            {
                "start": source_start,
                "end": source_end,
                "matched_text": source_text[
                    source_start:source_end
                ],
            }
        )

    return adjusted_matches


def find_matches_in_regions(
    source_text: str,
    regions: List[Dict[str, Any]],
    target_text: str
) -> List[Dict[str, Any]]:
    # Search each region independently so text from separate source
    # sections cannot be joined into one accidental match.
    matches = []

    for region in regions:
        local_matches = find_normalized_matches(
            region["text"],
            target_text
        )

        matches.extend(
            move_matches_to_source_positions(
                local_matches,
                region["start"],
                source_text
            )
        )

    return matches


def find_matching_function(
    functions: List[Dict[str, Any]],
    function_name: str,
    function_signature: str
) -> Tuple[
    Optional[Dict[str, Any]],
    Optional[str]
]:
    # First find functions with the expected name.
    same_name_functions = [
        function
        for function in functions
        if function["name"] == function_name
    ]

    if not same_name_functions:
        return (
            None,
            "A function with the expected name was not found."
        )

    # Then require the normalized signature to remain unchanged.
    matching_functions = [
        function
        for function in same_name_functions
        if (
            function["normalized_signature"]
            == function_signature
        )
    ]

    if len(matching_functions) == 1:
        return matching_functions[0], None

    if len(matching_functions) > 1:
        return (
            None,
            "More than one function with the expected "
            "name and signature was found."
        )

    return (
        None,
        "The function name was found, but its signature "
        "has changed."
    )


def build_non_function_regions(
    source_text: str,
    functions: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    # Build separate source regions outside function definitions.
    #
    # Keeping the regions separate prevents code before and after a
    # function from being treated as one continuous piece of code.
    regions = []
    region_start = 0

    for function in sorted(
        functions,
        key=lambda item: item["start"]
    ):
        region_end = function["start"]

        if region_start < region_end:
            regions.append(
                {
                    "start": region_start,
                    "end": region_end,
                    "text": source_text[
                        region_start:region_end
                    ],
                }
            )

        region_start = function["end"]

    if region_start < len(source_text):
        regions.append(
            {
                "start": region_start,
                "end": len(source_text),
                "text": source_text[
                    region_start:
                ],
            }
        )

    return regions


def count_normalized_occurrences(
    regions: List[Dict[str, Any]],
    target_text: str
) -> int:
    # Count normalized occurrences across independent search regions.
    normalized_target = normalize_code_text(
        target_text
    )

    if not normalized_target:
        return 0

    return sum(
        normalize_code_text(
            region["text"]
        ).count(
            normalized_target
        )
        for region in regions
    )