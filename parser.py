from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple


# Preprocessor directive patterns used by the conditional block parser.
OPENING_DIRECTIVE_PATTERN = re.compile(
    r"^[ \t]*#[ \t]*(if|ifdef|ifndef)\b(.*)$"
)

ELIF_DIRECTIVE_PATTERN = re.compile(
    r"^[ \t]*#[ \t]*elif\b(.*)$"
)

ELSE_DIRECTIVE_PATTERN = re.compile(
    r"^[ \t]*#[ \t]*else\b"
)

ENDIF_DIRECTIVE_PATTERN = re.compile(
    r"^[ \t]*#[ \t]*endif\b"
)

INCLUDE_DIRECTIVE_PATTERN = re.compile(
    r"^[ \t]*#[ \t]*include\b"
)

# These constructs may contain parentheses and braces,
# but they are not function definitions.
CONTROL_KEYWORDS = {
    "if",
    "for",
    "while",
    "switch",
    "catch",
}


def mask_source_content(
    content: str,
    mask_literals: bool
) -> str:
    # Mask comments and optionally mask string and character literals.
    #
    # Newline characters and source length are preserved so character
    # positions remain aligned with the original source code.
    masked_chars = list(content)

    state = "NORMAL"
    index = 0

    while index < len(content):
        char = content[index]

        next_char = (
            content[index + 1]
            if index + 1 < len(content)
            else ""
        )

        if state == "NORMAL":
            if char == "/" and next_char == "/":
                masked_chars[index] = " "
                masked_chars[index + 1] = " "

                state = "LINE_COMMENT"
                index += 2
                continue

            if char == "/" and next_char == "*":
                masked_chars[index] = " "
                masked_chars[index + 1] = " "

                state = "BLOCK_COMMENT"
                index += 2
                continue

            if char == '"':
                if mask_literals:
                    masked_chars[index] = " "

                state = "STRING"
                index += 1
                continue

            if char == "'":
                if mask_literals:
                    masked_chars[index] = " "

                state = "CHAR"
                index += 1
                continue

            index += 1
            continue

        if state == "LINE_COMMENT":
            if char == "\n":
                state = "NORMAL"
            else:
                masked_chars[index] = " "

            index += 1
            continue

        if state == "BLOCK_COMMENT":
            if char == "*" and next_char == "/":
                masked_chars[index] = " "
                masked_chars[index + 1] = " "

                state = "NORMAL"
                index += 2
                continue

            if char not in "\r\n":
                masked_chars[index] = " "

            index += 1
            continue

        if state in {"STRING", "CHAR"}:
            closing_character = (
                '"'
                if state == "STRING"
                else "'"
            )

            if char == "\\":
                if mask_literals:
                    masked_chars[index] = " "

                    if (
                        index + 1 < len(content)
                        and content[index + 1] not in "\r\n"
                    ):
                        masked_chars[index + 1] = " "

                index += 2
                continue

            if mask_literals and char not in "\r\n":
                masked_chars[index] = " "

            if char == closing_character:
                state = "NORMAL"

            index += 1
            continue

    return "".join(masked_chars)


def mask_comments_and_literals(
    content: str
) -> str:
    # Mask comments, strings, and character literals.
    return mask_source_content(
        content,
        mask_literals=True
    )

def mask_comments(
    content: str
) -> str:
    # Mask only comments while preserving string and character literals.
    return mask_source_content(
        content,
        mask_literals=False
    )


def extract_function_name(
    signature: str
) -> Optional[str]:
    # Find top-level opening parentheses in the signature.
    # The identifier before the last suitable parenthesis is normally
    # the function name.
    cleaned_signature = mask_comments_and_literals(
        signature
    )

    parenthesis_depth = 0
    top_level_openings = []

    for index, char in enumerate(cleaned_signature):
        if char == "(":
            if parenthesis_depth == 0:
                top_level_openings.append(
                    index
                )

            parenthesis_depth += 1

        elif char == ")":
            parenthesis_depth = max(
                parenthesis_depth - 1,
                0
            )

    for opening_index in reversed(
        top_level_openings
    ):
        prefix = cleaned_signature[
            :opening_index
        ]

        name_match = re.search(
            r"([A-Za-z_][A-Za-z0-9_]*)\s*$",
            prefix
        )

        if name_match is None:
            continue

        function_name = name_match.group(1)

        if function_name not in CONTROL_KEYWORDS:
            return function_name

    return None


def find_signature_start_index(
    text: str
) -> int:
    # A function signature starts after the latest completed declaration
    # or preprocessor line in the current top-level source region.
    last_semicolon = text.rfind(";")
    last_preprocessor_line_end = -1

    current_index = 0

    for line in text.splitlines(
        keepends=True
    ):
        if line.lstrip().startswith("#"):
            last_preprocessor_line_end = (
                current_index + len(line)
            )

        current_index += len(line)

    return max(
        last_semicolon + 1,
        last_preprocessor_line_end
    )


def has_top_level_assignment(
    text: str
) -> bool:
    # Detect assignments outside parentheses.
    # This helps avoid treating a lambda or an initializer as a function.
    cleaned_text = mask_comments_and_literals(
        text
    )

    parenthesis_depth = 0

    for char in cleaned_text:
        if char == "(":
            parenthesis_depth += 1

        elif char == ")":
            parenthesis_depth = max(
                parenthesis_depth - 1,
                0
            )

        elif (
            char == "="
            and parenthesis_depth == 0
        ):
            return True

    return False


def find_function_regions(
    content: str
) -> Tuple[
    List[Dict[str, Any]],
    List[str]
]:
    # Find ordinary function definitions by tracking top-level braces.
    # The parser is conservative and does not attempt to understand
    # every possible C++ construct.
    masked_content = mask_comments_and_literals(
        content
    )

    functions = []
    warnings = []

    brace_depth = 0
    last_top_level_boundary = 0
    current_function = None

    index = 0

    while index < len(masked_content):
        char = masked_content[index]

        if char == "{":
            if brace_depth == 0:
                prefix = content[
                    last_top_level_boundary:index
                ]

                relative_signature_start = (
                    find_signature_start_index(
                        prefix
                    )
                )

                signature_start = (
                    last_top_level_boundary
                    + relative_signature_start
                )

                signature = content[
                    signature_start:index
                ]

                normalized_signature = re.sub(
                    r"\s+",
                    " ",
                    signature
                ).strip()

                function_name = (
                    extract_function_name(
                        signature
                    )
                )

                if (
                    function_name is not None
                    and "(" in normalized_signature
                    and not has_top_level_assignment(
                        normalized_signature
                    )
                ):
                    current_function = {
                        "name": function_name,
                        "signature": (
                            signature.strip()
                        ),
                        "normalized_signature": (
                            normalized_signature
                        ),
                        "start": signature_start,
                        "body_start": index,
                    }

                else:
                    current_function = None

            brace_depth += 1
            index += 1
            continue

        if char == "}":
            brace_depth -= 1

            if brace_depth < 0:
                warnings.append(
                    f"Unexpected closing brace at "
                    f"character {index}."
                )

                brace_depth = 0
                current_function = None

                last_top_level_boundary = (
                    index + 1
                )

                index += 1
                continue

            if brace_depth == 0:
                block_end = index + 1

                if current_function is not None:
                    completed_function = dict(
                        current_function
                    )

                    completed_function[
                        "body_end"
                    ] = block_end

                    completed_function[
                        "end"
                    ] = block_end

                    completed_function[
                        "content"
                    ] = content[
                        completed_function["start"]:
                        block_end
                    ]

                    functions.append(
                        completed_function
                    )

                current_function = None

                last_top_level_boundary = (
                    block_end
                )

            index += 1
            continue

        if (
            char == ";"
            and brace_depth == 0
        ):
            last_top_level_boundary = (
                index + 1
            )

        index += 1

    if brace_depth != 0:
        warnings.append(
            "The source contains unbalanced braces. "
            "Some function boundaries may be unavailable."
        )

    return functions, warnings


def remove_line_ending(
    text: str
) -> str:
    # Remove only CR and LF characters from the end of one line.
    return text.rstrip("\r\n")


def branch_contains_only_includes(
    branch_text: str
) -> bool:
    # An include branch may contain blank lines and comments,
    # but every meaningful source line must be an #include directive.
    masked_branch = mask_comments_and_literals(
        branch_text
    )

    meaningful_lines = []

    for line in masked_branch.splitlines():
        stripped_line = line.strip()

        if stripped_line:
            meaningful_lines.append(
                stripped_line
            )

    if not meaningful_lines:
        return False

    return all(
        INCLUDE_DIRECTIVE_PATTERN.match(
            line
        ) is not None
        for line in meaningful_lines
    )


def find_containing_function(
    block_start: int,
    block_end: int,
    functions: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    # Return the function whose body fully contains the block.
    for function in functions:
        if (
            function["body_start"] < block_start
            and block_end
            <= function["body_end"]
        ):
            return function

    return None


def classify_conditional_scope(
    block: Dict[str, Any],
    functions: List[Dict[str, Any]]
) -> Dict[str, Optional[str]]:
    # Function scope has priority because include-like text inside a
    # function must not be classified as a file-level include block.
    containing_function = (
        find_containing_function(
            block["start"],
            block["end"],
            functions
        )
    )

    if containing_function is not None:
        return {
            "scope": "function",
            "function_name": (
                containing_function["name"]
            ),
            "function_signature": (
                containing_function[
                    "normalized_signature"
                ]
            ),
        }

    branches = [
        block["original_branch"]
    ]

    if (
        block["alternative_branch"]
        is not None
    ):
        branches.append(
            block["alternative_branch"]
        )

    if all(
        branch_contains_only_includes(
            branch
        )
        for branch in branches
    ):
        return {
            "scope": "include",
            "function_name": None,
            "function_signature": None,
        }

    return {
        "scope": "global",
        "function_name": None,
        "function_signature": None,
    }


def extract_conditional_blocks(
    content: str,
    functions: Optional[
        List[Dict[str, Any]]
    ] = None
) -> Tuple[
    List[Dict[str, Any]],
    List[str]
]:
    # Find conditional compilation blocks with a stack.
    # Stack-based parsing allows nested #if blocks to be matched
    # with the correct #endif.
    if functions is None:
        functions, function_warnings = (
            find_function_regions(
                content
            )
        )

    else:
        function_warnings = []

    blocks = []
    warnings = list(
        function_warnings
    )

    stack = []

    original_lines = content.splitlines(
        keepends=True
    )

    masked_lines = (
        mask_comments_and_literals(
            content
        ).splitlines(
            keepends=True
        )
    )

    line_start = 0

    for line_number, (
        original_line,
        masked_line
    ) in enumerate(
        zip(
            original_lines,
            masked_lines
        ),
        start=1
    ):
        directive_line = (
            remove_line_ending(
                masked_line
            )
        )

        opening_match = (
            OPENING_DIRECTIVE_PATTERN.match(
                directive_line
            )
        )

        if opening_match is not None:
            if stack:
                stack[-1][
                    "contains_nested_conditionals"
                ] = True

            stack.append(
                {
                    "directive": (
                        opening_match.group(1)
                    ),
                    "condition": (
                        opening_match.group(
                            2
                        ).strip()
                    ),
                    "opening_line": (
                        remove_line_ending(
                            original_line
                        ).strip()
                    ),
                    "start": line_start,
                    "opening_line_end": (
                        line_start
                        + len(original_line)
                    ),
                    "opening_line_number": (
                        line_number
                    ),
                    "else_start": None,
                    "else_line_end": None,
                    "else_line_number": None,
                    "elif_lines": [],
                    "nesting_depth": len(
                        stack
                    ),
                    "contains_nested_conditionals": (
                        False
                    ),
                }
            )

            line_start += len(
                original_line
            )
            continue

        if ELIF_DIRECTIVE_PATTERN.match(
            directive_line
        ):
            if not stack:
                warnings.append(
                    f"Unmatched #elif at "
                    f"line {line_number}."
                )

            else:
                stack[-1][
                    "elif_lines"
                ].append(
                    line_number
                )

            line_start += len(
                original_line
            )
            continue

        if ELSE_DIRECTIVE_PATTERN.match(
            directive_line
        ):
            if not stack:
                warnings.append(
                    f"Unmatched #else at "
                    f"line {line_number}."
                )

            elif (
                stack[-1]["else_start"]
                is not None
            ):
                warnings.append(
                    f"Duplicate #else for block "
                    f"opened at line "
                    f"{stack[-1]['opening_line_number']}."
                )

            else:
                stack[-1][
                    "else_start"
                ] = line_start

                stack[-1][
                    "else_line_end"
                ] = (
                    line_start
                    + len(original_line)
                )

                stack[-1][
                    "else_line_number"
                ] = line_number

            line_start += len(
                original_line
            )
            continue

        if ENDIF_DIRECTIVE_PATTERN.match(
            directive_line
        ):
            if not stack:
                warnings.append(
                    f"Unmatched #endif at "
                    f"line {line_number}."
                )

                line_start += len(
                    original_line
                )
                continue

            pending_block = stack.pop()

            endif_start = line_start

            endif_end = (
                line_start
                + len(
                    remove_line_ending(
                        original_line
                    )
                )
            )

            original_branch_end = (
                pending_block[
                    "else_start"
                ]
                if pending_block[
                    "else_start"
                ] is not None
                else endif_start
            )

            original_branch = content[
                pending_block[
                    "opening_line_end"
                ]:
                original_branch_end
            ].rstrip(
                "\r\n"
            )

            alternative_branch = None

            if (
                pending_block["else_start"]
                is not None
            ):
                alternative_branch = content[
                    pending_block[
                        "else_line_end"
                    ]:
                    endif_start
                ].rstrip(
                    "\r\n"
                )

            block = {
                "directive": (
                    pending_block[
                        "directive"
                    ]
                ),
                "condition": (
                    pending_block[
                        "condition"
                    ]
                ),
                "opening_line": (
                    pending_block[
                        "opening_line"
                    ]
                ),
                "closing_line": (
                    remove_line_ending(
                        original_line
                    ).strip()
                ),
                "original_branch": (
                    original_branch
                ),
                "alternative_branch": (
                    alternative_branch
                ),
                "full_text": content[
                    pending_block["start"]:
                    endif_end
                ],
                "start": (
                    pending_block[
                        "start"
                    ]
                ),
                "end": endif_end,
                "opening_line_number": (
                    pending_block[
                        "opening_line_number"
                    ]
                ),
                "else_line_number": (
                    pending_block[
                        "else_line_number"
                    ]
                ),
                "closing_line_number": (
                    line_number
                ),
                "nesting_depth": (
                    pending_block[
                        "nesting_depth"
                    ]
                ),
                "contains_nested_conditionals": (
                    pending_block[
                        "contains_nested_conditionals"
                    ]
                ),
                "contains_elif": bool(
                    pending_block[
                        "elif_lines"
                    ]
                ),
                "has_else": (
                    pending_block[
                        "else_start"
                    ] is not None
                ),
            }

            block.update(
                classify_conditional_scope(
                    block,
                    functions
                )
            )

            blocks.append(
                block
            )

            line_start += len(
                original_line
            )
            continue

        line_start += len(
            original_line
        )

    for pending_block in stack:
        warnings.append(
            f"Conditional block opened at line "
            f"{pending_block['opening_line_number']} "
            f"does not have a matching #endif."
        )

    blocks.sort(
        key=lambda block: block["start"]
    )

    return blocks, warnings


def parse_source(
    content: str
) -> Dict[str, Any]:
    # Run the two small parsing stages required by this project.
    functions, function_warnings = (
        find_function_regions(
            content
        )
    )

    conditional_blocks, conditional_warnings = (
        extract_conditional_blocks(
            content,
            functions=functions
        )
    )

    return {
        "functions": functions,
        "conditional_blocks": (
            conditional_blocks
        ),
        "warnings": (
            function_warnings
            + conditional_warnings
        ),
    }


def parse_file(
    file_path: Path
) -> Dict[str, Any]:
    # Read and parse one C or C++ source file.
    if not file_path.exists():
        raise FileNotFoundError(
            f"Source file was not found: "
            f"{file_path}"
        )

    content = file_path.read_text(
        encoding="utf-8"
    )

    return parse_source(content)