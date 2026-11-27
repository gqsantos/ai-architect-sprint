from datetime import date
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


NonEmptyString = Annotated[
	str,
	StringConstraints(strict=True, strip_whitespace=True, min_length=1),
]
EmailString = Annotated[
	str,
	StringConstraints(
		strict=True,
		strip_whitespace=True,
		min_length=1,
		pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
	),
]
PositiveInt = Annotated[int, Field(gt=0)]


class EmployeeRecord(BaseModel):
	model_config = ConfigDict(strict=True, extra="forbid")

	id: PositiveInt
	first_name: NonEmptyString
	last_name: NonEmptyString
	email: EmailString
	phone: NonEmptyString
	birthdate: date
	street_address: NonEmptyString
	city: NonEmptyString
	province: NonEmptyString
	postal_code: NonEmptyString


class PTORecord(BaseModel):
	model_config = ConfigDict(strict=True, extra="forbid")

	employee_id: PositiveInt
	pto_type: NonEmptyString
	start_date: date
	end_date: date
	status: NonEmptyString
	approver_id: PositiveInt

	@model_validator(mode="after")
	def validate_date_range(self) -> "PTORecord":
		if self.end_date < self.start_date:
			raise ValueError("end_date must be on or after start_date")
		return self


class QuarantinedRecord(BaseModel):
	model_config = ConfigDict(strict=True, extra="forbid")

	original_row: dict[str, Any]
	failure_reason: NonEmptyString
