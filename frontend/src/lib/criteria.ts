import type { EligibilityRuleIn, EligibilityRuleOut } from "../api/types";

const LABELS: Record<string, string> = {
  cgpa_min: "CGPA ≥",
  cgpa_max: "CGPA ≤",
  backlog_max: "Active backlogs ≤",
  departments: "Departments",
  batch_years: "Pass-out years",
  skill_min_match: "Skill match ≥",
  age_max: "Max age",
  gender: "Gender",
  percentile_min: "Percentile ≥",
};

export function criterionLabel(type: string): string {
  return LABELS[type] ?? type.replace(/_/g, " ");
}

/** Local helper used by parseRuleFromInput to convert a raw boxed value. */

export function describeRule(r: EligibilityRuleIn | EligibilityRuleOut): string {
  const p = r.parameters;
  switch (r.criterion_type) {
    case "cgpa_min":
    case "cgpa_max":
    case "percentile_min":
    case "skill_min_match":
      return `${criterionLabel(r.criterion_type)} ${String(p.value ?? p.min ?? "")}`;
    case "backlog_max":
      return `Active backlogs ≤ ${String(p.active_backlogs ?? p.value ?? 0)}`;
    case "departments": {
      const depts = Array.isArray(p.departments) ? (p.departments as string[]) : [];
      return `Departments: ${depts.join(", ") || "—"}`;
    }
    case "batch_years": {
      const years = Array.isArray(p.years) ? (p.years as number[]) : [];
      return `Pass-out years: ${years.join(", ") || "—"}`;
    }
    case "age_max":
      return `Age ≤ ${String(p.value ?? "")}`;
    case "gender": {
      const allowed = Array.isArray(p.allowed) ? (p.allowed as string[]) : [];
      return `Gender: ${allowed.join(", ") || "—"}`;
    }
    default:
      return JSON.stringify(p) || criterionLabel(r.criterion_type);
  }
}

export function emptyRuleFor(type: string): EligibilityRuleIn {
  switch (type) {
    case "departments":
      return { criterion_type: type, parameters: { departments: [] } };
    case "batch_years":
      return { criterion_type: type, parameters: { years: [] } };
    case "gender":
      return { criterion_type: type, parameters: { allowed: [] } };
    case "backlog_max":
      return { criterion_type: type, parameters: { active_backlogs: 0 } };
    default:
      return { criterion_type: type, parameters: { value: 0 } };
  }
}

export function parseRuleFromInput(type: string, raw: string): EligibilityRuleIn {
  switch (type) {
    case "departments":
      return {
        criterion_type: type,
        parameters: {
          departments: raw
            .split(",")
            .map((s) => s.trim().toUpperCase())
            .filter(Boolean),
        },
      };
    case "batch_years":
      return {
        criterion_type: type,
        parameters: {
          years: raw
            .split(",")
            .map((s) => parseInt(s.trim(), 10))
            .filter((n) => !isNaN(n)),
        },
      };
    case "gender":
      return {
        criterion_type: type,
        parameters: {
          allowed: raw
            .split(",")
            .map((s) => s.trim().toLowerCase())
            .filter(Boolean),
        },
      };
    case "backlog_max":
      return { criterion_type: type, parameters: { active_backlogs: parseInt(raw, 10) || 0 } };
    default:
      return { criterion_type: type, parameters: { value: parseFloat(raw) || 0 } };
  }
}

export function ruleToInputValue(r: EligibilityRuleIn | EligibilityRuleOut): string {
  const p = r.parameters;
  switch (r.criterion_type) {
    case "departments":
      return Array.isArray(p.departments) ? (p.departments as string[]).join(", ") : "";
    case "batch_years":
      return Array.isArray(p.years) ? (p.years as number[]).join(", ") : "";
    case "gender":
      return Array.isArray(p.allowed) ? (p.allowed as string[]).join(", ") : "";
    case "backlog_max":
      return String(p.active_backlogs ?? p.value ?? 0);
    default:
      return String(p.value ?? "");
  }
}