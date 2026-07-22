from parser import parse_source


def print_conditional_blocks(title: str, content: str) -> None:
    print(f"\n{'=' * 60}")
    print(title)
    print("=" * 60)

    result = parse_source(content)

    for block in result["conditional_blocks"]:
        print(
            {
                "condition": block["condition"],
                "nesting_depth": block["nesting_depth"],
                "effective_nesting_depth": block[
                    "effective_nesting_depth"
                ],
                "is_header_guard": block["is_header_guard"],
                "inside_header_guard": block[
                    "inside_header_guard"
                ],
                "contains_nested_conditionals": block[
                    "contains_nested_conditionals"
                ],
                "contains_real_nested_conditionals": block[
                    "contains_real_nested_conditionals"
                ],
            }
        )

    if result["warnings"]:
        print("Warnings:")

        for warning in result["warnings"]:
            print(f"- {warning}")


content_1 = """
#ifndef SENSOR_H
#define SENSOR_H

#ifdef REHOST_MODE
#include "rehost_sensor.h"
#endif

#endif
"""

print_conditional_blocks(
    "Header guard içindeki normal conditional",
    content_1,
)



content_2 = """
#ifndef SENSOR_H
#define SENSOR_H

#ifdef REHOST_MODE

#ifdef WINDOWS
int value = 10;
#endif

#endif

#endif
"""

print_conditional_blocks(
    "Header guard içindeki gerçek nested conditional",
    content_2,
)

content_3 = """
#ifdef FEATURE_A

#ifdef FEATURE_B
int value = 10;
#endif

#endif
"""

print_conditional_blocks(
    "Header guard olmadan gerçek nesting",
    content_3,
)


content_4 = """
int global_value = 5;

#ifndef FEATURE_ENABLED
#define FEATURE_ENABLED

int another_value = 10;

#endif
"""

print_conditional_blocks(
    "Dosyanın ortasındaki ifndef",
    content_4,
)


old_header = """
#ifndef OLD_SENSOR_H
#define OLD_SENSOR_H

#ifdef REHOST_MODE
int old_value;
#endif

#endif
"""

new_header = """
#ifndef NEW_SENSOR_DRIVER_H
#define NEW_SENSOR_DRIVER_H

#ifdef REHOST_MODE
int old_value;
#endif

#endif
"""

print_conditional_blocks(
    "Eski header",
    old_header,
)

print_conditional_blocks(
    "Yeni header",
    new_header,
)
