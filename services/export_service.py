import io

import pandas as pd

from utils.i18n import localize_df_columns, sheet_name_for


def build_excel_report_bytes(summary_df, matched_df, missing_df, uncited_df, language: str = "zh") -> bytes:
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        localize_df_columns(summary_df, "summary", language).to_excel(
            writer,
            index=False,
            sheet_name=sheet_name_for("summary", language),
        )
        localize_df_columns(matched_df, "matched", language).to_excel(
            writer,
            index=False,
            sheet_name=sheet_name_for("matched", language),
        )
        localize_df_columns(missing_df, "missing", language).to_excel(
            writer,
            index=False,
            sheet_name=sheet_name_for("missing", language),
        )
        localize_df_columns(uncited_df, "uncited", language).to_excel(
            writer,
            index=False,
            sheet_name=sheet_name_for("uncited", language),
        )
    return out.getvalue()
