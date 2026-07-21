from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple


# Preprocessor directive patterns used by the conditional block parser.
OPENING_DIRECTIVE_PATTERN = re.compile(r"^[ \t]*#[ \t]*(if|ifdef|ifndef)\b(.*)$")
ELIF_DIRECTIVE_PATTERN = re.compile(r"^[ \t]*#[ \t]*elif\b(.*)$")
ELSE_DIRECTIVE_PATTERN = re.compile(r"^[ \t]*#[ \t]*else\b")
ENDIF_DIRECTIVE_PATTERN = re.compile(r"^[ \t]*#[ \t]*endif\b")

INCLUDE_DIRECTIVE_PATTERN = re.compile(r"^[ \t]*#[ \t]*include\b")

# These constructs may contain parentheses and braces, but they are not function definitions.
CONTROL_KEYWORDS = {
    "if",
    "for",
    "while",
    "switch",
    "catch",
}


def mask_source_content(content: str, mask_literals: bool) -> str:
    # Mask comments and optionally mask string and character literals.
    # Newline characters and source length are preserved so character positions remain aligned with the original source code.
    
    # printf("This is not a brace: }");
    # // fake directive: #endif
    # Bu tarz şeylerin yanlış yönlendirmemesi için bu gerekli.
    
    masked_chars = list(content)

    state = "NORMAL"    # parser’ın o anda kaynak kodun hangi bölümünde olduğu
    index = 0           # incelenen karakterin konumu

    # states: NORMAL, LINE_COMMENT, BLOCK_COMMENT, STRING, CHAR

    while index < len(content):
        char = content[index]

        # Bazı C yapıları iki char ile anlaşılır (//, /*, */), bu yüzden mevcut char ile sonrakini de alıyoruz.
        next_char = (content[index + 1] if index + 1 < len(content) else "")

        if state == "NORMAL":   # normal C/C++ kodu
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
                # Eğer masked_literals = True ise boşluğa dönüştürür.
                # False olurse bırakır ama state yine de STRING olur ki içindeki // falan comment sayılmasın.

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

        if state == "LINE_COMMENT":     # // comment
            # satır sonuna kadar bütün charları space yap. /n'i silme.
            if char == "\n":
                state = "NORMAL"
            else:
                masked_chars[index] = " "

            index += 1
            continue

        if state == "BLOCK_COMMENT":    # /* ... */ comment
            if char == "*" and next_char == "/":
                masked_chars[index] = " "
                masked_chars[index + 1] = " "

                state = "NORMAL"
                index += 2
                continue

            # satır sayısını bozmamak için bunlara dokunmuyoruz.
            if char not in "\r\n":
                masked_chars[index] = " "

            index += 1
            continue

        if state in {"STRING", "CHAR"}:     # STRING: "...", CHAR: '...'
            closing_character = ('"' if state == "STRING" else "'")

            if char == "\\":
                if mask_literals:
                    masked_chars[index] = " "

                    if (index + 1 < len(content) and content[index + 1] not in "\r\n"):
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
# it garantees: len(result) == len(content)


def mask_comments_and_literals(content: str) -> str:
    # Mask comments, strings, and character literals.
    return mask_source_content(content, mask_literals=True)

def mask_comments(content: str) -> str:
    # Mask only comments while preserving string and character literals.
    return mask_source_content(content, mask_literals=False)


def normalize_function_signature(signature: str) -> str:
    # Ignore comments and formatting differences while preserving whitespace that separates C tokens.
    signature_without_comments = mask_comments(signature)

    normalized_signature = re.sub(r"\s+", " ", signature_without_comments).strip()

    return re.sub(r"\s*([(),*\[\]])\s*", r"\1", normalized_signature)


def extract_function_name(signature: str) -> Optional[str]:
    # Find top-level opening parentheses in the signature.
    # The identifier before the last suitable parenthesis is normally the function name.
    cleaned_signature = mask_comments_and_literals(signature)

    parenthesis_depth = 0   # O anda kaç kat parantezin içinde olduğumuzu gösterir.
    top_level_openings = [] # En dış seviyede başlayan ( karakterlerinin indekslerini tutar.

    for index, char in enumerate(cleaned_signature):
        if char == "(":
            if parenthesis_depth == 0:
                top_level_openings.append(index)
            parenthesis_depth += 1

        elif char == ")":
            parenthesis_depth = max(parenthesis_depth - 1, 0)

    for opening_index in reversed(top_level_openings):
        prefix = cleaned_signature[:opening_index]

        name_match = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\s*$", prefix)
        # [A-Za-z_]: isim harf veya _ ile başlamalıdır.
        # [A-Za-z0-9_]*: devamında harf, rakam veya _ bulunabilir.
        # \s*: ardından boşluk olabilir.
        # $: identifier, prefix’in sonundaki isim olmalıdır.

        if name_match is None:
            continue

        function_name = name_match.group(1)

        if function_name not in CONTROL_KEYWORDS:
            return function_name

    # static int calculate_sum (int a, int b) -----> calculate_sum
    return None


def find_signature_start_index(text: str) -> int:
    # A function signature starts after the latest completed declaration or preprocessor line in the current top-level source region.
    last_semicolon = text.rfind(";")
    last_preprocessor_line_end = -1

    current_index = 0

    # definelar ";" ile bitmiyor o yüzden onlara ayrı bakıp satır sonlarını alıyoruz.
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("#"):
            last_preprocessor_line_end = (current_index + len(line))

        current_index += len(line)

    # iki olasıdan daha ileride olan seçilir: son ; ya da son preprocessor satırının sonu
    return max(last_semicolon + 1, last_preprocessor_line_end)


def has_top_level_assignment(text: str) -> bool:
    # Detect assignments outside parentheses.
    # This helps avoid treating a lambda or an initializer as a function.
    # İsim, (, { buldu ama eğer = varsa bu bir atama/initializer
    cleaned_text = mask_comments_and_literals(text)

    parenthesis_depth = 0

    for char in cleaned_text:
        if char == "(":
            parenthesis_depth += 1

        elif char == ")":
            parenthesis_depth = max(parenthesis_depth - 1, 0)

        # = parantezin içinde değilse sıkıntı, o yüzden parantez derinliğine bakıyoruz.
        # parantezin içindeyse mesela void process(int value = 10) bunda sıkıntı yok.
        elif (char == "=" and parenthesis_depth == 0):
            return True
    # auto handler = [](int value) --> True --> yapı fonksiyon olarak kabul edilmez.
    return False


def find_function_regions(content: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    # Find ordinary function definitions by tracking top-level braces.
    # The parser is conservative and does not attempt to understand every possible C++ construct.

    # parser sıradan fonksiyonları kabul ederken initializer ve lambda gibi şüpheli yapıları temkinli biçimde dışarıda bırakıyor.

    masked_content = mask_comments_and_literals(content)

    # fonksiyon bu iki listeyi döndürüyor:
    functions = []      # --> name, signature, normalized_signature, start, body_start, body_end, end, content
    warnings = []       # e.g. unbalanced braces

    brace_depth = 0     # süslü parantez derinliği
    # bunun sayesinde if{} tarzı şeylere bakmıyoruz.

    last_top_level_boundary = 0 
    # Yeni bir fonksiyon imzasının aranabileceği top-level başlangıç noktasını tutar.
    # Bu sınır genelde: son ; ya da bir önceki bloğun }

    current_function = None

    index = 0

    while index < len(masked_content):
        char = masked_content[index]

        if char == "{":
            if brace_depth == 0:
                prefix = content[last_top_level_boundary:index]

                relative_signature_start = (find_signature_start_index(prefix))

                signature_start = (last_top_level_boundary + relative_signature_start)

                signature = content[signature_start:index]
                normalized_signature = (normalize_function_signature(signature))

                function_name = (extract_function_name(signature))

                if (
                    function_name is not None       # name çıkmış olmalı
                    and "(" in normalized_signature # struct{} tarzı şeylerin fonksiyon sayılmasını önler.
                    and not has_top_level_assignment(normalized_signature) # parantez dışında = olmamalı
                ):
                    current_function = {
                        "name": function_name,
                        "signature": (signature.strip()),
                        "normalized_signature": (normalized_signature),
                        "start": signature_start,
                        "body_start": index,
                    }

                else:
                    current_function = None

            brace_depth += 1    # { ister fonksiyon gövdesi ister başka bir blok olsun, süslü parantez derinliği artırılır.
            index += 1
            continue

        if char == "}":
            brace_depth -= 1

            if brace_depth < 0:
                warnings.append(f"Unexpected closing brace at character {index}.")

                brace_depth = 0
                current_function = None

                last_top_level_boundary = (index + 1)

                index += 1
                continue

            if brace_depth == 0:    # Top-level blok tamamen kapanmış.
                block_end = index + 1

                if current_function is not None:
                    completed_function = dict(current_function)

                    completed_function["body_end"] = block_end
                    completed_function["end"] = block_end
                    # İleride fonksiyon sonuna dahil edilmek istenen başka bir yapı olursa bu alanlar farklılaştırılabilir. Mevcut kodda ikisi aynıdır.
                    
                    completed_function["content"] = content[completed_function["start"]:block_end]
                    # Fonksiyon imzasının başladığı yerden kapanış } karakterinin sonrasına kadar orijinal kaynak metin alınır.
                    # Burada masked content değil de original content kullanılır.

                    functions.append(completed_function)

                current_function = None
                last_top_level_boundary = (block_end)

            index += 1
            continue

        if (char == ";" and brace_depth == 0):
            last_top_level_boundary = (index + 1)

        index += 1

    if brace_depth != 0:
        warnings.append("The source contains unbalanced braces. Some function boundaries may be unavailable.")

    return functions, warnings


def remove_line_ending(text: str) -> str:
    # Remove only CR and LF characters from the end of one line.
    return text.rstrip("\r\n")


def branch_contains_only_includes(branch_text: str) -> bool:
    # scope belirlemede kullanılacak
    # An include branch may contain blank lines and comments, but every meaningful source line must be an #include directive.
    masked_branch = mask_comments_and_literals(branch_text)

    meaningful_lines = []

    for line in masked_branch.splitlines():
        stripped_line = line.strip()

        if stripped_line:
            meaningful_lines.append(stripped_line)

    if not meaningful_lines:
        return False

    return all(INCLUDE_DIRECTIVE_PATTERN.match(line) is not None
        for line in meaningful_lines)


def find_containing_function(block_start: int, block_end: int, functions: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    # scope belirlemede kullanılacak eğer function döndürürse function scope
    # Return the function whose body fully contains the block.
    for function in functions:
        if (
            function["body_start"] < block_start
            and block_end <= function["body_end"]
        ):
            return function

    return None


def classify_conditional_scope(block: Dict[str, Any], functions: List[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    # scope types: fuction, global, include
    # scope belirleme işlemi burada
    # Function scope has priority because include-like text inside a function must not be classified as a file-level include block.
    
    # Fonksiyonun karar sırası:
    # 1. Blok bir fonksiyon gövdesinin içinde mi? Evet → function
    # 2. Değilse bütün dalları yalnızca #include mı içeriyor? Evet → include
    # 3. İkisi de değilse → global
    containing_function = (find_containing_function(block["start"], block["end"], functions))

    if containing_function is not None:
        return {
            "scope": "function",
            "function_name": (containing_function["name"]),
            "function_signature": (containing_function["normalized_signature"]),
        }

    branches = [block["original_branch"]]   # original as in first branch

    if (block["alternative_branch"] is not None):
        branches.append(block["alternative_branch"])

    if all(branch_contains_only_includes(branch) for branch in branches):
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


def extract_conditional_blocks(content: str, functions: Optional[List[Dict[str, Any]]] = None
) -> Tuple[List[Dict[str, Any]], List[str]]:
    # #if / #ifdef / #ifndef buluyor.
    # girdi olarak tüm metni ve çıkarttığımız fonksiyon listesini alıyor.
    # çıktı: conditional_blocks ve warnings

    # Find conditional compilation blocks with a stack.
    # Stack-based parsing allows nested #if blocks to be matched with the correct #endif.
    if functions is None:
        functions, function_warnings = (find_function_regions(content))

    else:
        function_warnings = []

    blocks = []     # bulunan conditional_blocks buraya eklenecek
    warnings = list(function_warnings)

    stack = []

    original_lines = content.splitlines(keepends=True)
    masked_lines = (mask_comments_and_literals(content).splitlines(keepends=True))

    line_start = 0

    # original ve masked eşleştiriliyor.
    for line_number, (original_line, masked_line) in enumerate(zip(original_lines, masked_lines), start=1):

        directive_line = (remove_line_ending(masked_line))
        opening_match = (OPENING_DIRECTIVE_PATTERN.match(directive_line))
        # #ifdef REHOST_MODE ---> opening_match.group(1)="ifdef", opening_match.group(2)= " REHOST_MODE"

        if opening_match is not None:
            if stack:   # stack boş değilse nested
                stack[-1]["contains_nested_conditionals"] = True
                # stack[-1] üstteki ifdef. ondaki nested var bilgisini true yapıyoruz

            stack.append(
                {
                    "directive": (opening_match.group(1)),
                    "condition": (opening_match.group(2).strip()),
                    "opening_line": (remove_line_ending(original_line).strip()),
                    "start": line_start,
                    "opening_line_end": (line_start + len(original_line)),
                    "opening_line_number": (line_number),
                    "else_start": None,
                    "else_line_end": None,
                    "else_line_number": None,
                    "elif_lines": [],
                    "nesting_depth": len(stack),
                    "contains_nested_conditionals": (False),
                }
            )

            line_start += len(original_line)
            continue

        if ELIF_DIRECTIVE_PATTERN.match(directive_line):
            # stack boşsa bir ifdef falan yoksa else kendi başına duruyor demek
            if not stack:
                warnings.append(f"Unmatched #elif at line {line_number}.")

            else:
                stack[-1]["elif_lines"].append(line_number)

            line_start += len(original_line)
            continue

        if ELSE_DIRECTIVE_PATTERN.match(directive_line):
            if not stack:
                warnings.append(f"Unmatched #else at line {line_number}.")

            # birden fazla else varsa error
            elif (stack[-1]["else_start"] is not None):
                warnings.append(f"Duplicate #else for block opened at line {stack[-1]['opening_line_number']}.")

            else:
                stack[-1]["else_start"] = line_start
                stack[-1]["else_line_end"] = (line_start + len(original_line))
                stack[-1]["else_line_number"] = line_number     # #else'in satır numarası

            line_start += len(original_line)
            continue

        if ENDIF_DIRECTIVE_PATTERN.match(directive_line):
            if not stack:   # stack boşsa önceden ifdef falan eklenmemiş demek
                warnings.append(f"Unmatched #endif at line {line_number}.")
                line_start += len(original_line)
                continue

            pending_block = stack.pop()     # stackten çıkar

            endif_start = line_start
            endif_end = (line_start + len(remove_line_ending(original_line)))

            original_branch_end = (
                pending_block["else_start"]
                if pending_block["else_start"] is not None
                else endif_start
            )

            # original branch ifdef'den else e kadar, else yoksa endif'e kadar
            original_branch = content[pending_block["opening_line_end"]:original_branch_end].rstrip("\r\n")
            alternative_branch = None

            # else varsa alternative branch onu tutacak.
            if (pending_block["else_start"] is not None):
                alternative_branch = content[pending_block["else_line_end"]:endif_start].rstrip("\r\n")

            block = {
                "directive": (pending_block["directive"]),
                "condition": (pending_block["condition"]),
                "opening_line": (pending_block["opening_line"]),
                "closing_line": (remove_line_ending(original_line).strip()),
                "original_branch": (original_branch),
                "alternative_branch": (alternative_branch),
                "full_text": content[pending_block["start"]:endif_end],
                "start": (pending_block["start"]),
                "end": endif_end,
                "opening_line_number": (pending_block["opening_line_number"]),
                "else_line_number": (pending_block["else_line_number"]),
                "closing_line_number": (line_number),
                "nesting_depth": (pending_block["nesting_depth"]),
                "contains_nested_conditionals": (pending_block["contains_nested_conditionals"]),
                "contains_elif": bool(pending_block["elif_lines"]),
                "has_else": (pending_block["else_start"] is not None),
            }

            block.update(classify_conditional_scope(block, functions))
            blocks.append(block)
            line_start += len(original_line)
            continue

        line_start += len(original_line)

    # en son stack boşalmadıysa kapatması unutulmuş bir ifdef var.
    for pending_block in stack:
        warnings.append(f"Conditional block opened at line {pending_block['opening_line_number']} does not have a matching #endif.")

    blocks.sort(key=lambda block: block["start"])

    return blocks, warnings


def parse_source(content: str) -> Dict[str, Any]:
    # Run the two small parsing stages required by this project.
    functions, function_warnings = (find_function_regions(content))

    conditional_blocks, conditional_warnings = (extract_conditional_blocks(content, functions=functions))

    return {
        "functions": functions,
        "conditional_blocks": (conditional_blocks),
        "warnings": (function_warnings + conditional_warnings),
    }


def parse_file(file_path: Path) -> Dict[str, Any]:
    # Read and parse one C or C++ source file.
    if not file_path.exists():
        raise FileNotFoundError(f"Source file was not found: {file_path}")

    content = file_path.read_text(encoding="utf-8")

    return parse_source(content)
