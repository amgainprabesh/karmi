"""Karmi dataset — consent, licensing and withdrawal for contributed records.

Why this module exists
----------------------
A dataset of naksa drawings is a dataset of *personal* and *authored* works.
Nothing enters Karmi's dataset without an explicit, recorded, revocable grant
from every rights holder. This module is that grant, in machine-readable form.
The plan this implements is ``docs/research/dataset-plan.md`` (sections cited
inline below).

Nepal — Privacy Act, 2075 (2018)  [dataset-plan §3, §8]
-------------------------------------------------------
* Consent is the basis: data about a household (names, ward/kitta, the home
  itself) may be collected and used with the data subject's consent, and the
  Act's purpose-limitation rule (§12(3)) binds the collector: data "shall be
  used only for the purpose for which such data have been collected". That is
  why :class:`ConsentScope` names the purposes explicitly — *dataset release*
  and *model training* are separate checkboxes, not fine print.
* Guardian consent is required for owners under 18 (§33); :class:`ConsentGrant`
  records this with ``guardian=True`` rather than pretending it away.
* Nepal has no general data-protection authority and the Act's reach over
  foreign entities is unclear, but the project treats the Act's consent and
  purpose-limitation duties as binding regardless (dataset-plan §8).
* Withdrawal: contributors may withdraw at any time. The dataset plan is
  explicit that withdrawal is honoured in *future* revisions — copies already
  downloaded cannot be recalled (dataset-plan §3, §8). :func:`withdraw`
  produces a :class:`RedactionInstruction` that says exactly that, and
  ``dataset.export`` refuses to export withdrawn records.

Nepal — Copyright Act, 2059 (2002)  [dataset-plan §4]
-----------------------------------------------------
* "Architectural design" and "other work relating to architecture" are
  protected works (§2(a)(5)-(6)); the **author is the first owner** of the
  economic rights (§6(1)); a work prepared for remuneration can vest in the
  paying party (§6(2)(c)). In practice that means the designer/consultancy,
  and/or the homeowner depending on their contract — *when in doubt, get both
  signatures* (dataset-plan §4). :class:`ConsentRole` therefore distinguishes
  homeowner, drawing author and photographer, and a record's public release
  requires every signatory to have granted the same licence scope.
* Moral rights — attribution and integrity — are **not transferable** and
  survive (§8). Consequence, enforced by the record schema: redaction is a
  modification and only happens with consent; contributors are credited at the
  aggregate level (dataset card acknowledgements); a modified drawing is never
  presented as the author's unaltered work.
* The municipal approval stamp transfers no copyright — approval is an
  administrative act, not a licence to publish (dataset-plan §4).

What this module does *not* do
------------------------------
It does not collect anything and it does not verify signatures — it is the
storage format for the outcome of a human, bilingual, consent process
(dataset-plan §3). The signed forms remain the legal record; the record here
stores pseudonymous references to them.

CLI
---
::

    python -m dataset.consent --withdraw karmi-example-0003 --records-dir dataset/example
    python -m dataset.consent --list dataset/example
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, Sequence

from pydantic import BaseModel, Field, model_validator

__all__ = [
    "ConsentRole",
    "ConsentMethod",
    "LicenceId",
    "Licence",
    "ConsentScope",
    "ConsentGrant",
    "Consent",
    "RedactionInstruction",
    "HasConsent",
    "withdraw",
    "LICENCE_IDS",
]


# --------------------------------------------------------------------------- #
# licence vocabulary
# --------------------------------------------------------------------------- #
class LicenceId(str, Enum):
    """Licence identifiers the dataset accepts.

    CC BY 4.0 is the recommended default for the public redacted tier
    (maximum utility; matches modern data-sharing norms — dataset-plan §4).
    Where a contributor grants less, a per-record licence is recorded instead
    of silently applying BY: ``cc-by-sa-4.0``, ``cc-by-nc-4.0``, or ``other``
    with a terms note.
    """

    CC_BY_4_0 = "cc-by-4.0"
    CC_BY_SA_4_0 = "cc-by-sa-4.0"
    CC_BY_NC_4_0 = "cc-by-nc-4.0"
    OTHER = "other"


LICENCE_IDS: frozenset[str] = frozenset(x.value for x in LicenceId)


class Licence(BaseModel):
    """The licence a record is released under (granted via consent, per plan §4).

    A CC licence can only be granted by the rights holder; this object records
    *what was granted*, while :class:`Consent` records *who granted it*.
    """

    id: LicenceId
    terms_note: str | None = Field(
        None,
        description="required when id == 'other'; the actual terms, or a pointer "
        "to a terms file in the release",
    )
    attribution: str | None = Field(
        None,
        description="aggregate credit line for the dataset card (no personal names "
        "unless the contributor agreed to be credited by name)",
    )

    @model_validator(mode="after")
    def _other_needs_terms(self) -> "Licence":
        if self.id == LicenceId.OTHER and not (self.terms_note or "").strip():
            raise ValueError(
                "licence id 'other' requires terms_note — record the actual terms "
                "(dataset-plan §4: 'license: other' + terms file)"
            )
        return self


# --------------------------------------------------------------------------- #
# consent model
# --------------------------------------------------------------------------- #
class ConsentRole(str, Enum):
    """Who a consent grant comes from (dataset-plan §3)."""

    HOMEOWNER = "homeowner"
    DRAWING_AUTHOR = "drawing_author"
    PHOTOGRAPHER = "photographer"


class ConsentMethod(str, Enum):
    """How consent was given. Recorded because 'how' matters legally."""

    WRITTEN_FORM = "written_form"        # bilingual paper form, signed
    DIGITAL_FORM = "digital_form"        # e-signed / form with OTP trail
    EMAIL = "email"                      # explicit written email from the contributor
    VERBAL_WITNESSED = "verbal_witnessed"  # verbal, witnessed and noted (weakest; flagged in review)


class ConsentScope(BaseModel):
    """What the signatory agreed to — the purposes, named explicitly.

    The Privacy Act 2075 purpose-limitation rule (§12(3)) means purposes may
    not be stretched later: dataset release and model training are separate
    grants, and ``restrictions`` records anything narrower the contributor
    asked for (e.g. 'drawing only, no photos', 'gated tier only').
    """

    licence_scope: list[LicenceId] = Field(
        min_length=1,
        description="licences the signatory agreed their contribution may be "
        "released under (dataset-plan §4)",
    )
    dataset_release: bool = Field(
        False, description="may this contribution appear in a published dataset at all?"
    )
    model_training: bool = Field(
        False, description="may this contribution be used to train models?"
    )
    restrictions: list[str] = Field(
        default_factory=list,
        description="free-form additional limits the contributor attached, e.g. "
        "'photos excluded', 'gated tier only', 'ward-level location only'",
    )


class ConsentGrant(BaseModel):
    """One signatory's grant: who, what, when, how. Explicit, never a boolean."""

    roles: list[ConsentRole] = Field(
        min_length=1,
        description="a signatory may hold several roles at once (e.g. the "
        "homeowner who also took the photos)",
    )
    method: ConsentMethod
    granted_at: date
    scope: ConsentScope
    signatory_id: str | None = Field(
        None,
        description="pseudonymous reference to the signed form (e.g. 'form-c-0012'); "
        "never a name, never an email",
    )
    evidence: str | None = Field(
        None,
        description="what the evidence is, without reproducing PII (e.g. "
        "'bilingual form signed 2026-03-14, scan held in encrypted store')",
    )
    guardian: bool = Field(
        False, description="consent given by a guardian for an owner under 18 "
        "(Privacy Act 2075 §33)"
    )

    @model_validator(mode="after")
    def _no_duplicate_roles(self) -> "ConsentGrant":
        if len(set(self.roles)) != len(self.roles):
            raise ValueError("roles must not repeat within one grant")
        return self


class Consent(BaseModel):
    """The per-record consent block. Required on every :class:`DatasetRecord`.

    Holds one grant per signatory plus the record-level withdrawal state.
    A record whose consent is withdrawn can still be *stored* (for the
    historical record and for the changelog), but ``dataset.export`` will
    never include it in a release.
    """

    grants: list[ConsentGrant] = Field(
        min_length=1, description="one per signatory; at minimum the homeowner"
    )
    withdrawn: bool = False
    withdrawn_at: datetime | None = None
    withdrawal_reason: str | None = None
    withdrawal_requested_by: ConsentRole | None = None

    @model_validator(mode="after")
    def _withdrawal_state_is_complete(self) -> "Consent":
        if self.withdrawn:
            if self.withdrawn_at is None or not (self.withdrawal_reason or "").strip():
                raise ValueError(
                    "a withdrawn consent must carry withdrawn_at and a non-empty "
                    "withdrawal_reason — withdrawal is an event, not a flag flip"
                )
        else:
            if self.withdrawn_at is not None or self.withdrawal_reason is not None:
                raise ValueError(
                    "withdrawn_at / withdrawal_reason are set but withdrawn is False"
                )
        return self

    # -- helpers ----------------------------------------------------------- #
    def roles_present(self) -> set[ConsentRole]:
        out: set[ConsentRole] = set()
        for g in self.grants:
            out.update(g.roles)
        return out

    def licence_intersection(self) -> set[str]:
        """Licences *every* signatory agreed to.

        The record licence must be in this set for a public release — a CC
        licence can only be granted by the rights holder, and every rights
        holder matters (dataset-plan §4).
        """
        sets = [set(x.value for x in g.scope.licence_scope) for g in self.grants]
        if not sets:
            return set()
        return set.intersection(*sets)

    def licence_union(self) -> set[str]:
        out: set[str] = set()
        for g in self.grants:
            out.update(x.value for x in g.scope.licence_scope)
        return out

    def grants_release(self) -> bool:
        return bool(self.grants) and all(g.scope.dataset_release for g in self.grants)


# --------------------------------------------------------------------------- #
# withdrawal → redaction instruction
# --------------------------------------------------------------------------- #
class HasConsent(Protocol):
    """Anything that :func:`withdraw` can act on (avoids an import cycle)."""

    record_id: str
    consent: Consent


class RedactionInstruction(BaseModel):
    """What to do when a contributor withdraws. Machine-readable on purpose."""

    schema_id: str = Field("karmi-redaction-instruction/0.1.0", alias="schema")
    record_id: str
    action: str = Field("remove_from_release", frozen=True)
    scope: str = Field(
        "all_tiers",
        description="withdrawal removes the record from every tier, not just public",
    )
    requested_at: datetime
    reason: str
    requested_by: ConsentRole | None = None
    steps: list[str] = Field(
        default_factory=list,
        description="concrete operational steps for whoever runs the next export",
    )
    honest_limit: str = (
        "Copies of dataset revisions that were already downloaded cannot be "
        "recalled; the record is removed from the next revision onward "
        "(dataset-plan §3)."
    )

    model_config = {"populate_by_name": True}

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(self.model_dump(mode="json", by_alias=True), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return p


def withdraw(
    record: HasConsent,
    reason: str,
    *,
    when: datetime | None = None,
    requested_by: ConsentRole | None = None,
) -> RedactionInstruction:
    """Mark ``record.consent`` withdrawn and produce the redaction instruction.

    Mutates the record's consent block (that is the point — the record's own
    state must show the withdrawal), demotes a public-tier record to ``gated``
    (a withdrawn record cannot remain public — ``dataset.schema`` enforces
    this), and returns the instruction the operator acts on. Honest by
    construction: the instruction states that already-downloaded copies cannot
    be recalled.
    """
    if not (reason or "").strip():
        raise ValueError("withdrawal reason must be non-empty — record why")
    stamp = when or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)

    record.consent.withdrawn = True
    record.consent.withdrawn_at = stamp
    record.consent.withdrawal_reason = reason.strip()
    record.consent.withdrawal_requested_by = requested_by

    # A withdrawn record cannot sit in the public tier (dataset/schema.py).
    tier = getattr(record, "release_tier", None)
    if tier is not None and getattr(tier, "value", tier) == "public":
        try:
            record.release_tier = type(tier)("gated")
        except Exception:  # noqa: BLE001 — duck-typed callers without an enum
            record.release_tier = "gated"

    return RedactionInstruction(
        record_id=record.record_id,
        requested_at=stamp,
        reason=reason.strip(),
        requested_by=requested_by,
        steps=[
            f"Exclude {record.record_id} from every future export — "
            "to_jsonl() and to_hf_dataset() skip records whose consent is withdrawn.",
            f"Delete {record.record_id}'s media from any staged release directory "
            "before the next publication (staged releases are rebuilt from records).",
            "Record the withdrawal in the dataset card changelog and bump the "
            "dataset version for the next revision.",
            "If the record was already published: note in the changelog that earlier "
            "downloads cannot be recalled; the removal takes effect from the next revision.",
        ],
    )


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _default_records_dir() -> Path:
    return Path(__file__).resolve().parent / "example"


def _load_record_files(records_dir: Path) -> list[tuple[Path, Any]]:
    """Load every file in ``records_dir`` that parses as a DatasetRecord.

    Files that do not validate are skipped with a warning on stderr (they may be
    withdrawal instructions, or records written by an older schema version).
    """
    from dataset.schema import DatasetRecord  # local import: schema imports consent

    found: list[tuple[Path, Any]] = []
    for p in sorted(records_dir.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or "consent" not in data or "record_id" not in data:
            continue  # e.g. a redaction instruction, not a record
        try:
            found.append((p, DatasetRecord.model_validate(data)))
        except Exception as exc:  # noqa: BLE001
            print(
                f"warning: {p.name} does not validate as a dataset record "
                f"({type(exc).__name__}: {exc}) — skipped",
                file=sys.stderr,
            )
    return found


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m dataset.consent",
        description="Consent bookkeeping for the Karmi dataset. Withdrawing a record "
        "marks its consent block and writes a redaction instruction next to it.",
    )
    ap.add_argument("--withdraw", metavar="RECORD_ID", help="record id to withdraw")
    ap.add_argument(
        "--records-dir",
        default=None,
        help="directory of record JSON files (default: dataset/example)",
    )
    ap.add_argument("--reason", default=None, help="why the contributor withdrew")
    ap.add_argument(
        "--requested-by",
        choices=[r.value for r in ConsentRole],
        default=None,
        help="which signatory asked for the withdrawal",
    )
    ap.add_argument("--list", action="store_true", help="list records and consent state")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    records_dir = Path(args.records_dir) if args.records_dir else _default_records_dir()
    if not records_dir.is_dir():
        print(f"error: records directory not found: {records_dir}", file=sys.stderr)
        return 2

    records = _load_record_files(records_dir)
    if not records:
        print(f"error: no dataset records found in {records_dir}", file=sys.stderr)
        return 2

    if args.list:
        rows = [
            {
                "record_id": rec.record_id,
                "withdrawn": rec.consent.withdrawn,
                "roles": sorted(r.value for r in rec.consent.roles_present()),
                "licences_granted": sorted(rec.consent.licence_union()),
                "release_ok": rec.consent.grants_release() and not rec.consent.withdrawn,
                "file": path.name,
            }
            for path, rec in records
        ]
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        else:
            for r in rows:
                state = "WITHDRAWN" if r["withdrawn"] else ("release-ok" if r["release_ok"] else "no-release")
                print(f"{r['record_id']:<24} {state:<10} roles={','.join(r['roles'])} "
                      f"licences={','.join(r['licences_granted'])}")
        return 0

    if not args.withdraw:
        ap.print_help()
        return 2

    hit = [(p, rec) for p, rec in records if rec.record_id == args.withdraw]
    if not hit:
        print(f"error: no record with id {args.withdraw!r} in {records_dir}", file=sys.stderr)
        return 2
    path, record = hit[0]

    if record.consent.withdrawn:
        print(
            f"error: {record.record_id} is already withdrawn "
            f"(at {record.consent.withdrawn_at:%Y-%m-%d %H:%M}): "
            f"{record.consent.withdrawal_reason}",
            file=sys.stderr,
        )
        return 2

    reason = args.reason or (
        "Contributor requested withdrawal (reason not recorded in detail; "
        "contact notes held with the signed form)."
    )
    requested_by = ConsentRole(args.requested_by) if args.requested_by else None
    instruction = withdraw(record, reason, requested_by=requested_by)

    # Persist: the record now shows the withdrawal, and the instruction sits next to it.
    path.write_text(
        json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    instruction_path = path.with_name(f"{record.record_id}.withdrawal.json")
    instruction.save(instruction_path)

    if args.json:
        print(json.dumps(instruction.model_dump(mode="json"), ensure_ascii=False, indent=2))
    else:
        print(f"WITHDRAWN  {record.record_id}")
        print(f"  record updated:      {path.name}")
        print(f"  instruction written: {instruction_path.name}")
        print(f"  reason:              {instruction.reason}")
        print("  next steps:")
        for s in instruction.steps:
            print(f"    - {s}")
        print(f"  honest limit: {instruction.honest_limit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())