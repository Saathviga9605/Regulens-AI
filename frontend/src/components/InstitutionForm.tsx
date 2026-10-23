import { useState, type FormEvent } from "react";

import { INSTITUTION_TYPE_LABELS, RECORD_STATUS_LABELS, entries } from "../app/labels";
import { ApiError } from "../services/apiClient";
import type { Institution, InstitutionInput, InstitutionType, InstitutionUpdate, RecordStatus } from "../types/api";
import { Alert, SelectField, TextField, buttonStyles } from "./ui";

type Values = Omit<InstitutionInput, "institution_type"> & { institution_type: InstitutionType | ""; status: RecordStatus };

const LIMITS: Record<keyof Omit<Values, "institution_type" | "status">, [number, number, string]> = {
  name: [3, 200, "Official name"],
  state: [2, 80, "State"],
  district: [2, 80, "District"],
  address: [5, 500, "Address"],
  trust_name: [3, 200, "Trust or sponsoring body"],
  property_identifier: [3, 100, "Property / survey identifier"],
};

function validate(values: Values): Record<string, string> {
  const errors: Record<string, string> = {};
  for (const [field, [min, max, label]] of Object.entries(LIMITS)) {
    const len = values[field as keyof typeof LIMITS].trim().length;
    if (len < min || len > max) errors[field] = `${label} must be ${min}–${max} characters.`;
  }
  if (!values.institution_type) errors.institution_type = "Select an institution type.";
  return errors;
}

interface Props {
  institution?: Institution;
  submitLabel: string;
  onSubmit: (input: InstitutionInput | InstitutionUpdate) => Promise<void>;
  onCancel?: () => void;
}

export function InstitutionForm({ institution, submitLabel, onSubmit, onCancel }: Props) {
  const editing = institution !== undefined;
  const [values, setValues] = useState<Values>({
    name: institution?.name ?? "",
    institution_type: institution?.institution_type ?? "",
    state: institution?.state ?? "",
    district: institution?.district ?? "",
    address: institution?.address ?? "",
    trust_name: institution?.trust_name ?? "",
    property_identifier: institution?.property_identifier ?? "",
    status: institution?.status ?? "active",
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const bind = (field: keyof typeof LIMITS) => ({
    label: LIMITS[field][2],
    value: values[field],
    maxLength: LIMITS[field][1],
    error: errors[field],
    onChange: (e: { target: { value: string } }) => setValues((v) => ({ ...v, [field]: e.target.value })),
  });

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    const found = validate(values);
    setErrors(found);
    if (Object.keys(found).length > 0 || !values.institution_type) {
      setFormError("Please correct the highlighted fields.");
      return;
    }
    const { status, ...rest } = values;
    const input: InstitutionInput = { ...rest, institution_type: values.institution_type };
    setSubmitting(true);
    try {
      await onSubmit(editing ? { ...input, status } : input);
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

  return (
    <form noValidate onSubmit={handleSubmit} className="space-y-4" aria-label="Institution form">
      {formError && <Alert tone="error">{formError}</Alert>}
      <Alert tone="info">Use fictional data only. Do not enter real institutions or personal information.</Alert>
      <div className="grid gap-4 md:grid-cols-2">
        <TextField {...bind("name")} required />
        <SelectField
          label="Institution type"
          value={values.institution_type}
          onChange={(e) => setValues((v) => ({ ...v, institution_type: e.target.value as InstitutionType | "" }))}
          options={entries(INSTITUTION_TYPE_LABELS)}
          placeholder="Select a type"
          error={errors.institution_type}
          required
        />
        <TextField {...bind("state")} required />
        <TextField {...bind("district")} required />
        <div className="md:col-span-2">
          <TextField {...bind("address")} required />
        </div>
        <TextField {...bind("trust_name")} required />
        <TextField {...bind("property_identifier")} required />
        {editing && (
          <SelectField
            label="Record status"
            value={values.status}
            onChange={(e) => setValues((v) => ({ ...v, status: e.target.value as RecordStatus }))}
            options={entries(RECORD_STATUS_LABELS)}
            hint="Inactive institutions cannot be used for new applications."
          />
        )}
      </div>
      <div className="flex gap-2 border-t border-line pt-4">
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
