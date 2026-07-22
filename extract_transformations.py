from pathlib import Path
import json
import argparse
from typing import Any, Dict, List, Optional, Tuple

from parser import parse_file
from transformation_matching import build_non_function_regions, count_normalized_occurrences, find_matching_function, normalize_code_text


PROJECT_ROOT = Path(__file__).resolve().parent

ORIGINAL_DIR = (PROJECT_ROOT / "original")

REHOST_DIR = (PROJECT_ROOT / "rehost")

TRANSFORMATIONS_FILE = (PROJECT_ROOT / "rehost_transformations.json")

EXTRACTION_REPORT_FILE = (PROJECT_ROOT / "extraction_report.txt")

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


def read_source_file(file_path: Path) -> str:
    # Read one source file.
    if not file_path.exists():
        raise FileNotFoundError(f"Source file was not found: {file_path}")

    try:
        return file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        print(f"{file_path} UTF-8 olarak okunamadı, cp1254 denendi.")
        return file_path.read_text(encoding="cp1254")



def read_support_file_content(file_path: Path) -> str:
    # Read a support file without changing its line endings.
    if not file_path.exists():
        raise FileNotFoundError(f"Support file was not found: {file_path}")

    # Satır sonundaki '\r\n' ya da '\n' hangisi varsa değişmesin diye readText() değil readByte() ile okuyup decode ile texte çevirdik.
    file_bytes = file_path.read_bytes()

    try:
        return file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        print(f"{file_path} UTF-8 olarak okunamadı, cp1254 denendi.")
        return file_bytes.decode("cp1254")


def find_source_files(source_directory: Path) -> Dict[str, Path]:
    # Find supported C and C++ files recursively.
    # Files are indexed by their relative POSIX-style paths so matching files in original and rehost can be paired reliably.
    if not source_directory.exists():
        raise FileNotFoundError("Source directory was not found: "f"{source_directory}")

    if not source_directory.is_dir():
        raise NotADirectoryError("Source path is not a directory: "f"{source_directory}")

    source_files = {}

    for file_path in source_directory.rglob("*"):
        if not file_path.is_file():
            continue

        if (file_path.suffix.lower()not in SUPPORTED_SOURCE_EXTENSIONS):
            continue

        relative_file_path = (file_path.relative_to(source_directory).as_posix())

        source_files[relative_file_path] = file_path

    return source_files


def get_original_search_regions(block: Dict[str, Any], original_source: str, original_functions: List[Dict[str, Any]]
) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    # Rehost içinden çıkarılan conditional block için şunu belirler: Bu block’un original hâlini eski original dosyanın hangi kısmında aramalıyım?
    # function scope → yalnızca aynı fonksiyonun gövdesinde ara
    # include scope → yalnızca fonksiyonların dışında ara
    # global scope → yalnızca fonksiyonların dışında ara

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
        return (build_non_function_regions(original_source, original_functions), None)

    return (None, f"Unsupported scope: {block['scope']}")


def select_matching_original_branch(block: Dict[str, Any], search_regions: List[Dict[str, Any]]
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    # Determine which conditional branch came from the old original file.
    # The parser only knows the physical branch positions:
    # - original_branch: branch before #else
    # - alternative_branch: branch after #else
    # Therefore, both branches are searched in the old original source.
    branch_candidates = [
        {
            "name": "first branch",
            "text": block.get("original_branch"),
        },
        {
            "name": "else branch",
            "text": block.get("alternative_branch"),
        },
    ]

    branch_results = []

    for candidate in branch_candidates:
        branch_text = candidate["text"]

        # A missing or empty branch cannot represent code from the old original file.
        if (not isinstance(branch_text, str) or not normalize_code_text(branch_text)):
            occurrence_count = 0

        else:
            occurrence_count = (count_normalized_occurrences(search_regions, branch_text))

        branch_results.append(
            {
                "name": candidate["name"],
                "text": branch_text,
                "occurrence_count": (occurrence_count),
            }
        )

    unique_matches = [result for result in branch_results if result["occurrence_count"] == 1]
    found_matches = [result for result in branch_results if result["occurrence_count"] > 0]

    # MODIFY: safe case çok safe ya
    # Safe case:
    # One branch occurs exactly once and the other does not occur.
    if (len(unique_matches) == 1 and len(found_matches) == 1):
        selected_match = unique_matches[0]
        selected_block = dict(block)

        # build_transformation() expects the matched old-original code under the original_branch key.
        selected_block["original_branch"] = selected_match["text"]

        return selected_block, None

    result_details = ", ".join(
        (f"{result['name']}: {result['occurrence_count']} match(es)")
        for result in branch_results
    )

    if not found_matches:
        return (None,
            "Neither conditional branch was found as one continuous block in the expected scope. "
            f"Results: {result_details}."
        )

    if len(found_matches) > 1:
        return (None,
            "More than one conditional branch was found in the old original source, so the original branch is ambiguous. "
            f"Results: {result_details}."
        )

    return (None,
        "The matching conditional branch was found more than once, so the match is ambiguous. "
        f"Results: {result_details}."
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

    matching_function, error = find_matching_function(rehost_functions,function_name,function_signature)

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

def find_containing_non_function_region(block: Dict[str, Any],rehost_source: str,rehost_functions: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    # Find the non-function source region that completely contains the conditional block.
    non_function_regions = build_non_function_regions(rehost_source, rehost_functions)

    for region in non_function_regions:
        if (region["start"] <= block["start"] and block["end"] <= region["end"]):
            return region
    return None

def find_unique_following_non_function_anchor(block: Dict[str, Any],rehost_source: str,rehost_functions: List[Dict[str, Any]],original_search_regions: List[Dict[str, Any]]) -> Optional[str]:
    # Find a unique file-level code fragment after a rehost-only conditional block.
    containing_region = find_containing_non_function_region(block=block, rehost_source=rehost_source, rehost_functions=rehost_functions)

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

        occurrence_count = count_normalized_occurrences(original_search_regions, candidate_text)

        if occurrence_count == 1:
            return candidate_text

        if occurrence_count == 0:
            return None

        if meaningful_line_count >= 5:
            return None

    return None

def find_unique_preceding_non_function_anchor(block: Dict[str, Any],rehost_source: str,rehost_functions: List[Dict[str, Any]],original_search_regions: List[Dict[str, Any]]) -> Optional[str]:
    # Find a unique file-level code fragment before a rehost-only conditional block.

    containing_region = find_containing_non_function_region(block=block, rehost_source=rehost_source, rehost_functions=rehost_functions)

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
    # Store only information required by apply_transformations.py.
    transformation = {
        "id": (f"conditional_{transformation_number}"),
        "file": relative_file_path,
        "scope": block["scope"],
        "match": (block["original_branch"].strip()),
        "replacement": (block["full_text"].strip())
    }

    # Function information is required only for function-scope transformations.
    if block["scope"] == "function":
        transformation["function"] = {
            "name": block["function_name"],
            "signature": (block["function_signature"])
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
        "content": block["full_text"].strip(),
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
        "content": block["full_text"].strip(),
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

def build_report_entry(relative_file_path: str, block: Dict[str, Any], result: str, reason: str, transformation_id: Optional[str] = None) -> Dict[str, Any]:
    # Keep extraction details outside the transformation JSON.
    return {
        "result": result,
        "transformation_id": transformation_id,
        "file": relative_file_path,
        "scope": block["scope"],
        "function_name": (block["function_name"]),
        "opening_line": (block["opening_line_number"]),
        "match_text": (block["original_branch"].strip()),
        "reason": reason
    }


def extract_transformations(original_source: str, rehost_source: str, original_parse_result: Dict[str, Any], rehost_parse_result: Dict[str, Any], relative_file_path: str, starting_transformation_number: int
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    # Verify each conditional block from the old rehost file against the old original file.
    transformations = []
    report_entries = []

    original_functions = (original_parse_result["functions"])
    conditional_blocks = (rehost_parse_result["conditional_blocks"])
    transformation_candidate_blocks = [block for block in conditional_blocks if not block["is_header_guard"]]
    rehost_functions = rehost_parse_result["functions"]
    parser_warnings = (original_parse_result["warnings"] + rehost_parse_result["warnings"])

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

    for block in transformation_candidate_blocks:
        # Multiple alternative branches are not supported yet.
        if block["contains_elif"]:
            report_entries.append(
                build_report_entry(
                    relative_file_path,
                    block,
                    result="SKIPPED",
                    reason=("Conditional blocks containing #elif are not supported yet.")
                )
            )
            continue

        # Nested transformations may overlap.
        # They are skipped until overlap handling is added.
        # header girmiyor buraya. o kısım nested sayılmıyor
        if (block["contains_real_nested_conditionals"] or block["effective_nesting_depth"] > 0):
            report_entries.append(
                build_report_entry(
                    relative_file_path,
                    block,
                    result="SKIPPED",
                    reason=("The conditional block has real nested conditional structure and is not supported yet.")
                )
            )
            continue

        # if not contains #elif
        search_regions, search_error = (get_original_search_regions(block, original_source, original_functions))

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

        (selected_block, branch_selection_error) = select_matching_original_branch(block, search_regions)

        if selected_block is None:
            branch_candidates = [block.get("original_branch"), block.get("alternative_branch"),]

            branches_are_absent = all(
                (
                    not isinstance(branch_text, str)
                    or not normalize_code_text(branch_text)
                    or count_normalized_occurrences(search_regions,branch_text) == 0
                )
                for branch_text in branch_candidates
            )

            # Insertion is allowed only when neither conditional branch exists in the old original source.
            if branches_are_absent:
                insertion_position = None
                insertion_anchor = None
                fallback_position = None
                fallback_anchor = None

                if block["scope"] == "function":
                    # First try a reliable function boundary.
                    insertion_position = (determine_function_insertion_position(block=block, rehost_source=rehost_source, rehost_functions=rehost_functions))

                    # Anchors are needed only when the block is not at a reliable function boundary.
                    if insertion_position is None:
                        following_anchor = (find_unique_following_anchor(block=block, rehost_source=rehost_source, rehost_functions=rehost_functions, original_search_regions=search_regions))
                        preceding_anchor = (find_unique_preceding_anchor(block=block, rehost_source=rehost_source, rehost_functions=rehost_functions, original_search_regions=search_regions))

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
                    following_anchor = find_unique_following_non_function_anchor(block=block,rehost_source=rehost_source,rehost_functions=rehost_functions,original_search_regions=search_regions)
                    preceding_anchor = find_unique_preceding_non_function_anchor(block=block, rehost_source=rehost_source, rehost_functions=rehost_functions, original_search_regions=search_regions)

                    # Prefer the following code as the primary anchor.
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
                            reason=("Neither conditional branch exists in the old original source. The complete block "
                                f"was stored as a {insertion_position} insertion."),
                            transformation_id=transformation["id"]
                        )
                    )

                    continue

            report_entries.append(
                build_report_entry(
                    relative_file_path,
                    block,
                    result="SKIPPED",
                    reason=(
                        branch_selection_error
                        or "No unique and reliable insertion point was found."
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
                transformation_id=(transformation["id"])
            )
        )

    return transformations, report_entries


def build_support_files(rehost_only_paths: List[str], rehost_files: Dict[str, Path]
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]], List[str]]:
    # Store rehost-only source files so apply_transformations.py does not need access to the old rehost directory.
    support_files = []
    report_entries = []
    warnings = []

    for relative_file_path in rehost_only_paths:
        support_file_path = rehost_files[relative_file_path]

        try:
            content = read_support_file_content(support_file_path)

        except (OSError, UnicodeDecodeError) as error:
            reason = (f"The rehost-only file could not be stored as UTF-8 or cp1254 content: {error}")

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
                "reason": ("The file exists only in rehost, so its complete content was stored in the JSON."),
            }
        )

    return (support_files, report_entries, warnings)


def save_transformations_json(transformations: List[Dict[str, Any]], support_files: List[Dict[str, str]], output_file: Path) -> None:
    # Keep the permanent JSON small and application-focused.
    output_data = {
        "transformations": transformations,
        "support_files": support_files,
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
    detected_block_count: int, output_file: Path) -> None:
    # Create a detailed human-readable extraction report.
    created_count = sum(entry["result"] == "CREATED" for entry in report_entries)
    skipped_count = sum(entry["result"] == "SKIPPED" for entry in report_entries)

    stored_support_file_count = sum(entry["result"] == "CREATED" for entry in support_file_entries)
    skipped_support_file_count = sum(entry["result"] == "SKIPPED" for entry in support_file_entries)

    report_lines = [
        "REHOST TRANSFORMATION EXTRACTION REPORT",
        "=" * 40,
        "",
        "SUMMARY",
        "-------",
        f"Detected conditional blocks: {detected_block_count}",
        f"Created transformations: {created_count}",
        f"Skipped blocks: {skipped_count}",
        (f"Support files stored in JSON: {stored_support_file_count}"),
        (f"Support files skipped: {skipped_support_file_count}"),
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
                indent_text(entry["match_text"]),
                ""
            ]
        )
    report_lines.extend(
        [
            "SUPPORT FILES",
            "-------------"
        ]
    )
    if support_file_entries:
        for entry in support_file_entries:
            report_lines.extend(
                [
                    f"[{entry['result']}]",
                    f"File: {entry['file']}",
                    f"Reason: {entry['reason']}",
                    ""
                ]
            )
    else:
        report_lines.extend(
            [
                "None",
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
            report_lines.append(f"- {warning}")
    else:
        report_lines.append("None")

    report_lines.append("")

    output_file.write_text("\n".join(report_lines), encoding="utf-8")


def parse_arguments() -> argparse.Namespace:
    # Read optional command-line settings.
    parser = argparse.ArgumentParser(
        description=("Extract verified conditional compilation transformations from old original and rehost files.")
    )

    parser.add_argument(
        "--report",
        action="store_true",
        help=("Create the detailed extraction_report.txt file.")
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
    all_support_files = []
    all_support_file_entries = []
    all_warnings = []

    detected_block_count = 0
    next_transformation_number = 1

    # Files must exist at the same relative path in both directories.
    for relative_file_path in common_relative_paths:
        original_file = original_files[relative_file_path]
        rehost_file = rehost_files[relative_file_path]

        try:
            original_source = read_source_file(original_file)
            rehost_source = read_source_file(rehost_file)
            
            original_parse_result = parse_file(original_file)
            rehost_parse_result = parse_file(rehost_file)

        except (OSError, UnicodeDecodeError, ValueError) as error:
            all_warnings.append(f"{relative_file_path}: The file pair could not be processed: {error}")
            continue

        (file_transformations, file_report_entries
        ) = extract_transformations(
            original_source=original_source,
            rehost_source=rehost_source,
            original_parse_result=(original_parse_result),
            rehost_parse_result=(rehost_parse_result),
            relative_file_path=(relative_file_path),
            starting_transformation_number=(next_transformation_number)
        )

        all_transformations.extend(file_transformations)
        all_report_entries.extend(file_report_entries)

        next_transformation_number += len(file_transformations)

        detected_block_count += len(rehost_parse_result["conditional_blocks"])

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

    # Rehost-only files are complete support files rather than conditional transformations. Store their content in the JSON.
    (all_support_files, all_support_file_entries, support_file_warnings) = build_support_files(rehost_only_paths, rehost_files)

    all_warnings.extend(support_file_warnings)

    save_transformations_json(
        transformations=all_transformations,
        support_files=all_support_files,
        output_file=TRANSFORMATIONS_FILE
    )

    if arguments.report:
        save_extraction_report(
            report_entries=all_report_entries,
            support_file_entries=(all_support_file_entries),
            parser_warnings=all_warnings,
            detected_block_count=(detected_block_count),
            output_file=(EXTRACTION_REPORT_FILE)
        )
    
    print("\nTransformations written to: " f"{TRANSFORMATIONS_FILE}")
    print("Support files stored in JSON: " f"{len(all_support_files)}")

    if arguments.report:
        print("Extraction report written to: " f"{EXTRACTION_REPORT_FILE}")
    else:
        print("Extraction report was not created. Use --report to enable it.")


if __name__ == "__main__":
    main()
