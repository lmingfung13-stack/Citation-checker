import io

import pandas as pd


def build_excel_report_bytes(summary_df, matched_df, missing_df, uncited_df) -> bytes:
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        summary_df.to_excel(writer, index=False, sheet_name="摘要")
        matched_df.to_excel(writer, index=False, sheet_name="成功配對")
        missing_df.to_excel(writer, index=False, sheet_name="缺失引用")
        uncited_df.to_excel(writer, index=False, sheet_name="未被引用")
    return out.getvalue()
