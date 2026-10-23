"""Enumerations shared by models, schemas and services.

Values are stored as strings; changing a value requires a data migration.
"""

from enum import StrEnum


class InstitutionType(StrEnum):
    GOVERNMENT = "government"
    GOVERNMENT_AIDED = "government_aided"
    PRIVATE_SELF_FINANCING = "private_self_financing"
    DEEMED_UNIVERSITY = "deemed_university"
    STATE_PRIVATE_UNIVERSITY = "state_private_university"


class RecordStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class ApplicationCategory(StrEnum):
    EXTENSION_OF_APPROVAL = "extension_of_approval"


class ApplicationType(StrEnum):
    EOA_NO_CHANGE = "eoa_no_change"
    INCREASE_IN_INTAKE = "increase_in_intake"
    REDUCTION_IN_INTAKE = "reduction_in_intake"
    INTRODUCTION_OF_NEW_COURSE = "introduction_of_new_course"
    CHANGE_OF_INSTITUTION_NAME = "change_of_institution_name"


class ProgrammeLevel(StrEnum):
    DIPLOMA = "diploma"
    UNDERGRADUATE = "undergraduate"
    POSTGRADUATE = "postgraduate"


class Shift(StrEnum):
    FIRST = "first"
    SECOND = "second"


class ApplicationStatus(StrEnum):
    """Internal ReguLens workflow statuses. None of these is an AICTE decision."""

    DRAFT = "draft"
    READY_FOR_PRELIMINARY_SCRUTINY = "ready_for_preliminary_scrutiny"
    UNDER_PRELIMINARY_SCRUTINY = "under_preliminary_scrutiny"
    AWAITING_ADDITIONAL_EVIDENCE = "awaiting_additional_evidence"
    PRELIMINARY_SCRUTINY_COMPLETED = "preliminary_scrutiny_completed"
