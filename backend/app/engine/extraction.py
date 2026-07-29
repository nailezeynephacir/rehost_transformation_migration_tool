from dataclasses import dataclass, field
from pathlib import Path
import json
from typing import Any, Dict, List, Optional, Set, Tuple

from .parser import exclude_functions_in_disabled_regions, parse_source
from .transformation_matching import (
    build_non_function_regions,
    count_normalized_occurrences,
    find_matching_function,
    normalize_code_text,
)


PARSED_SOURCE_EXTENSIONS = {
    ".c",
    ".h",
    ".cc",
    ".cpp",
    ".cxx",
    ".hh",
    ".hpp",
    ".hxx",
}

SUPPORT_FILE_EXTENSIONS = {
    ".py",
    ".sh",
    ".bat",
    ".cmd",
    ".ps1",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".cmake",
}

SUPPORT_FILE_NAMES = {
    "CMakeLists.txt",
    "Makefile",
}

TRACKED_FILE_EXTENSIONS = PARSED_SOURCE_EXTENSIONS | SUPPORT_FILE_EXTENSIONS
TRACKED_FILE_NAMES = SUPPORT_FILE_NAMES


@dataclass
class ExtractionResultItem:
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


@dataclass
class ExtractionSummary:
    applied: int
    skipped: int
    already_applied: int = 0


@dataclass
class ExtractionResult:
    results: List[ExtractionResultItem] = field(default_factory=list)
    summary: ExtractionSummary = field(default_factory=lambda: ExtractionSummary(0, 0, 0))


def read_source_file(file_path: Path) -> str:
    # Read one source file.
    if not file_path.exists():
        raise FileNotFoundError(f"Source file was not found: {file_path}")

    if not file_path.is_file():
        raise IsADirectoryError(f"Source path is not a file: {file_path}")

    encodings = ("utf-8", "cp1254")
    for encoding in encodings:
        try:
            return file_path.read_text(encoding=encoding)

        except UnicodeDecodeError:
            continue

    raise UnicodeError(f"Source file could not be decoded: {file_path}. Tried encodings: {', '.join(encodings)}")


def read_support_file_content(file_path: Path) -> str:
    # Read a support file without changing its line endings.
    if not file_path.exists():
        raise FileNotFoundError(f"Support file was not found: {file_path}")

    if not file_path.is_file():
        raise IsADirectoryError(f"Support file path is not a file: {file_path}")

    # Satır sonundaki '\r\n' ya da '\n' hangisi varsa değişmesin diye readText() değil readByte() ile okuyup decode ile texte çevirdik.
    file_bytes = file_path.read_bytes()

    encodings = ("utf-8", "cp1254")
    for encoding in encodings:
        try:
            return file_bytes.decode(encoding)

        except UnicodeDecodeError:
            continue

    raise UnicodeError(f"Support file could not be decoded: {file_path}. Tried encodings: {', '.join(encodings)}")


def find_project_files(source_directory: Path, allowed_extensions: set, allowed_names: Optional[Set[str]] = None,) -> Dict[str, Path]:
    # Find files with the requested extensions recursively.
    allowed_names = allowed_names or set()

    if not source_directory.exists():
        raise FileNotFoundError(f"Source directory was not found: {source_directory}")

    if not source_directory.is_dir():
        raise NotADirectoryError(f"Source path is not a directory: {source_directory}")

    project_files = {}

    for file_path in source_directory.rglob("*"):
        if not file_path.is_file():
            continue

        if (file_path.suffix.lower() not in allowed_extensions
            and file_path.name not in allowed_names):
            continue

        relative_file_path = (file_path.relative_to(source_directory).as_posix())
        project_files[relative_file_path] = file_path

    return project_files


def get_original_search_regions(
    block: Dict[str, Any],
    original_source: str,
    original_functions: List[Dict[str, Any]],
    original_non_function_regions: List[Dict[str, Any]],
) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    # Rehost içinden çıkarılan conditional block için şunu belirler: Bu block'un original hâlini eski original dosyanın hangi kısmında aramalıyım?
    # function scope -> yalnızca aynı fonksiyonun gövdesinde ara
    # include scope -> yalnızca fonksiyonların dışında ara
    # global scope -> yalnızca fonksiyonların dışında ara

    # Function transformations must be verified only inside the matching function.
    if block["scope"] == "function":
        function_name = block["function_name"]
        function_signature = block["function_signature"]

        if (function_name is None or function_signature is None):
            return (None, "Function information is missing.")

        matching_function, error = find_matching_function(original_functions, function_name, function_signature)

        if matching_function is None:
            return None, error

        # Search only inside the function body. (excluding {})
        body_start = (matching_function["body_start"] + 1)
        body_end = (matching_function["body_end"] - 1)

        return (
            [
                {
                    "start": body_start,
                    "end": body_end,
                    "text": original_source[body_start:body_end],
                }
            ],
            None
        )

    # Include and global transformations must be searched only outside functions.
    # Separate regions prevent code on opposite sides of a function from becoming one false match.
    if block["scope"] in {"include", "global"}:
        return original_non_function_regions, None

    return None, f"Unsupported scope: {block['scope']}"


def select_matching_original_branch(block: Dict[str, Any], search_regions: List[Dict[str, Any]]
) -> Tuple[Optional[Dict[str, Any]], Optional[str], List[Dict[str, Any]]]:
    # Determine which conditional branch came from the old original file.
    branches = block.get("branches")

    if not isinstance(branches, list) or not branches:
        return (
            None,
            "The conditional block does not contain a valid branches list.",
            [],
        )

    branch_results = []

    for branch in branches:
        branch_text = branch.get("content")

        # An empty branch cannot represent a continuous code section taken from the old original source.
        if (not isinstance(branch_text, str) or not normalize_code_text(branch_text)):
            occurrence_count = 0

        else:
            occurrence_count = count_normalized_occurrences(search_regions, branch_text,)

        branch_results.append(
            {
                "directive": branch.get("directive"),
                "condition": branch.get("condition"),
                "text": branch_text,
                "occurrence_count": occurrence_count,
                # Restored: the line the branch opens on, so ambiguous/none-matched
                # messages can say *where*, not just *how many*.
                "line_number": branch.get("line_number"),
            }
        )

    found_matches = [result for result in branch_results if result["occurrence_count"] > 0]

    if len(found_matches) == 1:
        selected_match = found_matches[0]

        # Sibling team decision (2026-07-28): multiple untransformed matches
        # are ambiguous in every scope, including function scope - removed
        # the prior scope exception. Rationale: two identical matches inside
        # one function don't prove both were meant to change - if only one
        # of them was actually guarded in the real rehost, extraction can't
        # tell which without this check, and would learn a transformation
        # that wasn't actually made.
        if selected_match["occurrence_count"] > 1:
            return (
                None,
                "The matching branch was found more than once in the required scope, so the match is ambiguous.",
                branch_results,
            )

        selected_block = dict(block)

        selected_block["matched_branch_content"] = selected_match["text"]

        selected_block["matched_branch"] = {
            "directive": selected_match["directive"],
            "condition": selected_match["condition"],
        }

        return selected_block, None, branch_results

    result_details = []

    for result in branch_results:
        directive = result["directive"]
        condition = result["condition"]

        if condition is None:
            branch_description = f"#{directive}"
        else:
            branch_description = f"#{directive} {condition}"

        result_details.append(
            f"{branch_description} (line {result['line_number']}): {result['occurrence_count']} match(es)")

    result_details_text = ", ".join(result_details)

    if not found_matches:
        return (
            None,
            "None of the conditional branches was found as one continuous block in the expected scope. "
            f"Results: {result_details_text}.",
            branch_results,
        )

    if len(found_matches) > 1:
        return (
            None,
            "More than one conditional branch was found in the old original source, so the original branch is ambiguous. "
            f"Results: {result_details_text}.",
            branch_results,
        )


# ----- ORIGINALDE OLMAYIP SADECE REHOSTTA OLAN KODLARI EKLEMEK İÇİN -----
def determine_function_insertion_position(block: Dict[str, Any], rehost_source: str, rehost_functions: List[Dict[str, Any]]) -> Optional[str]:
    # Determine whether a rehost-only conditional block is at the beginning or end of its containing function.
    function_name = block.get("function_name")
    function_signature = block.get("function_signature")

    if function_name is None or function_signature is None:
        return None

    matching_function, error = find_matching_function(rehost_functions, function_name, function_signature)

    if matching_function is None:
        return None

    code_before_block = rehost_source[matching_function["body_start"] + 1:block["start"]]
    code_after_block = rehost_source[block["end"]:matching_function["body_end"] - 1]

    if not normalize_code_text(code_before_block):
        return "function_start"

    if not normalize_code_text(code_after_block):
        return "function_end"

    return None


def contains_unstable_preprocessor_directive(text: str) -> bool:
    # Permit #include anchors, but reject conditional and macro directives.
    for line in text.splitlines():
        normalized_line = normalize_code_text(line)

        if not normalized_line:
            continue

        if (normalized_line.startswith("#") and not normalized_line.startswith("#include")):
            return True

    return False


def find_unique_following_anchor(block: Dict[str, Any], rehost_source: str, rehost_functions: List[Dict[str, Any]], original_search_regions: List[Dict[str, Any]]) -> Optional[str]:
    # Find a unique piece of code after a rehost-only conditional  block so the block can be inserted immediately before it.
    function_name = block.get("function_name")
    function_signature = block.get("function_signature")

    if function_name is None or function_signature is None:
        return None

    matching_function, error = find_matching_function(rehost_functions, function_name, function_signature)

    if matching_function is None:
        return None

    code_after_block = rehost_source[block["end"]:matching_function["body_end"] - 1]

    candidate_lines = []
    meaningful_line_count = 0

    for line in code_after_block.splitlines(keepends=True):
        candidate_lines.append(line)

        # Empty lines and comments do not make an anchor reliable.
        if not normalize_code_text(line):
            continue

        meaningful_line_count += 1
        candidate_text = "".join(candidate_lines).strip()

        if contains_unstable_preprocessor_directive(candidate_text):
            return None

        occurrence_count = count_normalized_occurrences(original_search_regions, candidate_text)

        if occurrence_count == 1:
            return candidate_text

        # If the candidate does not exist at all, extending it cannot turn it into a valid continuous match.
        if occurrence_count == 0:
            return None

        # Avoid using an unnecessarily large anchor.
        if meaningful_line_count >= 5:
            return None

    return None


def find_unique_preceding_anchor(block: Dict[str, Any], rehost_source: str, rehost_functions: List[Dict[str, Any]], original_search_regions: List[Dict[str, Any]]) -> Optional[str]:
    # Find a unique piece of code before a rehost-only conditional block so the block can be inserted immediately after it.
    function_name = block.get("function_name")
    function_signature = block.get("function_signature")

    if function_name is None or function_signature is None:
        return None

    matching_function, error = find_matching_function(rehost_functions, function_name, function_signature)

    if matching_function is None:
        return None

    code_before_block = rehost_source[matching_function["body_start"] + 1:block["start"]]
    lines_before_block = code_before_block.splitlines(keepends=True)

    candidate_lines = []
    meaningful_line_count = 0

    # Start with the line closest to the conditional block and gradually extend the candidate upward.
    for line in reversed(lines_before_block):
        candidate_lines.insert(0, line)

        # Empty lines and comments do not make an anchor reliable.
        if not normalize_code_text(line):
            continue

        meaningful_line_count += 1
        candidate_text = "".join(candidate_lines).strip()

        # Do not use conditional or macro directives as function-scope anchors.
        if contains_unstable_preprocessor_directive(candidate_text):
            return None

        occurrence_count = count_normalized_occurrences(original_search_regions, candidate_text)

        if occurrence_count == 1:
            return candidate_text

        # If the closest candidate does not exist in the original, extending it upward cannot produce a continuous match.
        if occurrence_count == 0:
            return None

        # Avoid using an unnecessarily large anchor.
        if meaningful_line_count >= 5:
            return None
    return None


def find_containing_non_function_region(block: Dict[str, Any], rehost_non_function_regions: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    # Find the non-function source region that completely
    # contains the conditional block.
    for region in rehost_non_function_regions:
        if (
            region["start"] <= block["start"]
            and block["end"] <= region["end"]
        ):
            return region

    return None


def find_unique_following_non_function_anchor(block: Dict[str, Any], rehost_source: str, rehost_non_function_regions: List[Dict[str, Any]], original_search_regions: List[Dict[str, Any]]) -> Optional[str]:
    # Find a unique file-level code fragment after a rehost-only conditional block.
    containing_region = find_containing_non_function_region(block=block, rehost_non_function_regions=rehost_non_function_regions,)

    if containing_region is None:
        return None

    code_after_block = rehost_source[block["end"]:containing_region["end"]]

    candidate_lines = []
    meaningful_line_count = 0

    for line in code_after_block.splitlines(keepends=True):
        candidate_lines.append(line)

        if not normalize_code_text(line):
            continue

        meaningful_line_count += 1
        candidate_text = "".join(candidate_lines).strip()

        # #define SENSOR_H, #endif, #ifdef gibi kırılgan anchor'lar kullanılmaz ama #include "x.h" kullanılabilir.
        if contains_unstable_preprocessor_directive(candidate_text):
            return None

        occurrence_count = count_normalized_occurrences(original_search_regions, candidate_text)

        if occurrence_count == 1:
            return candidate_text

        if occurrence_count == 0:
            return None

        if meaningful_line_count >= 5:
            return None

    return None


def find_unique_preceding_non_function_anchor(block: Dict[str, Any], rehost_source: str, rehost_non_function_regions: List[Dict[str, Any]], original_search_regions: List[Dict[str, Any]]) -> Optional[str]:
    # Find a unique file-level code fragment before a rehost-only conditional block.

    containing_region = find_containing_non_function_region(
        block=block,
        rehost_non_function_regions=rehost_non_function_regions,
    )
    if containing_region is None:
        return None

    code_before_block = rehost_source[containing_region["start"]:block["start"]]
    lines_before_block = code_before_block.splitlines(keepends=True)

    candidate_lines = []
    meaningful_line_count = 0

    for line in reversed(lines_before_block):
        candidate_lines.insert(0, line)

        if not normalize_code_text(line):
            continue

        meaningful_line_count += 1
        candidate_text = "".join(candidate_lines).strip()

        # #define SENSOR_H, #endif, #ifdef gibi kırılgan anchor'lar kullanılmaz ama #include "x.h" kullanılabilir.
        if contains_unstable_preprocessor_directive(candidate_text):
            return None

        occurrence_count = count_normalized_occurrences(original_search_regions, candidate_text)

        if occurrence_count == 1:
            return candidate_text

        if occurrence_count == 0:
            return None

        if meaningful_line_count >= 5:
            return None

    return None
# ------------------------------------------------------------------------

# ----- build transformations --------------------------------------------
def build_transformation(transformation_number: int, relative_file_path: str, block: Dict[str, Any]) -> Dict[str, Any]:
    # Store only information required by application.py.
    matched_branch_content = block.get("matched_branch_content")

    if (not isinstance(matched_branch_content, str) or not normalize_code_text(matched_branch_content)):
        raise ValueError("The selected conditional block does not contain valid matched branch content.")

    full_text = block.get("full_text")

    if not isinstance(full_text, str) or not full_text.strip():
        raise ValueError("The selected conditional block does not contain valid replacement text.")

    transformation = {
        "id": f"conditional_{transformation_number}",
        "file": relative_file_path,
        "scope": block["scope"],
        "match": matched_branch_content.strip(),
        "replacement": full_text.rstrip("\r\n"),
    }

    # Function information is required only for function-scope transformations.
    if block["scope"] == "function":
        transformation["function"] = {
            "name": block["function_name"],
            "signature": block["function_signature"],
        }

    return transformation


def build_insertion_transformation(transformation_number: int, relative_file_path: str, block: Dict[str, Any], position: str) -> Dict[str, Any]:
    # Store a rehost-only conditional block as a positional insertion.
    return {
        "id": f"conditional_{transformation_number}",
        "file": relative_file_path,
        "scope": "function",
        "operation": "insert",
        "position": position,
        "content": block["full_text"].rstrip("\r\n"),
        "function": {
            "name": block["function_name"],
            "signature": block["function_signature"],
        },
    }


def build_anchor_insertion_transformation(transformation_number: int, relative_file_path: str, block: Dict[str, Any], position: str, anchor: str, fallback_position: Optional[str] = None, fallback_anchor: Optional[str] = None
) -> Dict[str, Any]:
    # Store a rehost-only conditional block as an insertion immediately before or after a unique anchor.
    transformation = {
        "id": f"conditional_{transformation_number}",
        "file": relative_file_path,
        "scope": block["scope"],
        "operation": "insert",
        "position": position,
        "anchor": anchor,
        "content": block["full_text"].rstrip("\r\n"),
    }

    # Store the opposite-side anchor as a fallback when available.
    if (
        fallback_position in {"before", "after"}
        and isinstance(fallback_anchor, str)
        and fallback_anchor.strip()
    ):
        transformation["fallback_position"] = fallback_position
        transformation["fallback_anchor"] = fallback_anchor

    if block["scope"] == "function":
        transformation["function"] = {
            "name": block["function_name"],
            "signature": block["function_signature"],
        }

    return transformation
# ------------------------------------------------------------------------

def build_report_entry(relative_file_path: str, block: Dict[str, Any], result: str, reason: str, transformation_id: Optional[str] = None, transformation: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    # Keep extraction details outside the transformation JSON.
    match_text = block.get("matched_branch_content", "")

    if not isinstance(match_text, str):
        match_text = ""

    matched_branch = block.get("matched_branch")

    branch_directive = None
    branch_condition = None

    if isinstance(matched_branch, dict):
        branch_directive = matched_branch.get("directive")
        branch_condition = matched_branch.get("condition")

    operation = "replace"
    position = None
    anchor = None
    fallback_position = None
    fallback_anchor = None

    if isinstance(transformation, dict):
        operation = transformation.get("operation", "replace")
        position = transformation.get("position")
        anchor = transformation.get("anchor")
        fallback_position = transformation.get("fallback_position")
        fallback_anchor = transformation.get("fallback_anchor")

    return {
        "result": result,
        "transformation_id": transformation_id,
        "file": relative_file_path,
        "scope": block["scope"],
        "function_name": block["function_name"],
        "operation": operation,
        "position": position,
        "anchor": anchor,
        "fallback_position": fallback_position,
        "fallback_anchor": fallback_anchor,
        "matched_branch_directive": branch_directive,
        "matched_branch_condition": branch_condition,
        "match_text": match_text.strip(),
        # Restored: build_report_entry() had stopped carrying the block's
        # opening line through to the report.
        "opening_line_number": block.get("opening_line_number"),
        # Which target macro(s) this block was actually about - needed so the
        # service layer can populate TransformationResult.matched_macro without
        # re-deriving it from scratch.
        "target_macros": block.get("matched_target_macros", []),
        "reason": reason,
        # The complete rehost conditional block text - the service layer's
        # source for TransformationResult.rehost_snippet.
        "rehost_snippet": block.get("full_text"),
    }


def _build_no_target_blocks_report_entry(relative_file_path: str) -> Dict[str, Any]:
    # Bug fix: a file whose conditional blocks exist but none reference a
    # target macro used to produce zero report entries for that file - no
    # CREATED, no SKIPPED, no trace it was ever looked at.
    return {
        "result": "SKIPPED",
        "transformation_id": None,
        "file": relative_file_path,
        "scope": None,
        "function_name": None,
        "operation": "none",
        "position": None,
        "anchor": None,
        "fallback_position": None,
        "fallback_anchor": None,
        "matched_branch_directive": None,
        "matched_branch_condition": None,
        "match_text": "",
        "opening_line_number": None,
        "target_macros": [],
        "reason": "The rehost file contains conditional compilation blocks, but none of them reference a target macro.",
        "rehost_snippet": None,
    }


def extract_file_transformations(original_source: str, rehost_source: str, original_parse_result: Dict[str, Any], rehost_parse_result: Dict[str, Any], relative_file_path: str, starting_transformation_number: int
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    # Verify each conditional block from the old rehost file against the old original file.
    transformations = []
    report_entries = []

    original_functions = (original_parse_result["functions"])
    conditional_blocks = (rehost_parse_result["conditional_blocks"])
    transformation_candidate_blocks = [block for block in conditional_blocks if block["is_target"]]
    rehost_functions = rehost_parse_result["functions"]
    parser_warnings = (original_parse_result["warnings"] + rehost_parse_result["warnings"])

    # Bug fix: checked *before* the parser-warnings check below, since a file
    # with no target-referencing blocks at all has nothing else to report
    # regardless of whether the parser also emitted warnings.
    if conditional_blocks and not transformation_candidate_blocks:
        report_entries.append(_build_no_target_blocks_report_entry(relative_file_path))
        return transformations, report_entries

    # Parser warnings mean that source boundaries may be unreliable.
    # Skip every block from the file instead of producing transformations from partially parsed input.
    if parser_warnings:
        for block in transformation_candidate_blocks:
            report_entries.append(
                build_report_entry(
                    relative_file_path,
                    block,
                    result="SKIPPED",
                    reason=("The file produced parser warnings, so no transformation was extracted from this block.")
                )
            )
        return transformations, report_entries

    # Function-shaped constructs sitting entirely inside a provably-dead
    # "#if 0" block (see B3) must not be carved out of global/include search
    # text - find_function_regions() can't tell them apart from real, live
    # functions, so that exclusion is done explicitly here, only for the
    # regions built below. original_functions/rehost_functions themselves
    # stay unfiltered - function-scope matching elsewhere in this file still
    # needs to find such a function by name/signature if directly targeted.
    original_searchable_functions = exclude_functions_in_disabled_regions(
        original_functions, original_parse_result["conditional_blocks"]
    )
    rehost_searchable_functions = exclude_functions_in_disabled_regions(
        rehost_functions, conditional_blocks
    )

    # These regions depend only on the parsed file, so build them once per file.
    original_non_function_regions = build_non_function_regions(original_source, original_searchable_functions,)
    rehost_non_function_regions = build_non_function_regions(rehost_source, rehost_searchable_functions,)

    for block in transformation_candidate_blocks:

        # Target conditional blocks nested inside other target conditional blocks may create overlapping transformations.
        if (block["has_target_ancestor"] or block["contains_nested_target_conditionals"]):
            report_entries.append(
                build_report_entry(
                    relative_file_path,
                    block,
                    result="SKIPPED",
                    reason=("The target conditional block is nested inside another target conditional block or contains a nested target conditional block."),
                )
            )
            continue

        search_regions, search_error = get_original_search_regions(
            block=block,
            original_source=original_source,
            original_functions=original_functions,
            original_non_function_regions=original_non_function_regions,
        )

        if search_regions is None:
            report_entries.append(
                build_report_entry(
                    relative_file_path,
                    block,
                    result="SKIPPED",
                    reason=(search_error or "The search region could not be determined.")
                )
            )

            continue

        (selected_block, branch_selection_error, branch_results,
        ) = select_matching_original_branch(block, search_regions,)

        if selected_block is None:
            branches_are_absent = all(result["occurrence_count"] == 0 for result in branch_results)

            # Insertion is allowed only when none of the conditional branches exists in the old original source.
            if branches_are_absent:
                insertion_position = None
                insertion_anchor = None
                fallback_position = None
                fallback_anchor = None

                if block["scope"] == "function":
                    insertion_position = determine_function_insertion_position(
                        block=block,
                        rehost_source=rehost_source,
                        rehost_functions=rehost_functions,
                    )

                    if insertion_position is None:
                        following_anchor = find_unique_following_anchor(
                            block=block,
                            rehost_source=rehost_source,
                            rehost_functions=rehost_functions,
                            original_search_regions=search_regions,
                        )

                        preceding_anchor = find_unique_preceding_anchor(
                            block=block,
                            rehost_source=rehost_source,
                            rehost_functions=rehost_functions,
                            original_search_regions=search_regions,
                        )

                        if following_anchor is not None:
                            insertion_position = "before"
                            insertion_anchor = following_anchor

                            if preceding_anchor is not None:
                                fallback_position = "after"
                                fallback_anchor = preceding_anchor

                        elif preceding_anchor is not None:
                            insertion_position = "after"
                            insertion_anchor = preceding_anchor

                elif block["scope"] in {"include", "global"}:
                    following_anchor = find_unique_following_non_function_anchor(
                        block=block,
                        rehost_source=rehost_source,
                        rehost_non_function_regions=rehost_non_function_regions,
                        original_search_regions=search_regions,
                    )

                    preceding_anchor = find_unique_preceding_non_function_anchor(
                        block=block,
                        rehost_source=rehost_source,
                        rehost_non_function_regions=rehost_non_function_regions,
                        original_search_regions=search_regions,
                    )

                    if following_anchor is not None:
                        insertion_position = "before"
                        insertion_anchor = following_anchor

                        if preceding_anchor is not None:
                            fallback_position = "after"
                            fallback_anchor = preceding_anchor

                    elif preceding_anchor is not None:
                        insertion_position = "after"
                        insertion_anchor = preceding_anchor

                transformation = None

                if insertion_position in {"function_start", "function_end"}:
                    transformation = (
                        build_insertion_transformation(
                            transformation_number=(starting_transformation_number + len(transformations)),
                            relative_file_path=relative_file_path,
                            block=block,
                            position=insertion_position
                        )
                    )

                elif (
                    insertion_position in {"before", "after"} and insertion_anchor is not None
                ):
                    transformation = (
                        build_anchor_insertion_transformation(
                            transformation_number=(starting_transformation_number + len(transformations)),
                            relative_file_path=relative_file_path,
                            block=block,
                            position=insertion_position,
                            anchor=insertion_anchor,
                            fallback_position=fallback_position,
                            fallback_anchor=fallback_anchor
                        )
                    )

                if transformation is not None:
                    transformations.append(transformation)

                    report_entries.append(
                        build_report_entry(
                            relative_file_path,
                            block,
                            result="CREATED",
                            reason=("None of the conditional branch exists in the old original source. The complete block was stored as an insertion."),
                            transformation_id=transformation["id"],
                            transformation=transformation,
                        )
                    )

                    continue

            report_entries.append(
                build_report_entry(
                    relative_file_path,
                    block,
                    result="SKIPPED",
                    reason=(
                        "None of the conditional branch exists in the old original source, but no unique and reliable insertion point could be identified."
                        if branches_are_absent
                        else (branch_selection_error or "The original branch could not be identified.")
                    )
                )
            )

            continue

        transformation = build_transformation(
            transformation_number=(starting_transformation_number + len(transformations)),
            relative_file_path=relative_file_path,
            block=selected_block,
        )

        transformations.append(transformation)

        report_entries.append(
            build_report_entry(
                relative_file_path,
                selected_block,
                result="CREATED",
                reason=("Conditional branch was found in the expected scope."),
                transformation_id=(transformation["id"]),
                transformation=transformation,
            )
        )

    return transformations, report_entries


def build_support_files(rehost_only_paths: List[str], rehost_files: Dict[str, Path]
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]], List[str]]:
    # Store rehost-only source files so application.py does not need access to the old rehost directory.
    support_files = []
    report_entries = []
    warnings = []

    for relative_file_path in rehost_only_paths:
        support_file_path = rehost_files[relative_file_path]

        try:
            content = read_support_file_content(support_file_path)

        except (OSError, UnicodeError) as error:
            reason = f"The rehost-only file could not be stored as UTF-8 or cp1254 content: {error}"
            report_entries.append(
                {
                    "result": "SKIPPED",
                    "file": relative_file_path,
                    "reason": reason,
                }
            )

            warnings.append(f"{relative_file_path}: {reason}")

            continue

        support_files.append(
            {
                "path": relative_file_path,
                "content": content,
            }
        )

        report_entries.append(
            {
                "result": "CREATED",
                "file": relative_file_path,
                "reason": "The file exists only in rehost, so its complete content was stored in the JSON.",
            }
        )

    return (support_files, report_entries, warnings)


def save_transformations_json(transformations: List[Dict[str, Any]], support_files: List[Dict[str, str]], target_macros: set, output_file: Path) -> None:
    # Keep the permanent JSON small and application-focused.
    # target_macros is included so a downstream consumer (e.g. the web UI)
    # can display what a run was searched for without needing to keep its
    # own separate record - sorted for deterministic output, since sets
    # don't have a stable iteration order and aren't JSON-serializable directly.
    output_data = {
        "transformations": transformations,
        "support_files": support_files,
        "target_macros": sorted(target_macros),
    }

    output_file.write_text(
        json.dumps(
            output_data,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )


def indent_text(text: str, indentation: str = "    ") -> str:
    # Indent multiline source text for a readable report.
    return "\n".join(indentation + line for line in text.splitlines())


def save_extraction_report(report_entries: List[Dict[str, Any]], support_file_entries: List[Dict[str, str]], parser_warnings: List[str],
detected_block_count: int, output_file: Path,) -> None:
    # Create a detailed human-readable extraction report.
    created_count = sum(
        entry["result"] == "CREATED"
        for entry in report_entries
    )
    skipped_count = sum(
        entry["result"] == "SKIPPED"
        for entry in report_entries
    )

    stored_support_file_count = sum(
        entry["result"] == "CREATED"
        for entry in support_file_entries
    )
    skipped_support_file_count = sum(
        entry["result"] == "SKIPPED"
        for entry in support_file_entries
    )

    report_lines = [
        "REHOST TRANSFORMATION EXTRACTION REPORT",
        "=" * 40,
        "",
        "SUMMARY",
        "-------",
        f"Target conditional blocks detected: {detected_block_count}",
        f"Created transformations: {created_count}",
        f"Skipped blocks: {skipped_count}",
        f"Support files stored in JSON: {stored_support_file_count}",
        f"Support files skipped: {skipped_support_file_count}",
        f"Warnings: {len(parser_warnings)}",
        "",
        "TRANSFORMATIONS",
        "---------------",
    ]

    if report_entries:
        for entry in report_entries:
            report_lines.extend(
                [
                    f"[{entry['result']}]",
                    f"File: {entry['file']}",
                    f"Scope: {entry['scope']}",
                ]
            )

            # Restored: the report-printing loop had stopped printing the
            # block's opening line alongside the file/scope.
            if entry.get("opening_line_number") is not None:
                report_lines.append(f"Line: {entry['opening_line_number']}")

            if entry["transformation_id"] is not None:
                report_lines.append(
                    f"Transformation: {entry['transformation_id']}"
                )

            if entry["function_name"] is not None:
                report_lines.append(
                    f"Function: {entry['function_name']}"
                )

            matched_directive = entry.get(
                "matched_branch_directive"
            )

            if matched_directive is not None:
                matched_condition = entry.get(
                    "matched_branch_condition"
                )

                if matched_condition is None:
                    branch_description = f"#{matched_directive}"
                else:
                    branch_description = (
                        f"#{matched_directive} "
                        f"{matched_condition}"
                    )

                report_lines.append(f"Matched branch: {branch_description}")

            report_lines.append(f"Operation: {entry['operation']}")

            if entry["operation"] == "insert":
                report_lines.append(f"Position: {entry['position']}")

                if entry["anchor"] is not None:
                    report_lines.extend(["Anchor:", indent_text(entry["anchor"]),])

                if entry["fallback_anchor"] is not None:
                    report_lines.extend(
                        [
                            (
                                "Fallback position: "
                                f"{entry['fallback_position']}"
                            ),
                            "Fallback anchor:",
                            indent_text(
                                entry["fallback_anchor"]
                            ),
                        ]
                    )

            report_lines.append(f"Reason: {entry['reason']}")

            if entry["operation"] == "replace":
                report_lines.extend(["Matched original branch:", indent_text(entry["match_text"]),])

            report_lines.append("")
    else:
        report_lines.extend(
            [
                "None",
                "",
            ]
        )

    report_lines.extend(
        [
            "SUPPORT FILES",
            "-------------",
        ]
    )

    if support_file_entries:
        for entry in support_file_entries:
            report_lines.extend(
                [
                    f"[{entry['result']}]",
                    f"File: {entry['file']}",
                    f"Reason: {entry['reason']}",
                    "",
                ]
            )
    else:
        report_lines.extend(
            [
                "None",
                "",
            ]
        )

    report_lines.extend(
        [
            "WARNINGS",
            "--------",
        ]
    )

    if parser_warnings:
        for warning in parser_warnings:
            report_lines.append(f"- {warning}")
    else:
        report_lines.append("None")

    report_lines.append("")

    output_file.write_text("\n".join(report_lines), encoding="utf-8",)


def _to_extraction_result_item(entry: Dict[str, Any]) -> ExtractionResultItem:
    matched_macros = entry.get("target_macros") or []
    original_snippet = entry.get("match_text") or None
    rehost_snippet = entry.get("rehost_snippet") or None

    return ExtractionResultItem(
        transformation_id=entry.get("transformation_id"),
        file=entry["file"],
        scope=entry.get("scope"),
        function_name=entry.get("function_name"),
        status="Applied" if entry["result"] == "CREATED" else "Skipped",
        matched_macro=", ".join(matched_macros) if matched_macros else None,
        opening_line=entry.get("opening_line_number"),
        reason=entry["reason"],
        original_snippet=original_snippet,
        rehost_snippet=rehost_snippet,
    )


def _build_extraction_summary(report_entries: List[Dict[str, Any]]) -> ExtractionSummary:
    applied = sum(1 for entry in report_entries if entry["result"] == "CREATED")
    skipped = sum(1 for entry in report_entries if entry["result"] == "SKIPPED")
    return ExtractionSummary(applied=applied, skipped=skipped, already_applied=0)


def extract_transformations(
    original_dir: Path,
    rehost_dir: Path,
    transformations_path: Path,
    report_path: Path,
    target_macros: Set[str],
) -> ExtractionResult:
    original_source_files = find_project_files(original_dir, PARSED_SOURCE_EXTENSIONS)
    rehost_source_files = find_project_files(rehost_dir, PARSED_SOURCE_EXTENSIONS)

    original_tracked_files = find_project_files(
        original_dir,
        TRACKED_FILE_EXTENSIONS,
        TRACKED_FILE_NAMES,
    )
    rehost_tracked_files = find_project_files(
        rehost_dir,
        TRACKED_FILE_EXTENSIONS,
        TRACKED_FILE_NAMES,
    )

    original_source_paths = set(original_source_files)
    rehost_source_paths = set(rehost_source_files)

    common_relative_paths = sorted(original_source_paths & rehost_source_paths)
    original_only_paths = sorted(original_source_paths - rehost_source_paths)

    original_tracked_paths = set(original_tracked_files)
    rehost_tracked_paths = set(rehost_tracked_files)

    rehost_only_paths = sorted(rehost_tracked_paths - original_tracked_paths)

    all_transformations: List[Dict[str, Any]] = []
    all_report_entries: List[Dict[str, Any]] = []
    all_warnings: List[str] = []

    detected_block_count = 0
    next_transformation_number = 1

    # Files must exist at the same relative path in both directories.
    for relative_file_path in common_relative_paths:
        original_file = original_source_files[relative_file_path]
        rehost_file = rehost_source_files[relative_file_path]

        try:
            original_source = read_source_file(original_file)
            rehost_source = read_source_file(rehost_file)

            original_parse_result = parse_source(original_source, target_macros=target_macros,)
            rehost_parse_result = parse_source(rehost_source, target_macros=target_macros,)

            file_transformations, file_report_entries = extract_file_transformations(
                original_source=original_source,
                rehost_source=rehost_source,
                original_parse_result=original_parse_result,
                rehost_parse_result=rehost_parse_result,
                relative_file_path=relative_file_path,
                starting_transformation_number=next_transformation_number
            )

            all_transformations.extend(file_transformations)
            all_report_entries.extend(file_report_entries)

            next_transformation_number += len(file_transformations)

            detected_block_count += sum(
                block["is_target"]
                for block in rehost_parse_result["conditional_blocks"]
            )

            all_warnings.extend(
                f"{relative_file_path} (original): {warning}"
                for warning in original_parse_result["warnings"]
            )

            all_warnings.extend(
                f"{relative_file_path} (rehost): {warning}"
                for warning in rehost_parse_result["warnings"]
            )

        except (OSError, UnicodeError, ValueError) as error:
            all_warnings.append(f"{relative_file_path}: "
                f"The file pair could not be processed: {error}"
            )
            continue

    # An original-only file has no old rehost version to learn from.
    for relative_file_path in original_only_paths:
        all_warnings.append(f"{relative_file_path}: The file exists only in original and was skipped.")

    # Rehost-only files are complete support files rather than conditional transformations. Store their content in the JSON.
    (all_support_files, all_support_file_entries, support_file_warnings) = build_support_files(rehost_only_paths, rehost_tracked_files)

    all_warnings.extend(support_file_warnings)

    save_transformations_json(
        transformations=all_transformations,
        support_files=all_support_files,
        target_macros=target_macros,
        output_file=transformations_path
    )

    save_extraction_report(
        report_entries=all_report_entries,
        support_file_entries=(all_support_file_entries),
        parser_warnings=all_warnings,
        detected_block_count=(detected_block_count),
        output_file=(report_path)
    )

    return ExtractionResult(
        results=[_to_extraction_result_item(entry) for entry in all_report_entries],
        summary=_build_extraction_summary(all_report_entries),
    )