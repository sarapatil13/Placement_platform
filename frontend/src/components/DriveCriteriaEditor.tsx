import type { CriterionType, EligibilityRuleIn } from "../api/types";
import { Button, Field, Input, Select, Tag } from "./ui";
import { criterionLabel, describeRule, emptyRuleFor, parseRuleFromInput, ruleToInputValue } from "../lib/criteria";

const CRITERION_TYPES = [
  "cgpa_min",
  "cgpa_max",
  "backlog_max",
  "departments",
  "batch_years",
  "age_max",
  "gender",
  "percentile_min",
] as const;

interface Props {
  value: EligibilityRuleIn[];
  onChange: (rules: EligibilityRuleIn[]) => void;
  placeholder?: string;
}

const PLACEHOLDERS: Record<string, string> = {
  cgpa_min: "e.g. 7.0",
  cgpa_max: "e.g. 9.0",
  backlog_max: "e.g. 1",
  departments: "CSE, ISE, AIML",
  batch_years: "2026, 2027",
  age_max: "e.g. 28",
  gender: "female, male",
  percentile_min: "e.g. 75",
};

export function DriveCriteriaEditor({ value, onChange }: Props) {
  function update(i: number, next: EligibilityRuleIn) {
    onChange(value.map((r, idx) => (idx === i ? next : r)));
  }

  function remove(i: number) {
    onChange(value.filter((_: EligibilityRuleIn, idx: number) => idx !== i));
  }

  function add(type: CriterionType) {
    onChange([...value, emptyRuleFor(type)]);
  }

  return (
    <div className="stack">
      {value.length === 0 ? (
        <p className="rule-note mb-0">No criteria configured. Applications will be allowed without an eligibility gate.</p>
      ) : (
        value.map((rule, i) => (
          <div className="row" key={i}>
            <Select
              style={{ maxWidth: 190 }}
              value={rule.criterion_type}
              onChange={(e) => {
                const t = e.target.value as CriterionType;
                update(i, emptyRuleFor(t));
              }}
            >
              {CRITERION_TYPES.map((t) => (
                <option key={t} value={t}>
                  {criterionLabel(t)}
                </option>
              ))}
            </Select>
            <div style={{ flex: 1, minWidth: 200 }}>
              <Input
                value={ruleToInputValue(rule)}
                placeholder={PLACEHOLDERS[rule.criterion_type] ?? ""}
                onChange={(e) => update(i, parseRuleFromInput(rule.criterion_type, e.target.value))}
              />
            </div>
            <Tag tone="neutral">{describeRule(rule)}</Tag>
            <Button variant="danger" className="btn-sm" onClick={() => remove(i)}>
              Remove
            </Button>
          </div>
        ))
      )}
      <div className="row">
        <Field label="Add criterion">
          <Button
            variant="secondary"
            className="btn-sm"
            onClick={() => add("cgpa_min")}
          >
            + CGPA min
          </Button>
        </Field>
        <Field label="">
          <Button variant="secondary" className="btn-sm" onClick={() => add("backlog_max")}>
            + Backlog max
          </Button>
        </Field>
        <Field label="">
          <Button variant="secondary" className="btn-sm" onClick={() => add("departments")}>
            + Departments
          </Button>
        </Field>
        <Field label="">
          <Button variant="secondary" className="btn-sm" onClick={() => add("batch_years")}>
            + Batch years
          </Button>
        </Field>
      </div>
    </div>
  );
}