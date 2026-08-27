"""Decode a raw BTHSurvey (Survey&Report) export into a tidy responses table.

The raw export has two sheets:

* ``VariableView`` — one row per column of ``Data``: variable name, the full
  question label, question type, and the numeric value codes
  (``"1 = 1 - Strongly Disagree\\n2 = ..."``).
* ``Data`` — one row per respondent, numeric codes only, with ``999`` marking
  "not answered". The country question is exploded into one dummy column per
  country (``VAR56_1`` ... ``VAR56_195``), each holding 1 = selected,
  2 = not selected, 999 = the whole question was skipped.

Nothing about the layout is hardcoded by position: variables are classified by
their declared value codes, so a re-export with a different number of claims,
demographics or countries still decodes (and fails loudly if it does not match
the claims metadata).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .config import Config

# BTHSurvey writes checkbox options in Swedish regardless of survey language.
_YES_CODES = {"ja", "yes"}
_LIKERT_MARKER = "strongly disagree"
_COMMENT_SUFFIX = "C"
_ID_COLUMN = "ID"

# Column names the tool understands as a completion duration, if a future
# export ever includes one. Checked case-insensitively.
_DURATION_CANDIDATES = ("duration", "duration_seconds", "time_taken", "responsetime")


class DecodeError(RuntimeError):
    """Raised when the export does not match the structure the tool expects."""


@dataclass
class VariableSpec:
    name: str
    label: str
    qtype: str
    data_type: str
    codes: dict[int, str]
    missing_code: int | None


@dataclass
class DecodedSurvey:
    """Everything the pipeline needs from one export file."""

    source_file: Path
    responses: pd.DataFrame           # one row per respondent, decoded
    comments: pd.DataFrame            # long: respondent_id, claim_id, comment
    claim_columns: list[str]          # claim_id order as presented in the survey
    demographic_columns: list[str]
    survey_text: dict[str, str]       # claim_id -> exact wording shown to respondents
    consent_column: str | None
    duration_column: str | None
    notes: list[str] = field(default_factory=list)


def _parse_value_codes(raw: object) -> dict[int, str]:
    """Turn ``"1 = Developer\\n2 = Tech lead"`` into ``{1: "Developer", ...}``."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return {}
    text = str(raw).strip()
    if text.lower() in {"none", "nan", ""}:
        return {}
    codes: dict[int, str] = {}
    for line in text.splitlines():
        m = re.match(r"\s*(\d+)\s*=\s*(.*)$", line)
        if m:
            codes[int(m.group(1))] = m.group(2).strip()
    return codes


def _read_variable_view(xlsx: Path) -> dict[str, VariableSpec]:
    vv = pd.read_excel(xlsx, sheet_name="VariableView")
    required = {"Variable Name", "Label", "Type", "Data Type", "Value Codes"}
    if not required.issubset(vv.columns):
        raise DecodeError(
            f"VariableView is missing columns {sorted(required - set(vv.columns))}"
        )
    specs: dict[str, VariableSpec] = {}
    for _, row in vv.iterrows():
        name = str(row["Variable Name"]).strip()
        miss = row.get("Missing Code")
        specs[name] = VariableSpec(
            name=name,
            label="" if pd.isna(row["Label"]) else str(row["Label"]).strip(),
            qtype=str(row["Type"]).strip(),
            data_type=str(row["Data Type"]).strip(),
            codes=_parse_value_codes(row["Value Codes"]),
            missing_code=None if pd.isna(miss) else int(miss),
        )
    return specs


def _is_likert(spec: VariableSpec) -> bool:
    """A claim item is the only variable whose codes carry the Likert anchors."""
    return any(_LIKERT_MARKER in v.lower() for v in spec.codes.values())


def _slugify(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return slug or "unnamed"


# Demographic labels as written in the live survey -> the short column names
# used throughout the analysis and the frontend.
_DEMOGRAPHIC_ALIASES = {
    "years_of_professional_software_engineering_experience": "experience",
    "primary_role": "role",
    "team_size": "team_size",
    "industry_domain": "industry",
    "company_size": "company_size",
    "geographic_region": "country",
}


def decode_export(xlsx_path: str | Path, claims: pd.DataFrame, cfg: Config) -> DecodedSurvey:
    """Decode ``xlsx_path`` against the claim metadata in ``claims``.

    ``claims`` must be ordered by ``q_number`` — the order the claims were
    imported into BTHSurvey, which is the order ``VAR01..VAR50`` follow.
    """
    xlsx = Path(xlsx_path)
    if not xlsx.exists():
        raise DecodeError(f"export file not found: {xlsx}")

    specs = _read_variable_view(xlsx)
    data = pd.read_excel(xlsx, sheet_name="Data")
    notes: list[str] = []

    if _ID_COLUMN not in data.columns:
        raise DecodeError(f"Data sheet has no '{_ID_COLUMN}' column")

    missing_code = cfg.missing_code
    idk_code = cfg.idk_code
    likert_values = set(cfg.likert_values)

    # ---- classify variables ------------------------------------------------
    likert_vars = [
        c for c in data.columns
        if c in specs and _is_likert(specs[c]) and not c.endswith(_COMMENT_SUFFIX)
    ]
    comment_vars = [
        c for c in data.columns
        if c.endswith(_COMMENT_SUFFIX)
        and c[:-1] in likert_vars
        and specs.get(c, VariableSpec(c, "", "", "", {}, None)).data_type.lower() == "string"
    ]

    if len(likert_vars) != len(claims):
        raise DecodeError(
            f"export has {len(likert_vars)} Likert claim items but the claims "
            f"metadata lists {len(claims)}. Refusing to guess the mapping."
        )

    # Checkbox families (name_index) — the country dropdown is exploded this way.
    family_members: dict[str, list[str]] = {}
    for c in data.columns:
        m = re.fullmatch(r"(VAR\d+)_(\d+)", str(c))
        if m and c in specs:
            family_members.setdefault(m.group(1), []).append(c)

    consent_column = None
    checkbox_demographics: dict[str, list[str]] = {}
    for family, members in family_members.items():
        label = specs[members[0]].label
        head = label.split(" - ")[0].strip()
        if "agree to participate" in label.lower():
            consent_column = members[0]
        elif len(members) > 1:
            checkbox_demographics[head] = members

    single_choice_demographics = [
        c for c in data.columns
        if c in specs
        and c not in likert_vars
        and not c.endswith(_COMMENT_SUFFIX)
        and not re.fullmatch(r"VAR\d+_\d+", str(c))
        and specs[c].codes
        and not _is_likert(specs[c])
    ]

    duration_column = next(
        (c for c in data.columns if str(c).lower().replace(" ", "_") in _DURATION_CANDIDATES),
        None,
    )
    if duration_column is None:
        notes.append(
            "No completion-duration column in this export; the speeding check "
            "reports 'unavailable' rather than passing respondents by default."
        )

    # ---- build the decoded frame ------------------------------------------
    out = pd.DataFrame(index=data.index)
    out["respondent_id"] = [f"R{int(v):05d}" for v in data[_ID_COLUMN]]
    out["source_row_id"] = data[_ID_COLUMN].astype(int)

    if consent_column is not None:
        consent_codes = specs[consent_column].codes
        out["consented"] = data[consent_column].map(
            lambda v: bool(consent_codes.get(int(v), "").strip().lower() in _YES_CODES)
            if pd.notna(v) and int(v) != missing_code else False
        )
    else:
        out["consented"] = True
        notes.append("No consent variable found in the export; consent assumed granted.")

    # Demographics: decode codes to their labels, 999 -> NA.
    demographic_columns: list[str] = []
    for var in single_choice_demographics:
        spec = specs[var]
        col = _DEMOGRAPHIC_ALIASES.get(_slugify(spec.label), _slugify(spec.label))
        codes = spec.codes
        out[col] = data[var].map(
            lambda v: codes.get(int(v)) if pd.notna(v) and int(v) != missing_code else pd.NA
        )
        demographic_columns.append(col)

    # Checkbox demographics (country): find the single selected option.
    for head, members in checkbox_demographics.items():
        col = _DEMOGRAPHIC_ALIASES.get(_slugify(head), _slugify(head))
        option_names = [specs[m].label.split(" - ", 1)[-1].strip() for m in members]
        block = data[members]
        selected: list[object] = []
        multi = 0
        for _, row in block.iterrows():
            hits = [
                option_names[i]
                for i, v in enumerate(row.tolist())
                if pd.notna(v) and int(v) != missing_code
                and specs[members[i]].codes.get(int(v), "").strip().lower() in _YES_CODES
            ]
            if len(hits) == 1:
                selected.append(hits[0])
            elif not hits:
                selected.append(pd.NA)
            else:
                multi += 1
                selected.append(pd.NA)
        out[col] = selected
        demographic_columns.append(col)
        if multi:
            notes.append(
                f"{multi} respondent(s) had multiple '{head}' options selected; "
                "recorded as missing rather than picking one arbitrarily."
            )

    # Claim answers: keep the raw 1-5 / IDK code. IDK is stored as a distinct
    # sentinel string, never as a number, so it can never leak into a median.
    claim_ids = claims["claim_id"].tolist()
    survey_text: dict[str, str] = {}
    for claim_id, var in zip(claim_ids, likert_vars):
        survey_text[claim_id] = specs[var].label
        col = data[var]
        decoded = []
        for v in col:
            if pd.isna(v) or int(v) == missing_code:
                decoded.append(pd.NA)
            elif int(v) == idk_code:
                decoded.append("IDK")
            elif int(v) in likert_values:
                decoded.append(str(int(v)))
            else:
                raise DecodeError(
                    f"unexpected answer code {v!r} in {var}; expected "
                    f"{sorted(likert_values)}, {idk_code} (IDK) or {missing_code} (missing)"
                )
        out[claim_id] = decoded

    if duration_column is not None:
        out["duration_seconds"] = pd.to_numeric(data[duration_column], errors="coerce")

    # Comments: long format, empty strings dropped.
    comment_rows = []
    for claim_id, var in zip(claim_ids, likert_vars):
        cvar = f"{var}{_COMMENT_SUFFIX}"
        if cvar not in comment_vars:
            continue
        for rid, answer, text in zip(out["respondent_id"], out[claim_id], data[cvar]):
            if pd.isna(text):
                continue
            body = str(text).strip()
            if not body:
                continue
            comment_rows.append(
                {"respondent_id": rid, "claim_id": claim_id,
                 "answer": answer if pd.notna(answer) else "", "comment": body}
            )
    comments = pd.DataFrame(
        comment_rows, columns=["respondent_id", "claim_id", "answer", "comment"]
    )

    return DecodedSurvey(
        source_file=xlsx,
        responses=out,
        comments=comments,
        claim_columns=claim_ids,
        demographic_columns=demographic_columns,
        survey_text=survey_text,
        consent_column=consent_column,
        duration_column=duration_column,
        notes=notes,
    )


def write_clean_csv(decoded: DecodedSurvey, out_dir: str | Path) -> tuple[Path, Path]:
    """Persist the decoded responses and comments; returns both paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^A-Za-z0-9]+", "_", decoded.source_file.stem).strip("_")
    responses_path = out_dir / f"{stem}_responses_clean.csv"
    comments_path = out_dir / f"{stem}_comments.csv"
    decoded.responses.to_csv(responses_path, index=False)
    decoded.comments.to_csv(comments_path, index=False)
    return responses_path, comments_path
