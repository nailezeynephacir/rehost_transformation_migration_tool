// Pulled out as a pure function (raw string in, array or null out) rather
// than embedded directly in a Vue watcher, specifically so this can be
// unit tested without needing a browser or a real File object.
export function parseTargetMacrosFromJson(rawText: string): string[] | null {
    let data: unknown;
  
    try {
      data = JSON.parse(rawText);
    } catch {
      return null;
    }
  
    if (typeof data !== "object" || data === null) return null;
  
    const macros = (data as Record<string, unknown>).target_macros;
  
    if (!Array.isArray(macros)) return null;
    if (!macros.every((item) => typeof item === "string")) return null;
    if (macros.length === 0) return null;
  
    return macros;
  }