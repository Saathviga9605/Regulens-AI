import { Plus, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";

import { ACADEMIC_YEARS, APPLICATION_TYPE_LABELS, PROGRAMME_LEVEL_LABELS, SHIFT_LABELS, entries } from "../app/labels";
import { ApiError } from "../services/apiClient";
import type { ApplicationInput, ApplicationType, Institution, Programme } from "../types/api";
import { Alert, SelectField, TextField, buttonStyles } from "./ui";

interface ProgrammeDraft {
  programme_level: Programme["programme_level"] | "";
  course_name: string;
  shift: Programme["shift"];
  existing_intake: string;
  proposed_intake: string;
}

export interface ApplicationFormValues {
  institution_code: string;
  academic_year: string;
  application_type: ApplicationType | "";
  programmes: ProgrammeDraft[];
}

type Errors = Record<string, string>;

const EMPTY_PROGRAMME: ProgrammeDraft = {
  programme_level: "",
  course_name: "",
  shift: "first",
  existing_intake: "",
  proposed_intake: "",
};

export function toFormValues(input?: Partial<ApplicationInput>): ApplicationFormValues {
  return {
    institution_code: input?.institution_code ?? "",
    academic_year: input?.academic_year ?? "",
    application_type: input?.application_type ?? "",
    programmes: input?.programmes?.map((p) => ({
      ...p,
      existing_intake: String(p.existing_intake),
      proposed_intake: String(p.proposed_intake),
    })) ?? [{ ...EMPTY_PROGRAMME }],
  };
}

function parseIntake(value: string): number | null {
  if (!/^\d+$/.test(value.trim())) return null;
  const n = Number(value);
  return n <= 600 ? n : null;
}

export function validate(values: ApplicationFormValues): { errors: Errors; input?: ApplicationInput } {
  const errors: Errors = {};
  if (!values.institution_code) errors.institution_code = "Select an institution.";
  if (!values.academic_year) errors.academic_year = "Select an academic year.";
  if (!values.application_type) errors.application_type = "Select an application type.";
  if (values.programmes.length === 0) errors.programmes = "Add at least one programme.";

  const programmes: Programme[] = [];
  values.programmes.forEach((p, i) => {
    const key = `programmes.${i}`;
    if (!p.programme_level) errors[`${key}.programme_level`] = "Select a level.";
    if (p.course_name.trim().length < 2) errors[`${key}.course_name`] = "Enter the course name.";
    const existing = parseIntake(p.existing_intake);
    const proposed = parseIntake(p.proposed_intake);
    if (existing === null) errors[`${key}.existing_intake`] = "Whole number from 0 to 600.";
    if (proposed === null) errors[`${key}.proposed_intake`] = "Whole number from 0 to 600.";
    if (p.programme_level && existing !== null && proposed !== null) {
      programmes.push({ programme_level: p.programme_level, course_name: p.course_name.trim(), shift: p.shift,
        existing_intake: existing, proposed_intake: proposed });
    }
  });

  if (Object.keys(errors).length > 0 || !values.application_type) return { errors };
  return {
    errors,
    input: {
      institution_code: values.institution_code,
      academic_year: values.academic_year,
      application_type: values.application_type,
      programmes,
    },
  };
}

interface Props {
  institutions: Institution[];
  initial: ApplicationFormValues;
  submitLabel: string;
  onSubmit: (input: ApplicationInput) => Promise<void>;
  onCancel?: () => void;
}

export function ApplicationForm({ institutions, initial, submitLabel, onSubmit, onCancel }: Props) {
  const [values, setValues] = useState(initial);
  const [errors, setErrors] = useState<Errors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const set = <K extends keyof ApplicationFormValues>(key: K, value: ApplicationFormValues[K]) =>
    setValues((v) => ({ ...v, [key]: value }));
  const setProgramme = (i: number, patch: Partial<ProgrammeDraft>) =>
    setValues((v) => ({ ...v, programmes: v.programmes.map((p, j) => (j === i ? { ...p, ...patch } : p)) }));

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    const result = validate(values);
    setErrors(result.errors);
    if (!result.input) {
      setFormError("Please correct the highlighted fields.");
      return;
    }
    setSubmitting(true);
    try {
      await onSubmit(result.input);
    } catch (err) {
      if (err instanceof ApiError) {
        setErrors(err.fieldErrors);
        setFormError(err.message);
      } else {
        setFormError("Unexpected error. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  const institutionOptions: [string, string][] = institutions.map((i) => [i.institution_code, `${i.name} (${i.institution_code})`]);

  return (
    <form noValidate onSubmit={handleSubmit} className="space-y-6" aria-label="Application form">
      {formError && <Alert tone="error">{formError}</Alert>}

      <div className="grid gap-4 md:grid-cols-3">
        <SelectField
          label="Institution"
          value={values.institution_code}
          onChange={(e) => set("institution_code", e.target.value)}
          options={institutionOptions}
          placeholder="Select an institution"
          error={errors.institution_code}
          required
        />
        <SelectField
          label="Academic year"
          value={values.academic_year}
          onChange={(e) => set("academic_year", e.target.value)}
          options={ACADEMIC_YEARS.map((y) => [y, y])}
          placeholder="Select a year"
          error={errors.academic_year}
          required
        />
        <SelectField
          label="Application type"
          value={values.application_type}
          onChange={(e) => set("application_type", e.target.value as ApplicationType | "")}
          options={entries(APPLICATION_TYPE_LABELS)}
          placeholder="Select a type"
          error={errors.application_type}
          required
        />
      </div>

      <fieldset className="space-y-3">
        <legend className="text-sm font-semibold text-slate-900">Declared programmes and intake</legend>
        <p className="text-xs text-slate-500">
          Use existing intake 0 for a newly introduced course. Intake values are declarations, not verified figures.
        </p>
        {errors.programmes && <p className="text-xs text-red-700">{errors.programmes}</p>}
        {values.programmes.map((p, i) => (
          <div key={i} className="rounded-md border border-slate-200 bg-slate-50 p-4" role="group" aria-label={`Programme ${i + 1}`}>
            <div className="grid gap-3 md:grid-cols-12">
              <div className="md:col-span-2">
                <SelectField
                  label="Level"
                  value={p.programme_level}
                  onChange={(e) => setProgramme(i, { programme_level: e.target.value as ProgrammeDraft["programme_level"] })}
                  options={entries(PROGRAMME_LEVEL_LABELS)}
                  placeholder="Select"
                  error={errors[`programmes.${i}.programme_level`]}
                />
              </div>
              <div className="md:col-span-4">
                <TextField
                  label="Course name"
                  value={p.course_name}
                  maxLength={150}
                  onChange={(e) => setProgramme(i, { course_name: e.target.value })}
                  error={errors[`programmes.${i}.course_name`]}
                />
              </div>
              <div className="md:col-span-2">
                <SelectField
                  label="Shift"
                  value={p.shift}
                  onChange={(e) => setProgramme(i, { shift: e.target.value as ProgrammeDraft["shift"] })}
                  options={entries(SHIFT_LABELS)}
                />
              </div>
              <div className="md:col-span-2">
                <TextField
                  label="Existing intake"
                  inputMode="numeric"
                  value={p.existing_intake}
                  onChange={(e) => setProgramme(i, { existing_intake: e.target.value })}
                  error={errors[`programmes.${i}.existing_intake`]}
                />
              </div>
              <div className="md:col-span-2">
                <TextField
                  label="Proposed intake"
                  inputMode="numeric"
                  value={p.proposed_intake}
                  onChange={(e) => setProgramme(i, { proposed_intake: e.target.value })}
                  error={errors[`programmes.${i}.proposed_intake`]}
                />
              </div>
            </div>
            {values.programmes.length > 1 && (
              <button
                type="button"
                className={`${buttonStyles.secondary} mt-3`}
                onClick={() => set("programmes", values.programmes.filter((_, j) => j !== i))}
              >
                <Trash2 aria-hidden="true" className="h-4 w-4" /> Remove programme {i + 1}
              </button>
            )}
          </div>
        ))}
        {values.programmes.length < 20 && (
          <button
            type="button"
            className={buttonStyles.secondary}
            onClick={() => set("programmes", [...values.programmes, { ...EMPTY_PROGRAMME }])}
          >
            <Plus aria-hidden="true" className="h-4 w-4" /> Add programme
          </button>
        )}
      </fieldset>

      <div className="flex gap-2 border-t border-slate-200 pt-4">
        <button type="submit" className={buttonStyles.primary} disabled={submitting}>
          {submitting ? "Saving…" : submitLabel}
        </button>
        {onCancel && (
          <button type="button" className={buttonStyles.secondary} onClick={onCancel} disabled={submitting}>
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}
