from pathlib import Path
import json
import argparse
from typing import Any, Dict, List, Optional, Tuple

from parser import parse_file
from transformation_matching import (
    build_non_function_regions,
    count_normalized_occurrences,
    find_matching_function,
    normalize_code_text,
)


PROJECT_ROOT = Path(__file__).resolve().parent

ORIGINAL_DIR = (
    PROJECT_ROOT
    / "original"
)

REHOST_DIR = (
    PROJECT_ROOT
    / "rehost"
)

SUPPORTED_SOURCE_EXTENSIONS = {
    ".c",
    ".h",
    ".cc",
    ".cpp",
    ".cxx",
    ".hh",
    ".hpp",
    ".hxx",
}

TRANSFORMATIONS_FILE = (
    PROJECT_ROOT
    / "rehost_transformations.json"
)

EXTRACTION_REPORT_FILE = (
    PROJECT_ROOT
    / "extraction_report.txt"
)


def read_source_file(file_path: Path) -> str:
    # Read one source file as UTF-8 text.
    if not file_path.exists():
        raise FileNotFoundError(
            f"Source file was not found: {file_path}"
        )

    return file_path.read_text(
        encoding="utf-8"
    )

def find_source_files(source_directory: Path) -> Dict[str, Path]:
    # Find supported C and C++ files recursively.
    #
    # Files are indexed by their relative POSIX-style paths so matching
    # files in original and rehost can be paired reliably.
    if not source_directory.exists():
        raise FileNotFoundError(
            "Source directory was not found: "
            f"{source_directory}"
        )

    if not source_directory.is_dir():
        raise NotADirectoryError(
            "Source path is not a directory: "
            f"{source_directory}"
        )

    source_files = {}

    for file_path in source_directory.rglob("*"):
        if not file_path.is_file():
            continue

        if (
            file_path.suffix.lower()
            not in SUPPORTED_SOURCE_EXTENSIONS
        ):
            continue

        relative_file_path = (
            file_path.relative_to(
                source_directory
            ).as_posix()
        )

        source_files[
            relative_file_path
        ] = file_path

    return source_files


def get_original_search_regions(
    block: Dict[str, Any],
    original_source: str,
    original_functions: List[Dict[str, Any]]
) -> Tuple[
    Optional[List[Dict[str, Any]]],
    Optional[str]
]:
    # Function transformations must be verified only inside
    # the matching function.
    if block["scope"] == "function":
        function_name = block["function_name"]
        function_signature = block[
            "function_signature"
        ]

        if (
            function_name is None
            or function_signature is None
        ):
            return (
                None,
                "Function information is missing."
            )

        matching_function, error = find_matching_function(
            original_functions,
            function_name,
            function_signature
        )

        if matching_function is None:
            return None, error

        # Search only inside the function body.
        body_start = (
            matching_function["body_start"] + 1
        )

        body_end = (
            matching_function["body_end"] - 1
        )

        return (
            [
                {
                    "start": body_start,
                    "end": body_end,
                    "text": original_source[
                        body_start:body_end
                    ],
                }
            ],
            None
        )

    # Include and global transformations must be searched
    # only outside functions. Separate regions prevent code on
    # opposite sides of a function from becoming one false match.
    if block["scope"] in {
        "include",
        "global"
    }:
        return (
            build_non_function_regions(
                original_source,
                original_functions
            ),
            None
        )

    return (
        None,
        f"Unsupported scope: {block['scope']}"
    )


def build_transformation(
    transformation_number: int,
    relative_file_path: str,
    block: Dict[str, Any]
) -> Dict[str, Any]:
    # Store only information required by apply_transformations.py.
    transformation = {
        "id": (
            f"conditional_"
            f"{transformation_number}"
        ),
        "file": relative_file_path,
        "scope": block["scope"],
        "match": (
            block["original_branch"].strip()
        ),
        "replacement": (
            block["full_text"].strip()
        )
    }

    # Function information is required only for function-scope
    # transformations.
    if block["scope"] == "function":
        transformation["function"] = {
            "name": block["function_name"],
            "signature": (
                block["function_signature"]
            )
        }

    return transformation


def build_report_entry(
    relative_file_path: str,
    block: Dict[str, Any],
    result: str,
    reason: str,
    transformation_id: Optional[str] = None
) -> Dict[str, Any]:
    # Keep extraction details outside the transformation JSON.
    return {
        "result": result,
        "transformation_id": transformation_id,
        "file": relative_file_path,
        "scope": block["scope"],
        "function_name": (
            block["function_name"]
        ),
        "opening_line": (
            block["opening_line_number"]
        ),
        "match_text": (
            block["original_branch"].strip()
        ),
        "reason": reason
    }


def extract_transformations(
    original_source: str,
    original_parse_result: Dict[str, Any],
    rehost_parse_result: Dict[str, Any],
    relative_file_path: str,
    starting_transformation_number: int
) -> Tuple[
    List[Dict[str, Any]],
    List[Dict[str, Any]]
]:
    # Verify each conditional block from the old rehost file
    # against the old original file.
    transformations = []
    report_entries = []

    original_functions = (
        original_parse_result["functions"]
    )

    conditional_blocks = (
        rehost_parse_result[
            "conditional_blocks"
        ]
    )

    parser_warnings = (
        original_parse_result["warnings"]
        + rehost_parse_result["warnings"]
    )

    # Parser warnings mean that source boundaries may be unreliable.
    # Skip every block from the file instead of producing transformations
    # from partially parsed input.
    if parser_warnings:
        for block in conditional_blocks:
            report_entries.append(
                build_report_entry(
                    relative_file_path,
                    block,
                    result="SKIPPED",
                    reason=(
                        "The file produced parser warnings, so no "
                        "transformation was extracted from this block."
                    )
                )
            )

        return transformations, report_entries

    for block in conditional_blocks:
        # The first version supports only blocks containing #else.
        if not block["has_else"]:
            report_entries.append(
                build_report_entry(
                    relative_file_path,
                    block,
                    result="SKIPPED",
                    reason=(
                        "The conditional block does not "
                        "contain an #else branch."
                    )
                )
            )

            continue

        # Multiple alternative branches are not supported yet.
        if block["contains_elif"]:
            report_entries.append(
                build_report_entry(
                    relative_file_path,
                    block,
                    result="SKIPPED",
                    reason=(
                        "Conditional blocks containing "
                        "#elif are not supported yet."
                    )
                )
            )

            continue

        # Nested transformations may overlap.
        # They are skipped until overlap handling is added.
        if (
            block[
                "contains_nested_conditionals"
            ]
            or block["nesting_depth"] > 0
        ):
            report_entries.append(
                build_report_entry(
                    relative_file_path,
                    block,
                    result="SKIPPED",
                    reason=(
                        "Nested conditional blocks are "
                        "not supported yet."
                    )
                )
            )

            continue

        original_branch = block[
            "original_branch"
        ]

        if not normalize_code_text(
            original_branch
        ):
            report_entries.append(
                build_report_entry(
                    relative_file_path,
                    block,
                    result="SKIPPED",
                    reason=(
                        "The original branch is empty."
                    )
                )
            )

            continue

        search_regions, search_error = (
            get_original_search_regions(
                block,
                original_source,
                original_functions
            )
        )

        if search_regions is None:
            report_entries.append(
                build_report_entry(
                    relative_file_path,
                    block,
                    result="SKIPPED",
                    reason=(
                        search_error
                        or "The search region could "
                           "not be determined."
                    )
                )
            )

            continue

        occurrence_count = (
            count_normalized_occurrences(
                search_regions,
                original_branch
            )
        )

        if occurrence_count == 0:
            report_entries.append(
                build_report_entry(
                    relative_file_path,
                    block,
                    result="SKIPPED",
                    reason=(
                        "The original branch was not found "
                        "in the expected scope."
                    )
                )
            )

            continue

        if occurrence_count > 1:
            report_entries.append(
                build_report_entry(
                    relative_file_path,
                    block,
                    result="SKIPPED",
                    reason=(
                        "The original branch was found "
                        f"{occurrence_count} times. "
                        "The match is ambiguous."
                    )
                )
            )

            continue

        transformation = build_transformation(
            transformation_number = (starting_transformation_number + len(transformations)),
            relative_file_path = (relative_file_path),
            block=block
        )

        transformations.append(
            transformation
        )

        report_entries.append(
            build_report_entry(
                relative_file_path,
                block,
                result="CREATED",
                reason=(
                    "The original branch was found once "
                    "in the expected scope."
                ),
                transformation_id=(
                    transformation["id"]
                )
            )
        )

    return transformations, report_entries



def save_transformations_json(
    transformations: List[Dict[str, Any]],
    output_file: Path
) -> None:
    # Keep the permanent JSON small and application-focused.
    output_data = {
        "transformations": transformations
    }

    output_file.write_text(
        json.dumps(
            output_data,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )


def indent_text(
    text: str,
    indentation: str = "    "
) -> str:
    # Indent multiline source text for a readable report.
    return "\n".join(
        indentation + line
        for line in text.splitlines()
    )


def save_extraction_report(
    report_entries: List[Dict[str, Any]],
    parser_warnings: List[str],
    detected_block_count: int,
    output_file: Path
) -> None:
    # Create a detailed human-readable extraction report.
    created_count = sum(
        entry["result"] == "CREATED"
        for entry in report_entries
    )

    skipped_count = sum(
        entry["result"] == "SKIPPED"
        for entry in report_entries
    )

    report_lines = [
        "REHOST TRANSFORMATION EXTRACTION REPORT",
        "=" * 40,
        "",
        "SUMMARY",
        "-------",
        f"Detected conditional blocks: {detected_block_count}",
        f"Created transformations: {created_count}",
        f"Skipped blocks: {skipped_count}",
        f"Warnings: {len(parser_warnings)}",
        ""
    ]

    for entry in report_entries:
        report_lines.extend(
            [
                f"[{entry['result']}]",
                f"File: {entry['file']}",
                f"Scope: {entry['scope']}"
            ]
        )

        if entry["transformation_id"] is not None:
            report_lines.append(
                "Transformation: "
                f"{entry['transformation_id']}"
            )

        if entry["function_name"] is not None:
            report_lines.append(
                f"Function: {entry['function_name']}"
            )

        report_lines.extend(
            [
                f"Rehost opening line: {entry['opening_line']}",
                f"Reason: {entry['reason']}",
                "Matched original branch:",
                indent_text(
                    entry["match_text"]
                ),
                ""
            ]
        )

    report_lines.extend(
        [
            "PARSER WARNINGS",
            "---------------"
        ]
    )

    if parser_warnings:
        for warning in parser_warnings:
            report_lines.append(
                f"- {warning}"
            )
    else:
        report_lines.append(
            "None"
        )

    report_lines.append("")

    output_file.write_text(
        "\n".join(report_lines),
        encoding="utf-8"
    )

def parse_arguments() -> argparse.Namespace:
    # Read optional command-line settings.
    parser = argparse.ArgumentParser(
        description=(
            "Extract verified conditional compilation "
            "transformations from old original and rehost files."
        )
    )

    parser.add_argument(
        "--report",
        action="store_true",
        help=(
            "Create the detailed extraction_report.txt file."
        )
    )

    return parser.parse_args()



def main() -> None:
    arguments = parse_arguments()

    original_files = find_source_files(ORIGINAL_DIR)

    rehost_files = find_source_files(REHOST_DIR)

    original_relative_paths = set(original_files)

    rehost_relative_paths = set(rehost_files)

    common_relative_paths = sorted(original_relative_paths& rehost_relative_paths)

    original_only_paths = sorted(original_relative_paths- rehost_relative_paths)

    rehost_only_paths = sorted(rehost_relative_paths- original_relative_paths)

    all_transformations = []
    all_report_entries = []
    all_warnings = []

    detected_block_count = 0
    next_transformation_number = 1

    # Files must exist at the same relative path in both directories.
    for relative_file_path in common_relative_paths:
        original_file = original_files[
            relative_file_path
        ]

        rehost_file = rehost_files[
            relative_file_path
        ]

        try:
            original_source = read_source_file(
                original_file
            )

            original_parse_result = parse_file(
                original_file
            )

            rehost_parse_result = parse_file(
                rehost_file
            )

        except (
            OSError,
            UnicodeDecodeError,
            ValueError
        ) as error:
            all_warnings.append(
                f"{relative_file_path}: "
                f"The file pair could not be processed: "
                f"{error}"
            )

            continue

        (
            file_transformations,
            file_report_entries
        ) = extract_transformations(
            original_source=original_source,
            original_parse_result=(
                original_parse_result
            ),
            rehost_parse_result=(
                rehost_parse_result
            ),
            relative_file_path=(
                relative_file_path
            ),
            starting_transformation_number=(
                next_transformation_number
            )
        )

        all_transformations.extend(
            file_transformations
        )

        all_report_entries.extend(
            file_report_entries
        )

        next_transformation_number += len(
            file_transformations
        )

        detected_block_count += len(
            rehost_parse_result[
                "conditional_blocks"
            ]
        )

        all_warnings.extend(
            (
                f"{relative_file_path} "
                f"(original): {warning}"
            )
            for warning in original_parse_result[
                "warnings"
            ]
        )

        all_warnings.extend(
            (
                f"{relative_file_path} "
                f"(rehost): {warning}"
            )
            for warning in rehost_parse_result[
                "warnings"
            ]
        )

    # An original-only file has no old rehost version to learn from.
    for relative_file_path in original_only_paths:
        all_warnings.append(
            f"{relative_file_path}: "
            "The file exists only in original and was skipped."
        )

    # A rehost-only file has no original version for branch verification.
    for relative_file_path in rehost_only_paths:
        all_warnings.append(
            f"{relative_file_path}: "
            "The file exists only in rehost and was skipped."
        )

    save_transformations_json(
        all_transformations,
        TRANSFORMATIONS_FILE
    )

    if arguments.report:
        save_extraction_report(
            report_entries=all_report_entries,
            parser_warnings=all_warnings,
            detected_block_count=(
                detected_block_count
            ),
            output_file=(
                EXTRACTION_REPORT_FILE
            )
        )

    created_count = len(
        all_transformations
    )

    skipped_count = sum(
        entry["result"] == "SKIPPED"
        for entry in all_report_entries
    )
    
    print(
        "\nTransformations written to: "
        f"{TRANSFORMATIONS_FILE}"
    )

    if arguments.report:
        print(
            "Extraction report written to: "
            f"{EXTRACTION_REPORT_FILE}"
        )
    else:
        print(
            "Extraction report was not created. "
            "Use --report to enable it."
        )


if __name__ == "__main__":
    main()