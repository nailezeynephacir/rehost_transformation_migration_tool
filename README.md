# Rehost Transformation Migration Tool

A web-based tool for transferring previously implemented rehosting changes from an older version of a source project to a newer version.

## Why This Project Exists

Embedded software frequently depends on hardware-specific components such as sensors, processor registers, communication interfaces, vendor libraries, and timing functions. Rehosting adapts this software to run in a host environment, such as Windows or Linux, so that its application logic can be tested without requiring the original target hardware.

These adaptations may include:

- conditional compilation blocks such as `#ifdef REHOST_MODE`,
- host-compatible replacements for hardware-dependent operations,
- changes inside functions,
- additional include directives,
- global declarations,
- and host-side support files.

When the vendor releases a new version of the original source code, the previously implemented rehost modifications may need to be applied again. Repeating this process manually is time-consuming and error-prone, especially when the updated source contains structural or functional changes.

This project automates the safe parts of that migration process.

The tool works with three versions of a project:

- **Original:** the old, unmodified source project.
- **Rehosted:** the old project after the rehost modifications were implemented.
- **New Original:** the updated source project that should receive the compatible rehost modifications.

First, the tool compares **Original** and **Rehosted** to identify conditional-compilation transformations associated with user-selected target macros. It stores the extracted transformations in a structured JSON file.

The generated transformations can then be applied to **New Original**. A transformation is applied only when the expected file, scope, function, signature, and source fragment can be matched safely. Ambiguous or incompatible cases are skipped and explained in a report instead of being changed silently.

## Main Features

- Extracts rehost-related conditional compilation changes from C and C++ projects.
- Filters conditional blocks using user-provided target macros.
- Supports function, include, and global scopes.
- Recognizes complete `#if`, `#ifdef`, `#ifndef`, `#elif`, `#else`, and `#endif` chains.
- Transfers rehost-only support files to the generated project.
- Applies transformations only when a safe match can be established.
- Detects transformations that have already been applied.
- Skips ambiguous or incompatible transformations with an explanation.
- Generates detailed extraction and application reports.
- Preserves files that do not require modification.
- Produces a downloadable ZIP containing the generated rehost project.
- Provides a Vue-based web interface and a REST API.
- Processes extraction and application operations asynchronously.
- Protects the backend against oversized uploads, ZIP path traversal, excessive extracted sizes, and excessive archive file counts.

## How It Works

The migration process consists of two main stages:

```text
Original + Rehosted
        │
        ▼
Extract Transformations
        │
        ▼
rehost_transformations.json
        │
        ▼
New Original + Transformation JSON
        │
        ▼
Apply Transformations
        │
        ▼
Generated Rehost Project
```

### 1. Extract Transformations

The extraction stage requires:

1. the old **Original** project as a ZIP file,
2. the old **Rehosted** project as a ZIP file,
3. one or more target macro names.

Example target macros:

```text
REHOST_MODE
REHOST_BUILD
PRINT_TEST
```

A conditional block is considered relevant when at least one of its branch conditions references one of the selected target macros.

The extraction stage creates:

- `rehost_transformations.json`
- `extraction_report.txt`

The JSON file contains the transformations that may later be applied to a newer source version. It also contains the rehost-only support files detected during extraction.

The report explains which transformations were created, which blocks were skipped, and why.

### 2. Review the Extraction Result

Before applying the transformations, review:

- the extracted transformation list,
- the original and rehosted code snippets,
- the detected scopes and functions,
- the matched target macros,
- and any skipped cases in `extraction_report.txt`.

A transformation may be skipped when, for example:

- the corresponding original file is missing,
- the parser produces warnings for the file,
- a safe original branch cannot be identified,
- multiple possible matches make the result ambiguous,
- or nested target conditionals could create overlapping transformations.

### 3. Apply Transformations

The application stage requires:

1. the **New Original** project as a ZIP file,
2. the generated `rehost_transformations.json` file.

The application stage creates:

- `generated_rehost.zip`
- `application_report.txt`
- individually downloadable generated files

The New Original project is copied first. The tool then attempts to apply each transformation to the copied project.

Each result is reported using one of the following statuses:

- **Applied:** the transformation was matched and applied successfully.
- **Already Applied:** the expected rehost code was already present.
- **Skipped:** the transformation could not be applied safely.

> [!IMPORTANT]
> Corresponding files must use the same relative paths in the Original, Rehosted, and New Original projects.
>
> For the simplest result, ZIP the contents of each project instead of placing them inside differently named parent directories.

## Example Scenario

Suppose the Original project contains:

```c
int add(int a, int b)
{
    uint8_t value1 = *VALUE_ADDRESS_1;
    uint8_t value2 = *VALUE_ADDRESS_2;

    return a * value2 + b * value1;
}
```

The Rehosted project contains:

```c
int add(int a, int b)
{
#ifndef REHOST_MODE
    uint8_t value1 = *VALUE_ADDRESS_1;
    uint8_t value2 = *VALUE_ADDRESS_2;
#else
    uint8_t value1 = 10;
    uint8_t value2 = 20;
#endif

    return a * value2 + b * value1;
}
```

If the same original source fragment can still be found safely inside the corresponding function in New Original, the tool can automatically transfer the conditional block.

If the function is missing, its signature has changed, the expected code has been modified, or the match is ambiguous, the transformation is skipped and recorded in the application report.

## Supported Files

The extraction engine parses the following C and C++ source extensions:

```text
.c
.h
.cc
.cpp
.cxx
.hh
.hpp
.hxx
```

The following rehost-only files can be stored and transferred as support files:

```text
.py
.sh
.bat
.cmd
.ps1
.json
.yaml
.yml
.toml
.cmake
CMakeLists.txt
Makefile
```

Source and support files are read using UTF-8 when possible, with CP1254 used as a fallback.

## Technology Stack

### Backend

- Python
- FastAPI
- Uvicorn
- Pydantic Settings

### Frontend

- Vue 3
- TypeScript
- Vite
- Tailwind CSS
- Axios
- Vue Router

### Communication

- REST API
- Multipart file uploads
- Asynchronous run processing
- Run-status polling

## Prerequisites

Before running the project, install:

- Python 3.10 or newer
- Node.js `20.19+` or `22.12+`
- npm

You can check the installed versions with:

```bash
python --version
node --version
npm --version
```

## Installation and Local Development

Download or clone the repository, then open two terminals in the project root.

One terminal will run the backend, and the other will run the frontend.

## Running the Backend

### Windows PowerShell

From the project root:

```powershell
cd backend

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install -r ..\requirements.txt
python -m uvicorn app.main:app --reload
```

If PowerShell prevents virtual-environment activation, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### macOS or Linux

From the project root:

```bash
cd backend

python3 -m venv .venv
source .venv/bin/activate

python -m pip install -r ../requirements.txt
python -m uvicorn app.main:app --reload
```

When the backend starts successfully, it will be available at:

- API: `http://127.0.0.1:8000`
- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- Health check: `http://127.0.0.1:8000/health`

A successful health-check response looks like:

```json
{
  "status": "ok"
}
```

## Running the Frontend

Open a second terminal and run:

```bash
cd frontend
npm ci
npm run dev
```

If `npm ci` cannot be used because the lock file is unavailable or incompatible, use:

```bash
npm install
npm run dev
```

The frontend will normally be available at:

```text
http://localhost:5173
```

Open this address in a web browser.

## Frontend API Configuration

The frontend uses the following backend address by default:

```text
http://localhost:8000
```

To use a different backend address, create a file named `.env.local` inside the `frontend` directory:

```env
VITE_API_BASE_URL=http://localhost:8000
```

Restart the frontend development server after changing this file.

## Using the Web Interface

### Extraction

1. Open the **Extract** page.
2. Select the Original project ZIP.
3. Select the Rehosted project ZIP.
4. enter at least one target macro, such as `REHOST_MODE`.
5. Start extraction.
6. Wait for the run to complete.
7. Review the transformation results and skipped cases.
8. Download:
   - `rehost_transformations.json`
   - `extraction_report.txt`

### Application

1. Open the **Apply** page.
2. Select the New Original project ZIP.
3. Select the previously generated `rehost_transformations.json`.
4. Start application.
5. Wait for the run to complete.
6. Review the Applied, Already Applied, and Skipped results.
7. Download:
   - `generated_rehost.zip`
   - `application_report.txt`

The generated project should be compiled, tested, and reviewed before being used.

## API Overview

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Checks whether the API is available. |
| `POST` | `/extract` | Starts a transformation-extraction run. |
| `POST` | `/apply` | Starts a transformation-application run. |
| `GET` | `/runs/{run_id}` | Returns the current status and results of a run. |
| `GET` | `/runs/{run_id}/artifacts` | Lists the artifacts generated by a run. |
| `GET` | `/runs/{run_id}/artifacts/{artifact_name}` | Downloads a generated artifact. |

### Extract Request

`POST /extract` expects multipart form data containing:

| Field | Type | Description |
| --- | --- | --- |
| `original` | ZIP file | Old unmodified project. |
| `rehost` | ZIP file | Old rehosted project. |
| `target_macros` | String list | Target preprocessor macros. |

### Apply Request

`POST /apply` expects multipart form data containing:

| Field | Type | Description |
| --- | --- | --- |
| `new_original` | ZIP file | Updated original project. |
| `transformations` | JSON file | Transformation file generated during extraction. |

Both endpoints return a run ID immediately:

```json
{
  "run_id": "example123456",
  "status": "queued"
}
```

The client can then poll:

```text
GET /runs/{run_id}
```

Possible run states are:

```text
queued
running
completed
failed
```

## Generated Artifacts

### Extraction Artifacts

| Artifact | Description |
| --- | --- |
| `rehost_transformations.json` | Machine-readable transformation definitions and support files. |
| `extraction_report.txt` | Human-readable extraction results and skipped-case explanations. |

### Application Artifacts

| Artifact | Description |
| --- | --- |
| `generated_rehost.zip` | Complete generated rehost project. |
| `application_report.txt` | Detailed application results and reasons. |
| Individual generated files | Files from the generated project that can be downloaded separately. |

## Configuration

Backend settings can be overridden using environment variables prefixed with `REHOST_`.

| Variable | Default | Description |
| --- | ---: | --- |
| `REHOST_RUN_RETENTION_HOURS` | `24` | Number of hours run data is retained. |
| `REHOST_MAX_UPLOAD_SIZE_MB` | `200` | Maximum compressed upload size in megabytes. |
| `REHOST_MAX_EXTRACTED_SIZE_MB` | `500` | Maximum total extracted archive size in megabytes. |
| `REHOST_MAX_ARCHIVE_FILE_COUNT` | `5000` | Maximum number of entries allowed in an archive. |

For example, in Windows PowerShell:

```powershell
$env:REHOST_MAX_UPLOAD_SIZE_MB = "100"
python -m uvicorn app.main:app --reload
```

On macOS or Linux:

```bash
export REHOST_MAX_UPLOAD_SIZE_MB=100
python -m uvicorn app.main:app --reload
```

Run data is stored temporarily under:

```text
backend/runtime/runs
```

Runs are retained for 24 hours by default. The backend periodically removes expired run directories.

## Project Structure

```text
.
├── backend/
│   └── app/
│       ├── api/
│       │   └── routes/              # HTTP endpoints
│       ├── core/                    # Configuration and error handling
│       ├── engine/                  # Active migration algorithms
│       │   ├── parser.py
│       │   ├── transformation_matching.py
│       │   ├── extraction.py
│       │   └── application.py
│       ├── schemas/                 # API request and response models
│       ├── services/                # Upload, run and artifact workflows
│       └── main.py                  # FastAPI application entry point
├── frontend/
│   ├── src/
│   │   ├── api/                     # Backend API client
│   │   ├── components/              # Reusable Vue components
│   │   ├── composables/             # Run-polling logic
│   │   ├── router/                  # Frontend routes
│   │   ├── types/                   # TypeScript API types
│   │   ├── utils/                   # Frontend utilities
│   │   └── views/                   # Extract, Apply and Story pages
│   ├── package.json
│   └── vite.config.ts
├── legacy/
│   └── standalone_algorithm/        # Earlier standalone implementation
├── test_cases/                       # Example migration scenarios
├── original/                         # Small example Original project
├── rehost/                           # Small example Rehosted project
├── new_original/                     # Small example New Original project
├── requirements.txt                  # Backend dependencies
└── README.md
```

The web application uses the algorithms under:

```text
backend/app/engine
```

The files under `legacy/standalone_algorithm` are retained as a reference to the earlier standalone implementation and are not used by the web application.

## Safety Model

The migration engine follows a conservative approach.

A transformation is applied only when the expected context can be verified. Depending on its scope, this verification may include:

- the expected relative file path,
- the function name,
- the normalized function signature,
- the expected source fragment,
- the conditional branch content,
- the transformation scope,
- and the number of matching occurrences.

Ambiguous matches outside a verified function scope are skipped.

The application stage works on a copied version of New Original and produces a separate generated project. The uploaded New Original archive is not modified directly.

The backend also protects uploaded archives by checking:

- compressed upload size,
- total extracted size,
- archive entry count,
- paths that attempt to escape the extraction directory,
- and requested artifact paths.

## Limitations

- The project uses a custom C/C++ parser rather than a complete compiler frontend.
- Complex or unusual C/C++ syntax may produce parser warnings.
- Transformations are based on conditional-compilation differences associated with selected target macros.
- Corresponding files must preserve compatible relative paths.
- Function-scoped transformations require the expected function context.
- Changed signatures or changed source fragments may cause transformations to be skipped.
- Nested target conditionals that could produce overlapping transformations are skipped.
- The tool cannot determine whether the resulting project is semantically correct.
- Generated output must still be compiled, tested, and reviewed.
- Hardware behavior and target-system compatibility must be validated separately.

## Testing

The `test_cases` directory contains example scenarios for cases such as:

- missing files,
- missing functions,
- changed function signatures,
- missing source fragments,
- multiple matches,
- already applied transformations,
- mixed Applied and Skipped results,
- support files,
- nested conditionals,
- and real-project source examples.

These cases can be packaged as ZIP files and used through the web interface to test extraction and application behavior.

## Important Note

This tool assists with transferring rehost modifications, but it does not replace:

- compilation,
- static analysis,
- automated testing,
- code review,
- hardware-in-the-loop testing,
- or validation on the target platform.

Every generated project should be reviewed and tested before use.

## Contributors

- [Naile Zeynep Hacır](https://github.com/nailezeynephacir)
- [Eylül Öztürk](https://github.com/lulye)
- [Mustafa Batu Demir](https://github.com/Batsy18)

This project was developed collaboratively during an internship project at ASELSAN.
