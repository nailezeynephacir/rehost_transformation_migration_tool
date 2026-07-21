from pathlib import Path
import json
import shutil
from typing import Any, Dict, List, Optional, Tuple

from parser import parse_source
from transformation_matching import build_non_function_regions, find_matches_in_regions, find_matching_function

PROJECT_ROOT = Path(__file__).resolve().parent

TRANSFORMATIONS_FILE = (PROJECT_ROOT / "rehost_transformations.json")

NEW_ORIGINAL_DIR = (PROJECT_ROOT / "new_original")

GENERATED_REHOST_DIR = (PROJECT_ROOT / "generated_rehost")

APPLICATION_REPORT_FILE = (PROJECT_ROOT / "application_report.txt")


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


def insert_text_at_position(source_text: str, insertion_index: int, content: str) -> str:
    # Insert a block while keeping it separated from surrounding code.
    prefix = source_text[:insertion_index]
    suffix = source_text[insertion_index:]

    text_to_insert = content.strip()

    if prefix and not prefix.endswith("\n"):
        text_to_insert = "\n" + text_to_insert

    if suffix and not suffix.startswith("\n"):
        text_to_insert = text_to_insert + "\n"

    return (prefix + text_to_insert + suffix)


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
        "parser_warnings": parser_warnings,
        "start": None,
        "end": None,
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
                "reason": ("The complete insertion content is already present in the required scope."),
                "match_count": 1,
                "start": existing_match["start"],
                "end": existing_match["end"],
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

        updated_source = insert_text_at_position(
            source_text=source_text,
            insertion_index=insertion_index,
            content=content
        )

        result.update(
            {
                "result": "APPLIED",
                "reason": (f"The insertion was applied at the {position} position."),
                "start": insertion_index,
                "end": insertion_index + len(content.strip()),
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

    if len(anchor_matches) == 0:
        result["reason"] = ("The insertion anchor was not found in the required scope.")
        return source_text, result

    if len(anchor_matches) > 1:
        result["reason"] = ("The insertion anchor was found more than once in the required scope. The insertion point is ambiguous.")
        return source_text, result

    anchor_match = anchor_matches[0]

    if position == "before":
        insertion_index = anchor_match["start"]
    else:
        insertion_index = anchor_match["end"]

    updated_source = insert_text_at_position(
        source_text=source_text,
        insertion_index=insertion_index,
        content=content
    )

    result.update(
        {
            "result": "APPLIED",
            "reason": (f"The insertion anchor was found exactly once and the content was inserted {position} it."),
            "start": insertion_index,
            "end": insertion_index + len(content.strip()),
        }
    )
    return updated_source, result


def get_transformation_function_name(transformation: Dict[str, Any]) -> Optional[str]:
    # Return the expected function name for function-scope transformations.
    function_information = transformation.get("function")

    if not isinstance(function_information,dict):
        return None

    function_name = function_information.get("name")

    if not isinstance(function_name, str):
        return None

    return function_name

## ----- This were added for occurence > 1, still do it case -----

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


def apply_replacement_to_matches(source_text: str, matches: List[Dict[str, Any]], replacement: str) -> str:
    # Apply replacements from right to left.
    # This prevents earlier character positions from changing.
    updated_source = source_text

    for match in sorted(matches, key=lambda item: item["start"],reverse=True):
        updated_source = (updated_source[:match["start"]] + replacement + updated_source[match["end"]:])

    return updated_source
## ----------------------------------------------------------------

def apply_single_transformation(source_text: str,transformation: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
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
            "start": None,
            "end": None,
        }

    transformation_id = transformation.get("id","unknown")

    regions, error, parser_warnings = (build_transformation_search_regions(source_text, transformation))

    result = {
        "transformation_id": transformation_id,
        "file": transformation.get("file"),
        "scope": transformation.get("scope"),
        "function_name": (get_transformation_function_name(transformation)),
        "expected_match": transformation.get("match", ""),
        "match_count": 0,
        "replacement_match_count": 0,
        "applied_count": 0,
        "parser_warnings": parser_warnings,
        "ranges": [],
        "start": None,
        "end": None,
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
        if not match_is_inside_replacement(match,replacement_matches)
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
                    "ranges": [
                        {
                            "start": match["start"],
                            "end": match["end"],
                        }
                        for match in replacement_matches
                    ],
                }
            )

        else:
            result["reason"] = ("The expected code was not found in the required scope.")

        return source_text, result

    # Multiple automatic replacements are currently allowed only
    # inside one verified function.
    if (len(matches_to_apply) > 1 and transformation.get("scope") != "function"):
        result["reason"] = ("The expected code was found more than once outside function scope. The match is ambiguous.")
        return source_text, result

    if matches_overlap(matches_to_apply):
        result["reason"] = ("The expected code produced overlapping matches, so the transformation was not applied.")
        return source_text, result

    updated_source = apply_replacement_to_matches(source_text,matches_to_apply,replacement)

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
            "start": matches_to_apply[0]["start"],
            "end": matches_to_apply[-1]["end"],
        }
    )

    return updated_source, result


def load_transformations(transformations_file: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    # Read and perform basic validation on the transformation JSON.
    if not transformations_file.exists():
        raise FileNotFoundError("Transformation file was not found: " f"{transformations_file}")

    try:
        transformation_data = json.loads(transformations_file.read_text(encoding="utf-8"))

    except json.JSONDecodeError as error:
        raise ValueError("Transformation file contains invalid JSON: "f"{error}") from error

    if not isinstance(transformation_data, dict):
        raise ValueError("The root of the transformation JSON must be an object.")

    transformations = transformation_data.get("transformations")

    if not isinstance(transformations, list):
        raise ValueError("The transformation JSON must contain a transformations list.")

    for index, transformation in enumerate(transformations, start=1):
        if not isinstance(transformation, dict):
            raise ValueError(f"Transformation {index} must be an object.")

        operation = transformation.get("operation", "replace")

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

        # Anchor-based insertions also require an anchor.
        if (operation == "insert" and transformation.get("position") in {"before", "after",} and "anchor" not in transformation):
            raise ValueError(f"Transformation {index} is an anchor-based insertion but does not contain an anchor.")
        
    # support_files is optional so older transformation JSON files
    # containing only transformations remain valid.
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
    return file_path.replace(
        "\\",
        "/"
    )


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
                    "reason": (f"The support file could not be created: {error}"),
                }
            )
            continue

        support_file_results.append(
            {
                "result": "CREATED",
                "file": relative_file_path,
                "reason": ("The support file was created from the content stored in the transformation JSON."),
            }
        )

    return support_file_results


def apply_transformations_to_source(source_text: str, transformations: List[Dict[str, Any]]) -> Tuple[str,List[Dict[str, Any]]]:
    # Apply transformations in their JSON order.
    # Each transformation searches the latest version of the source, including changes made by previously applied transformations.
    updated_source = source_text
    application_results = []

    for transformation in transformations:
        updated_source, result = (apply_single_transformation(updated_source, transformation))

        application_results.append(result)

    return (updated_source, application_results)


def build_file_skip_result(transformation: Dict[str, Any],reason: str) -> Dict[str, Any]:
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
        "start": None,
        "end": None,
    }


def apply_transformations_to_project(output_directory: Path,transformations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # Apply transformations to their corresponding files inside the generated project.
    grouped_transformations = (group_transformations_by_file(transformations))

    application_results = []

    for (relative_file_path, file_transformations) in grouped_transformations.items():
        output_file, path_error = (resolve_project_file(output_directory, relative_file_path))

        if output_file is None:
            for transformation in file_transformations:
                application_results.append(build_file_skip_result(transformation, path_error or "The file path is invalid."))
            continue

        if not output_file.exists():
            reason = (f"The file was not found in new_original: {relative_file_path}")

            for transformation in file_transformations:
                application_results.append(build_file_skip_result(transformation, reason))
            continue

        if not output_file.is_file():
            reason = ("The transformation path does not point to a regular file.")

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


        updated_source, file_results = (apply_transformations_to_source(source_text, file_transformations))
        output_file.write_text(updated_source,encoding=source_encoding)
        application_results.extend(file_results)

    return application_results


def indent_text(text: str, indentation: str = "    ") -> str:
    # Indent multiline source text for a readable report.
    lines = text.splitlines()
    if not lines:
        return indentation + "<empty>"
    
    return "\n".join(indentation + line for line in lines)


def save_application_report(application_results: List[Dict[str, Any]], transformation_count: int, transformed_file_count: int, output_file: Path) -> None:
    # Write a detailed report for applied and skipped transformations.
    applied_count = sum(result["result"] == "APPLIED" for result in application_results)
    skipped_count = sum(result["result"] == "SKIPPED" for result in application_results)
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
        (f"Transformations skipped: {skipped_count}"),
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

        if result["result"] == "APPLIED":
            report_lines.extend([(f"Original character range: {result['start']}:{result['end']}"), ""])

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
        return (file_path.read_text(encoding="utf-8"),"utf-8")

    except UnicodeDecodeError:
        print(f"{file_path}: utf-8 olarak okunamadı, cp1254 denendi.")
        return (file_path.read_text(encoding="cp1254"), "cp1254")


def main() -> None:
    transformations, support_files = load_transformations(TRANSFORMATIONS_FILE)

    prepare_generated_project(source_directory=NEW_ORIGINAL_DIR, output_directory=GENERATED_REHOST_DIR)

    support_file_results = apply_support_files_to_project(output_directory=GENERATED_REHOST_DIR, support_files=support_files)
    # not written in report - UPDATE
    
    application_results = (apply_transformations_to_project(output_directory=(GENERATED_REHOST_DIR), transformations=transformations))

    grouped_transformations = (group_transformations_by_file(transformations))

    save_application_report(
        application_results=application_results,
        transformation_count=len(transformations),
        transformed_file_count=len(grouped_transformations),
        output_file=APPLICATION_REPORT_FILE
    )

    print(f"\nGenerated project written to: {GENERATED_REHOST_DIR}")
    print(f"Application report written to: {APPLICATION_REPORT_FILE}")


if __name__ == "__main__":
    main()
