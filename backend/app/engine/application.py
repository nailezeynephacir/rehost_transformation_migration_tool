from dataclasses import dataclass, field
from pathlib import Path
import json
import shutil
from typing import Any, Dict, List, Optional, Tuple

import os
import tempfile

from .parser import parse_source
from .transformation_matching import build_non_function_regions, find_matches_in_regions, find_matching_function


@dataclass
class ApplicationResultItem:
    transformation_id: Optional[str]
    file: str
    scope: Optional[str]
    function_name: Optional[str]
    status: str
    matched_macro: Optional[str]
    opening_line: Optional[int]
    reason: str
    original_snippet: Optional[str]
    rehost_snippet: Optional[str]
    generated_snippet: Optional[str]


@dataclass
class ApplicationSummary:
    applied: int
    skipped: int
    already_applied: int


@dataclass
class ApplicationResult:
    results: List[ApplicationResultItem] = field(default_factory=list)
    summary: ApplicationSummary = field(default_factory=lambda: ApplicationSummary(0, 0, 0))
    # Relative (posix) paths, under output_dir, of every file this run wrote -
    # the service layer's source for the per-file artifact list.
    generated_files: List[str] = field(default_factory=list)


def _line_number_for_offset(text: str, offset: int) -> int:
    # 1-based line number containing a given character offset.
    return text.count("\n", 0, offset) + 1


def prepare_generated_project(source_directory: Path, output_directory: Path) -> None:
    # Create a fresh generated project from new_original.
    # Files without transformations are copied without modification.

    if not source_directory.exists():
        raise FileNotFoundError("New original directory was not found: " f"{source_directory}")

    if not source_directory.is_dir():
        raise NotADirectoryError("New original path is not a directory: " f"{source_directory}")

    if (source_directory.resolve() == output_directory.resolve()):
        raise ValueError("The input and output directories must be different.")

    if output_directory.exists():
        shutil.rmtree(output_directory) # deletes the directory

    shutil.copytree(source_directory, output_directory)


def build_transformation_search_regions(source_text: str, transformation: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Optional[str], List[str]]:
    # Build only the source regions allowed by the transformation scope.
    parse_result = parse_source(source_text)

    functions = parse_result["functions"]
    parser_warnings = parse_result["warnings"]

    scope = transformation.get("scope")

    if scope == "function":
        function_information = transformation.get("function")

        if not isinstance(function_information, dict):
            return ([], "Function information is missing from the transformation.", parser_warnings)

        function_name = function_information.get("name")
        function_signature = function_information.get("signature")

        if (not function_name or not function_signature):
            return ([], "Function name or signature is missing from the transformation.", parser_warnings)

        matching_function, error = find_matching_function(functions, function_name, function_signature)

        if matching_function is None:
            return ([], error, parser_warnings)

        # Search only inside the function body.
        body_start = (matching_function["body_start"] + 1)
        body_end = (matching_function["body_end"] - 1)

        return (
            [
                {
                    "start": body_start,
                    "end": body_end,
                    "text": source_text[body_start:body_end],
                }
            ],
            None,
            parser_warnings
        )

    if scope in {"include", "global"}:
        return (
            build_non_function_regions(source_text, functions),
            None,
            parser_warnings
        )

    return (
        [],
        f"Unsupported transformation scope: {scope}",
        parser_warnings
    )


def insert_text_at_position(source_text: str, insertion_index: int, content: str) -> Tuple[str, int, int]:
    # Insert a block while keeping it separated from surrounding code.
    prefix = source_text[:insertion_index]
    suffix = source_text[insertion_index:]

    text_to_insert = content.strip("\r\n")

    if prefix and not prefix.endswith("\n"):
        text_to_insert = "\n" + text_to_insert

    if suffix and not suffix.startswith("\n"):
        text_to_insert = text_to_insert + "\n"

    updated_source = prefix + text_to_insert + suffix

    return (updated_source, insertion_index, insertion_index + len(text_to_insert),)


def apply_insertion_transformation(source_text: str, transformation: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    # Apply a positional insertion only when its scope and insertion point can be identified safely.
    transformation_id = transformation.get("id", "unknown")

    regions, error, parser_warnings = (build_transformation_search_regions(source_text, transformation))

    content = transformation.get("content")
    position = transformation.get("position")
    anchor = transformation.get("anchor")

    result = {
        "transformation_id": transformation_id,
        "file": transformation.get("file"),
        "scope": transformation.get("scope"),
        "function_name": (get_transformation_function_name(transformation)),
        "expected_match": (anchor if isinstance(anchor, str) else ""),
        "result": "SKIPPED",
        "reason": "",
        "match_count": 0,
        "fallback_match_count": 0,
        "parser_warnings": parser_warnings,
        "applied_count": 0,
        "ranges": [],
        "opening_line": None,
    }

    # Parser warnings mean that function and non-function boundaries may be unreliable.
    if parser_warnings:
        result["reason"] = ("The source produced parser warnings, so the insertion was not applied.")
        return source_text, result

    if error is not None:
        result["reason"] = error
        return source_text, result

    if not isinstance(content, str) or not content.strip():
        result["reason"] = ("The insertion does not contain valid content.")
        return source_text, result

    # Check whether the complete conditional block is already present in the required scope. This keeps repeated application idempotent.
    content_matches = find_matches_in_regions(source_text, regions, content)

    if len(content_matches) == 1:
        existing_match = content_matches[0]

        result.update(
            {
                "result": "ALREADY_APPLIED",
                "reason": "The complete insertion content is already present in the required scope.",
                "match_count": 0,
                "applied_count": 0,
                "ranges": [
                    {
                        "start": existing_match["start"],
                        "end": existing_match["end"],
                    }
                ],
                "opening_line": _line_number_for_offset(source_text, existing_match["start"]),
            }
        )

        return source_text, result

    if len(content_matches) > 1:
        result.update(
            {
                "reason": "The complete insertion content was found more than once in the required scope. The existing code is ambiguous.",
                "match_count": len(content_matches),
            }
        )

        return source_text, result

    # Function-boundary insertions do not use an anchor.
    if position in {"function_start", "function_end"}:
        if transformation.get("scope") != "function":
            result["reason"] = (f"The {position} position can only be used with function-scope transformations.")
            return source_text, result

        if len(regions) != 1:
            result["reason"] = ("A unique function body region could not be identified.")
            return source_text, result

        function_region = regions[0]

        if position == "function_start":
            insertion_index = function_region["start"]
        else:
            insertion_index = function_region["end"]

        updated_source, inserted_start, inserted_end = insert_text_at_position(
            source_text=source_text,
            insertion_index=insertion_index,
            content=content,
        )

        result.update(
            {
                "result": "APPLIED",
                "reason": (f"The insertion was applied at the {position} position."),
                "applied_count": 1,
                "ranges": [
                    {
                        "start": inserted_start,
                        "end": inserted_end,
                    }
                ],
                "opening_line": _line_number_for_offset(source_text, inserted_start),
            }
        )
        return updated_source, result

    # Anchor-based insertions require exactly one anchor match.
    if position not in {"before", "after"}:
        result["reason"] = (f"Unsupported insertion position: {position}")
        return source_text, result

    if not isinstance(anchor, str) or not anchor.strip():
        result["reason"] = ("The anchor-based insertion does not contain a valid anchor.")
        return source_text, result

    anchor_matches = find_matches_in_regions(source_text, regions, anchor)

    result["match_count"] = len(anchor_matches)

    used_position = position
    used_anchor = anchor
    used_fallback = False

    if len(anchor_matches) == 0:
        fallback_position = transformation.get("fallback_position")
        fallback_anchor = transformation.get("fallback_anchor")

        fallback_is_valid = (
            fallback_position in {"before", "after"}
            and isinstance(fallback_anchor, str)
            and fallback_anchor.strip()
        )

        if not fallback_is_valid:
            result["reason"] = ("The primary insertion anchor was not found in the required scope and no valid fallback anchor is available.")
            return source_text, result

        fallback_matches = find_matches_in_regions(source_text, regions, fallback_anchor)
        result["fallback_match_count"] = len(fallback_matches)

        if len(fallback_matches) == 0:
            result["reason"] = ("Neither the primary insertion anchor nor the fallback anchor was found in the required scope.")
            return source_text, result

        if len(fallback_matches) > 1:
            result["reason"] = ("The primary insertion anchor was not found and the fallback anchor was found more than once. The insertion point is ambiguous.")
            return source_text, result

        anchor_matches = fallback_matches
        used_position = fallback_position
        used_anchor = fallback_anchor
        used_fallback = True

    elif len(anchor_matches) > 1:
        result["reason"] = ("The primary insertion anchor was found more than once in the required scope. The insertion point is ambiguous.")
        return source_text, result

    anchor_match = anchor_matches[0]

    if used_position == "before":
        anchor_match = include_leading_indentation(source_text, anchor_match,)
        insertion_index = anchor_match["start"]
    else:
        insertion_index = anchor_match["end"]

    updated_source, inserted_start, inserted_end = insert_text_at_position(
        source_text=source_text,
        insertion_index=insertion_index,
        content=content,
    )

    result.update(
        {
            "result": "APPLIED",
            "reason": (
                f"The primary anchor was not found, so the fallback anchor was used and the content was inserted {used_position} it."
                if used_fallback
                else
                f"The primary insertion anchor was found exactly once and the content was inserted {used_position} it."),
            "used_anchor": used_anchor,
            "used_position": used_position,
            "used_fallback": used_fallback,
            "applied_count": 1,
            "ranges": [
                {
                    "start": inserted_start,
                    "end": inserted_end,
                }
            ],
            "opening_line": _line_number_for_offset(source_text, inserted_start),
        }
    )
    return updated_source, result


def get_transformation_function_name(transformation: Dict[str, Any]) -> Optional[str]:
    # Return the expected function name for function-scope transformations.
    function_information = transformation.get("function")

    if not isinstance(function_information, dict):
        return None

    function_name = function_information.get("name")

    if not isinstance(function_name, str):
        return None

    return function_name


def match_is_inside_replacement(match: Dict[str, Any], replacement_matches: List[Dict[str, Any]]) -> bool:
    # An original-code match may be located inside an already-applied conditional replacement.
    # Ignore it to prevent nested conditionals.
    return any(replacement_match["start"] <= match["start"] and match["end"] <= replacement_match["end"] for replacement_match in replacement_matches)


def matches_overlap(matches: List[Dict[str, Any]]) -> bool:
    # Multiple matches are safe only when their source ranges do not overlap.
    ordered_matches = sorted(matches, key=lambda match: match["start"])

    for previous_match, current_match in zip(ordered_matches, ordered_matches[1:]):
        if current_match["start"] < previous_match["end"]:
            return True

    return False


def include_leading_indentation(source_text: str, match: Dict[str, Any],) -> Dict[str, Any]:
    # Include indentation before a match when it is the first meaningful content on its line.
    match_start = match["start"]

    newline_start = source_text.rfind("\n", 0, match_start)
    carriage_return_start = source_text.rfind("\r", 0, match_start)

    line_start = max(newline_start, carriage_return_start,) + 1

    leading_text = source_text[line_start:match_start]

    if leading_text.strip():
        return match

    return {
        **match,
        "start": line_start,
        "matched_text": source_text[line_start:match["end"]],
    }


def apply_replacement_to_matches(source_text: str, matches: List[Dict[str, Any]], replacement: str) -> str:
    # Apply replacements from right to left.
    # This prevents earlier character positions from changing.
    updated_source = source_text

    for match in sorted(matches, key=lambda item: item["start"], reverse=True):
        updated_source = (updated_source[:match["start"]] + replacement + updated_source[match["end"]:])

    return updated_source


def apply_single_transformation(source_text: str, transformation: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    # Apply one transformation only when exactly one safe match exists.
    # The original source is returned unchanged when the transformation cannot be applied safely or is already present.
    operation = transformation.get("operation", "replace")

    if operation == "insert":
        return apply_insertion_transformation(source_text=source_text, transformation=transformation)

    if operation != "replace":
        transformation_id = transformation.get("id", "unknown")

        return source_text, {
            "transformation_id": transformation_id,
            "file": transformation.get("file"),
            "scope": transformation.get("scope"),
            "function_name": (get_transformation_function_name(transformation)),
            "expected_match": "",
            "result": "SKIPPED",
            "reason": (f"Unsupported transformation operation: {operation}"),
            "match_count": 0,
            "parser_warnings": [],
            "applied_count": 0,
            "ranges": [],
            "opening_line": None,
        }

    transformation_id = transformation.get("id", "unknown")

    regions, error, parser_warnings = (build_transformation_search_regions(source_text, transformation))

    result = {
        "transformation_id": transformation_id,
        "file": transformation.get("file"),
        "scope": transformation.get("scope"),
        "function_name": (get_transformation_function_name(transformation)),
        "expected_match": transformation.get("match", ""),
        "result": "SKIPPED",
        "reason": "",
        "match_count": 0,
        "replacement_match_count": 0,
        "applied_count": 0,
        "parser_warnings": parser_warnings,
        "ranges": [],
        "opening_line": None,
    }

    # Parser warnings mean that source boundaries may be unreliable.
    if parser_warnings:
        result["reason"] = ("The source produced parser warnings, so the transformation was not applied.")
        return source_text, result

    if error is not None:
        result["reason"] = error
        return source_text, result

    replacement = transformation.get("replacement")

    if not isinstance(replacement, str):
        result["reason"] = ("The transformation does not contain a valid replacement string.")
        return source_text, result

    replacement_matches = find_matches_in_regions(source_text, regions, replacement)

    result["replacement_match_count"] = len(replacement_matches)

    # Then locate every occurrence of the old original code.
    original_matches = find_matches_in_regions(source_text, regions, transformation.get("match", ""))

    # The original branch also exists inside a complete conditional block.
    # Exclude such matches to avoid creating nested #ifdef blocks.
    matches_to_apply = [
        match
        for match in original_matches
        if not match_is_inside_replacement(match, replacement_matches)
    ]

    result["match_count"] = len(matches_to_apply)

    if not matches_to_apply:
        if replacement_matches:
            result.update(
                {
                    "result": "ALREADY_APPLIED",
                    "reason": ("No untransformed matches remain in the required scope. "
                         f"The complete replacement is already present {len(replacement_matches)} time(s)."
                    ),
                    "match_count": 0,
                    "applied_count": 0,
                        "ranges": [
                            {
                                "start": match["start"],
                                "end": match["end"],
                            }
                            for match in replacement_matches
                        ],
                    "opening_line": _line_number_for_offset(
                        source_text, min(match["start"] for match in replacement_matches)
                    ),
                }
            )

        else:
            result["reason"] = ("The expected code was not found in the required scope.")

        return source_text, result

    # Include the indentation at the beginning of matched lines.
    matches_to_apply = [
        include_leading_indentation(source_text, match)
        for match in matches_to_apply
    ]

    # Sibling team decision (2026-07-28), resolving the prior OPEN QUESTION:
    # multiple untransformed matches are ambiguous in every scope, including
    # function scope - matches the naming/intent of the sibling team's own
    # 06_skipped_multiple_matches fixture, and the "exactly one safe match"
    # principle apply_single_transformation() is built around. This mirrors
    # the same removed exception on the extraction side.
    if len(matches_to_apply) > 1:
        result["reason"] = ("The expected code was found more than once in the required scope. The match is ambiguous.")
        return source_text, result

    if matches_overlap(matches_to_apply):
        result["reason"] = ("The expected code produced overlapping matches, so the transformation was not applied.")
        return source_text, result

    updated_source = apply_replacement_to_matches(source_text, matches_to_apply, replacement)

    applied_ranges = [
        {
            "start": match["start"],
            "end": match["end"],
        }
        for match in matches_to_apply
    ]

    result.update(
        {
            "result": "APPLIED",
            "reason": (
                "The expected code was found "
                f"{len(matches_to_apply)} time(s) "
                "in the required scope. "
                "All matches were transformed."
            ),
            "applied_count": len(matches_to_apply),
            "ranges": applied_ranges,
            "opening_line": _line_number_for_offset(
                source_text, min(match["start"] for match in matches_to_apply)
            ),
        }
    )

    return updated_source, result


def require_non_empty_string(value: Any, field_name: str, transformation_index: int,) -> str:
    # Validate required textual transformation fields.
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Transformation {transformation_index} must contain a non-empty string {field_name}.")

    return value


def load_transformations(transformations_file: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    # Read and perform basic validation on the transformation JSON.
    if not transformations_file.exists():
        raise FileNotFoundError("Transformation file was not found: " f"{transformations_file}")

    try:
        transformation_data = json.loads(transformations_file.read_text(encoding="utf-8"))

    except json.JSONDecodeError as error:
        raise ValueError("Transformation file contains invalid JSON: " f"{error}") from error

    if not isinstance(transformation_data, dict):
        raise ValueError("The root of the transformation JSON must be an object.")

    transformations = transformation_data.get("transformations")

    if not isinstance(transformations, list):
        raise ValueError("The transformation JSON must contain a transformations list.")

    for index, transformation in enumerate(transformations, start=1):
        if not isinstance(transformation, dict):
            raise ValueError(f"Transformation {index} must be an object.")

        operation = transformation.get("operation", "replace")

        if not isinstance(operation, str):
            raise ValueError(f"Transformation {index} must contain a string operation.")

        if operation not in {"replace", "insert"}:
            raise ValueError(f"Transformation {index} contains an unsupported operation: {operation}")

        # These fields are required for every transformation type.
        required_fields = {"id", "file", "scope",}

        if operation == "replace":
            required_fields.update({"match", "replacement",})

        elif operation == "insert":
            required_fields.update({"position", "content",})

        else:
            raise ValueError(f"Transformation {index} contains an unsupported operation: {operation}")

        missing_fields = (required_fields - transformation.keys())

        if missing_fields:
            missing_text = ", ".join(sorted(missing_fields))
            raise ValueError(f"Transformation {index} is missing required fields: {missing_text}")

        # Validate fields shared by every transformation.
        require_non_empty_string(transformation.get("id"), "id", index,)
        require_non_empty_string(transformation.get("file"), "file", index,)

        scope = require_non_empty_string(transformation.get("scope"), "scope", index,)

        if scope not in {"function", "include", "global"}:
            raise ValueError(f"Transformation {index} contains an unsupported scope: {scope}")

        # Function information is required for function-scope transformations.
        if scope == "function":
            function_information = transformation.get("function")

            if not isinstance(function_information, dict):
                raise ValueError(f"Transformation {index} uses function scope but does not contain a valid function object.")

            require_non_empty_string(function_information.get("name"), "function.name", index,)
            require_non_empty_string(function_information.get("signature"), "function.signature", index,)

        if operation == "replace":
            require_non_empty_string(transformation.get("match"), "match", index,)
            require_non_empty_string(transformation.get("replacement"), "replacement", index,)

            continue

        # Validate insertion-specific fields.
        position = require_non_empty_string(transformation.get("position"), "position", index,)

        if position not in {"before", "after", "function_start", "function_end",}:
            raise ValueError(f"Transformation {index} contains an unsupported insertion position: {position}")

        require_non_empty_string(transformation.get("content"), "content", index,)

        if position in {"function_start", "function_end"}:
            if scope != "function":
                raise ValueError(f"Transformation {index} uses the {position} position, which requires function scope.")

        if position in {"before", "after"}:
            require_non_empty_string(transformation.get("anchor"), "anchor", index,)

        fallback_position = transformation.get("fallback_position")
        fallback_anchor = transformation.get("fallback_anchor")

        # Fallback position and anchor must either both exist or both be absent.
        if (fallback_position is None) != (fallback_anchor is None):
            raise ValueError(f"Transformation {index} must contain both fallback_position and fallback_anchor.")

        if fallback_position is not None:
            if fallback_position not in {"before", "after"}:
                raise ValueError(f"Transformation {index} contains an unsupported fallback position: {fallback_position}")

            require_non_empty_string(fallback_anchor, "fallback_anchor", index,)

    # support_files is optional so older transformation JSON files containing only transformations remain valid.
    support_files = transformation_data.get("support_files", [])

    if not isinstance(support_files, list):
        raise ValueError("The support_files value must be a list.")

    normalized_support_paths = set()

    for index, support_file in enumerate(support_files, start=1):
        if not isinstance(support_file, dict):
            raise ValueError(f"Support file {index} must be an object.")

        missing_fields = ({"path", "content"} - support_file.keys())

        if missing_fields:
            missing_text = ", ".join(sorted(missing_fields))
            raise ValueError(
                f"Support file {index} is missing "
                f"required fields: {missing_text}"
            )

        path = support_file.get("path")
        content = support_file.get("content")

        if (not isinstance(path, str) or not path.strip()):
            raise ValueError(f"Support file {index} must contain a non-empty string path.")

        if not isinstance(content, str):
            raise ValueError(f"Support file {index} must contain string content.")

        normalized_path = (normalize_relative_file_path(path))

        if normalized_path in normalized_support_paths:
            raise ValueError(f"The support_files list contains the same path more than once: {normalized_path}")

        normalized_support_paths.add(normalized_path)

    return transformations, support_files


def normalize_relative_file_path(file_path: str) -> str:
    # Use one consistent separator when comparing JSON file paths.
    return file_path.replace("\\", "/")


def group_transformations_by_file(transformations: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    # Group transformations by their normalized relative file path.
    grouped_transformations = {}

    for transformation in transformations:
        relative_file_path = (normalize_relative_file_path(str(transformation.get("file", ""))))

        grouped_transformations.setdefault(relative_file_path, []).append(transformation)

    return grouped_transformations


def resolve_project_file(project_directory: Path, relative_file_path: str) -> Tuple[Optional[Path], Optional[str]]:
    # Resolve a JSON file path without allowing it to leave the project directory.
    normalized_path = (normalize_relative_file_path(relative_file_path))
    relative_path = Path(normalized_path)

    if relative_path.is_absolute():
        return (None, "The transformation contains an absolute file path.")

    if ".." in relative_path.parts:
        return (None, "The transformation file path leaves the project directory.")

    project_directory_resolved = (project_directory.resolve())
    resolved_file = (project_directory / relative_path).resolve()

    try:
        resolved_file.relative_to(project_directory_resolved)

    except ValueError:
        return (None, "The transformation file path leaves the project directory.")

    return resolved_file, None


def apply_support_files_to_project(output_directory: Path, support_files: List[Dict[str, str]]) -> List[Dict[str, str]]:
    # Create rehost-only support files from the content stored in JSON.
    # Existing files copied from new_original are not overwritten.
    support_file_results = []

    for support_file in support_files:
        relative_file_path = normalize_relative_file_path(support_file["path"])

        content = support_file["content"]

        output_file, path_error = resolve_project_file(output_directory, relative_file_path)

        if output_file is None:
            support_file_results.append(
                {
                    "result": "SKIPPED",
                    "file": relative_file_path,
                    "reason": (path_error or "The support file path is invalid."),
                }
            )
            continue

        # new_original is copied before support files are created.
        # Therefore, an existing path belongs to new_original and should not be overwritten silently.
        if output_file.exists():
            support_file_results.append(
                {
                    "result": "SKIPPED",
                    "file": relative_file_path,
                    "reason": ("A file with the same path already exists in new_original, so it was not overwritten."),
                }
            )
            continue

        try:
            # Support files may be inside nested directories.
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # write_bytes preserves the line endings stored in the JSON.
            output_file.write_bytes(content.encode("utf-8"))

        except (OSError, UnicodeEncodeError) as error:
            support_file_results.append(
                {
                    "result": "SKIPPED",
                    "file": relative_file_path,
                    "reason": f"The support file could not be created: {error}",
                }
            )
            continue

        support_file_results.append(
            {
                "result": "CREATED",
                "file": relative_file_path,
                "reason": "The support file was created from the content stored in the transformation JSON.",
            }
        )

    return support_file_results


def apply_transformations_to_source(source_text: str, transformations: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
    # Apply transformations in their JSON order.
    # Each transformation searches the latest version of the source, including changes made by previously applied transformations.
    updated_source = source_text
    application_results = []

    for transformation in transformations:
        updated_source, result = (apply_single_transformation(updated_source, transformation))

        application_results.append(result)

    return (updated_source, application_results)


def build_file_skip_result(transformation: Dict[str, Any], reason: str) -> Dict[str, Any]:
    # Create a standard result when a source file cannot be processed.
    return {
        "transformation_id": transformation.get("id", "unknown"),
        "file": transformation.get("file"),
        "scope": transformation.get("scope"),
        "function_name": (get_transformation_function_name(transformation)),
        "expected_match": transformation.get(
            "match",
            ""
        ),
        "result": "SKIPPED",
        "reason": reason,
        "match_count": 0,
        "replacement_match_count": 0,
        "applied_count": 0,
        "parser_warnings": [],
        "ranges": [],
        "opening_line": None,
    }


def write_source_atomically(output_file: Path, source_text: str, source_encoding: str,) -> None:
    # Encode completely before opening or modifying any file.
    encoded_source = source_text.encode(source_encoding)
    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=output_file.parent,
            prefix=f".{output_file.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)

            temporary_file.write(encoded_source)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        # Replace the destination only after the temporary file has been written successfully.
        os.replace(temporary_path, output_file)

    except Exception:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass

        raise


def mark_unwritten_results_as_skipped(file_results: List[Dict[str, Any]], reason: str,) -> None:
    # Results calculated from an in-memory source are not considered successful when the final file cannot be written.
    for result in file_results:
        if result.get("result") not in {"APPLIED", "ALREADY_APPLIED",}:
            continue

        result.update(
            {
                "result": "SKIPPED",
                "reason": reason,
                "applied_count": 0,
                "ranges": [],
            }
        )


def apply_transformations_to_project(output_directory: Path, transformations: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    # Apply transformations to their corresponding files inside the generated project.
    # Returns the per-transformation results plus the relative paths of files
    # actually rewritten on disk (needed by the service layer's artifact list).
    grouped_transformations = (group_transformations_by_file(transformations))

    application_results = []
    modified_files: List[str] = []

    for (relative_file_path, file_transformations) in grouped_transformations.items():
        output_file, path_error = (resolve_project_file(output_directory, relative_file_path))

        if output_file is None:
            for transformation in file_transformations:
                application_results.append(build_file_skip_result(transformation, path_error or "The file path is invalid."))
            continue

        if not output_file.exists():
            reason = f"The file was not found in new_original: {relative_file_path}"

            for transformation in file_transformations:
                application_results.append(build_file_skip_result(transformation, reason))
            continue

        if not output_file.is_file():
            reason = "The transformation path does not point to a regular file."

            for transformation in file_transformations:
                application_results.append(build_file_skip_result(transformation, reason))
            continue

        try:
            source_text, source_encoding = read_source_with_encoding(output_file)

        except UnicodeDecodeError:
            reason = ("The file could not be read as UTF-8 or cp1254 text.")
            for transformation in file_transformations:
                application_results.append(build_file_skip_result(transformation, reason))
            continue

        updated_source, file_results = (apply_transformations_to_source(source_text, file_transformations,))

        # Do not rewrite a file when no transformation changed its content.
        if updated_source == source_text:
            application_results.extend(file_results)
            continue

        try:
            write_source_atomically(output_file, updated_source, source_encoding,)
            modified_files.append(relative_file_path)

        except UnicodeEncodeError as error:
            reason = (
                f"The transformed source could not be encoded as {source_encoding}. No changes were written: {error}")

            mark_unwritten_results_as_skipped(file_results, reason,)

        except OSError as error:
            reason = (
                f"The transformed source could not be written safely. No changes were written: {error}")

            mark_unwritten_results_as_skipped(file_results, reason,)

        application_results.extend(file_results)

    return application_results, modified_files


def indent_text(text: str, indentation: str = "    ") -> str:
    # Indent multiline source text for a readable report.
    lines = text.splitlines()
    if not lines:
        return indentation + "<empty>"

    return "\n".join(indentation + line for line in lines)


def save_application_report(application_results: List[Dict[str, Any]], support_file_results: List[Dict[str, str]], transformation_count: int, transformed_file_count: int, output_file: Path) -> None:
    # Write a detailed report for applied and skipped transformations.
    applied_count = sum(result["result"] == "APPLIED" for result in application_results)
    already_applied_count = sum(result["result"] == "ALREADY_APPLIED" for result in application_results)
    skipped_count = sum(result["result"] == "SKIPPED" for result in application_results)

    created_support_file_count = sum(result["result"] == "CREATED" for result in support_file_results)
    skipped_support_file_count = sum(result["result"] == "SKIPPED" for result in support_file_results)

    warning_count = sum(len(result.get("parser_warnings", [])) for result in application_results)

    report_lines = [
        "REHOST TRANSFORMATION APPLICATION REPORT",
        "=" * 40,
        "",
        "SUMMARY",
        "-------",
        (f"Files containing transformations: {transformed_file_count}"),
        (f"Transformations loaded: {transformation_count}"),
        (f"Transformations applied: {applied_count}"),
        (f"Transformations already applied: {already_applied_count}"),
        (f"Transformations skipped: {skipped_count}"),
        (f"Support files loaded: {len(support_file_results)}"),
        (f"Support files created: {created_support_file_count}"),
        (f"Support files skipped: {skipped_support_file_count}"),
        (f"Parser warnings: {warning_count}"),
        ""
    ]

    if not application_results:
        report_lines.extend(
            [
                "No transformations were available.",
                ""
            ]
        )

    report_lines.extend(
        [
            "SUPPORT FILE RESULTS",
            "--------------------",
            "",
        ]
    )

    if not support_file_results:
        report_lines.extend(["No support files were available.", "",])

    for support_result in support_file_results:
        report_lines.extend(
            [
                f"[{support_result['result']}]",
                f"File: {support_result['file']}",
                f"Reason: {support_result['reason']}",
                "",
            ]
        )

    report_lines.extend(
        [
            "TRANSFORMATION RESULTS",
            "----------------------",
            "",
        ]
    )

    for result in application_results:
        report_lines.extend(
            [
                f"[{result['result']}]",
                (f"Transformation: {result['transformation_id']}"),
                f"File: {result['file']}",
                f"Scope: {result['scope']}"
            ]
        )

        function_name = result.get("function_name")

        if function_name is not None:
            report_lines.append(f"Function: {function_name}")

        reason = result.get("reason")
        if reason:
            report_lines.append(f"Reason: {reason}")

        if result["result"] == "APPLIED":
            report_lines.append(f"Applied occurrence count: {result.get('applied_count', 0)}")

            applied_ranges = result.get("ranges", [])

            for range_number, character_range in enumerate(applied_ranges, start=1):
                report_lines.append(
                    "Original character range "
                    f"{range_number}: "
                    f"{character_range['start']}:"
                    f"{character_range['end']}"
                )

            report_lines.append("")

        else:
            expected_match = str(result.get("expected_match", ""))

            report_lines.extend(
                [
                    "Expected code:",
                    indent_text(expected_match),
                    ""
                ]
            )

        parser_warnings = result.get("parser_warnings", [])
        if parser_warnings:
            report_lines.append("Parser warnings:")

            for warning in parser_warnings:
                report_lines.append(f"    - {warning}")
            report_lines.append("")

    output_file.write_text("\n".join(report_lines), encoding="utf-8")


def read_source_with_encoding(file_path: Path) -> Tuple[str, str]:
    try:
        return (file_path.read_text(encoding="utf-8"), "utf-8")

    except UnicodeDecodeError:
        # (Print statement that used to live here removed - the engine must
        # stay run-unaware, it never logs to stdout.)
        return (file_path.read_text(encoding="cp1254"), "cp1254")


_STATUS_MAP = {
    "APPLIED": "Applied",
    "ALREADY_APPLIED": "Already Applied",
    "SKIPPED": "Skipped",
}


def _to_application_result_item(result: Dict[str, Any], transformation_lookup: Dict[str, Dict[str, Any]]) -> ApplicationResultItem:
    transformation = transformation_lookup.get(result.get("transformation_id"), {})
    operation = transformation.get("operation", "replace")

    if operation == "replace":
        original_snippet = transformation.get("match") or None
        snippet = transformation.get("replacement") or None
    else:
        original_snippet = transformation.get("anchor") or None
        snippet = transformation.get("content") or None

    status = _STATUS_MAP.get(result["result"], "Skipped")

    return ApplicationResultItem(
        transformation_id=result.get("transformation_id"),
        file=result.get("file"),
        scope=result.get("scope"),
        function_name=result.get("function_name"),
        status=status,
        # Apply never re-derives target-macro status - extraction already
        # decided that, and application only replays it.
        matched_macro=None,
        opening_line=result.get("opening_line"),
        reason=result.get("reason", ""),
        original_snippet=original_snippet,
        rehost_snippet=snippet,
        generated_snippet=snippet if status in {"Applied", "Already Applied"} else None,
    )


def _build_application_summary(application_results: List[Dict[str, Any]]) -> ApplicationSummary:
    applied = sum(1 for result in application_results if result["result"] == "APPLIED")
    already_applied = sum(1 for result in application_results if result["result"] == "ALREADY_APPLIED")
    skipped = sum(1 for result in application_results if result["result"] == "SKIPPED")
    return ApplicationSummary(applied=applied, skipped=skipped, already_applied=already_applied)


def apply_transformations(
    new_original_dir: Path,
    transformations_file: Path,
    output_dir: Path,
    report_path: Path,
) -> ApplicationResult:
    transformations, support_files = load_transformations(transformations_file)

    prepare_generated_project(source_directory=new_original_dir, output_directory=output_dir)

    support_file_results = apply_support_files_to_project(output_directory=output_dir, support_files=support_files)

    application_results, modified_files = apply_transformations_to_project(
        output_directory=output_dir, transformations=transformations
    )

    grouped_transformations = group_transformations_by_file(transformations)

    save_application_report(
        application_results=application_results,
        support_file_results=support_file_results,
        transformation_count=len(transformations),
        transformed_file_count=len(grouped_transformations),
        output_file=report_path
    )

    transformation_lookup = {t["id"]: t for t in transformations if isinstance(t.get("id"), str)}

    created_support_paths = [
        entry["file"] for entry in support_file_results if entry["result"] == "CREATED"
    ]
    generated_files = sorted(set(modified_files) | set(created_support_paths))

    return ApplicationResult(
        results=[_to_application_result_item(result, transformation_lookup) for result in application_results],
        summary=_build_application_summary(application_results),
        generated_files=generated_files,
    )