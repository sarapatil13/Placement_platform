import type { DriveRoundIn, RoundType } from "../api/types";
import { Button, Field, Input, Select } from "./ui";

export const ROUND_TYPE_LABELS: Record<RoundType, string> = {
  online_assessment: "Online assessment",
  technical_interview: "Technical interview",
  hr_interview: "HR interview",
  group_discussion: "Group discussion",
  other: "Other",
};

const ROUND_TYPES = Object.keys(ROUND_TYPE_LABELS) as RoundType[];

interface Props {
  value: DriveRoundIn[];
  onChange: (rounds: DriveRoundIn[]) => void;
}

function emptyRound(position: number): DriveRoundIn {
  return { position, round_type: "online_assessment", title: "", topics: [] };
}

export function DriveRoundsEditor({ value, onChange }: Props) {
  function update(index: number, patch: Partial<DriveRoundIn>) {
    onChange(value.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  }

  function remove(index: number) {
    onChange(value.filter((_, i) => i !== index).map((r, i) => ({ ...r, position: i + 1 })));
  }

  function add() {
    onChange([...value, emptyRound(value.length + 1)]);
  }

  return (
    <div className="stack">
      {value.length === 0 ? (
        <p className="rule-note mb-0">No rounds defined yet.</p>
      ) : (
        value.map((round, i) => (
          <div className="row" key={i} style={{ alignItems: "flex-start" }}>
            <Select
              style={{ maxWidth: 190 }}
              value={round.round_type}
              onChange={(e) => update(i, { round_type: e.target.value as RoundType })}
            >
              {ROUND_TYPES.map((t) => (
                <option key={t} value={t}>
                  {ROUND_TYPE_LABELS[t]}
                </option>
              ))}
            </Select>
            <div style={{ flex: 1, minWidth: 160 }}>
              <Input
                placeholder="Round title"
                value={round.title}
                onChange={(e) => update(i, { title: e.target.value })}
              />
            </div>
            <div style={{ flex: 1, minWidth: 200 }}>
              <Input
                placeholder="Topics (comma separated)"
                value={round.topics.join(", ")}
                onChange={(e) =>
                  update(i, {
                    topics: e.target.value
                      .split(",")
                      .map((s) => s.trim())
                      .filter(Boolean),
                  })
                }
              />
            </div>
            <Input
              type="datetime-local"
              style={{ maxWidth: 210 }}
              value={round.scheduled_at ? round.scheduled_at.slice(0, 16) : ""}
              onChange={(e) => update(i, { scheduled_at: e.target.value || undefined })}
            />
            <Button variant="danger" className="btn-sm" onClick={() => remove(i)}>
              Remove
            </Button>
          </div>
        ))
      )}
      <div className="row">
        <Field label="Add round">
          <Button variant="secondary" className="btn-sm" onClick={add}>
            + Round
          </Button>
        </Field>
      </div>
    </div>
  );
}
