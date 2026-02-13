from PIL import Image

try:
    import fitz  # PyMuPDF, need `pip install pymupdf`
except ImportError:
    fitz = None


def get_pdf_page_image(pdf_bytes, page_num, highlight_text=None):
    if fitz is None:
        return None

    doc = None
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        p_idx = int(page_num) - 1
        if p_idx < 0 or p_idx >= len(doc):
            doc.close()
            return None

        page = doc[p_idx]
        rects = None

        if highlight_text:
            clean_search = highlight_text.replace("...", "").strip()
            rects = page.search_for(clean_search)

            if not rects and len(clean_search) > 30:
                rects = page.search_for(clean_search[:30])
                if not rects:
                    rects = page.search_for(clean_search[:15])

            if not rects and len(clean_search) <= 30:
                no_parens = (
                    clean_search
                    .replace("(", "")
                    .replace(")", "")
                    .replace("（", "")
                    .replace("）", "")
                    .strip()
                )
                if no_parens != clean_search:
                    rects = page.search_for(no_parens)

                if not rects:
                    no_comma = no_parens.replace(",", "").replace("，", "")
                    if no_comma != no_parens:
                        rects = page.search_for(no_comma)

            if rects:
                shape = page.new_shape()
                for r in rects:
                    shape.draw_rect(r)
                    shape.finish(color=(1, 0, 0), fill=(1, 1, 0), fill_opacity=0.4, width=2)
                shape.commit()

        zoom = 2.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        doc.close()
        return img
    except Exception:
        return None
    finally:
        if doc is not None:
            try:
                doc.close()
            except Exception:
                pass
