import fitz
import json
import os
import pickle
from collections import defaultdict



def build_pdf_visualization(original_pdf_path: str, 
                            json_output_path: str) -> None:
    """
    Creates a visual representation of the extracted content from a PDF file by drawing rectangles around the identified text boxes and annotating them with their respective classes. 
    The function reads the original PDF and the corresponding JSON output, then generates an annotated PDF highlighting the different sections, headers, footers, text, and list items.

    Args:
        original_pdf_path (str): The path to the original PDF file.
        json_output_path (str): The path to the JSON file containing the extracted content.

    Returns:
        None

    """
    
    # Load the original PDF
    doc = fitz.open(original_pdf_path)

    # Load the JSON output extracted from the PDF
    with open(json_output_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Build the pages with annotations
    for page_data in data['pages']:
        page_num = page_data['page_number'] - 1  # fitz page numbers are 0-based
        page = doc[page_num]
        for box in page_data['boxes']:
            rect = fitz.Rect(box['x0'], box['y0'], box['x1'], box['y1'])
            
            if box.get('boxclass') == 'section-header':
                page.draw_rect(rect, color=(0, 1, 0), width=1)  # Green for section header
                
            elif box.get('boxclass') == 'page-header' or box.get('boxclass') == 'page-footer':
                page.draw_rect(rect, color=(0.6, 0, 0.6), width=1) # Pink for page header/footer
                
            elif box.get('boxclass') == 'text':
                page.draw_rect(rect, color=(0, 0, 1), width=1) # Blue rectangle

            elif box.get('boxclass') == 'list-item':
                page.insert_text(fitz.Point(rect.x1 + 5, rect.y0), box.get('boxclass', ''), color=(0, 0, 1), fontsize=8)
                page.draw_rect(rect, color=(0, 0, 1), width=1) # Blue rectangle with annotation
                
            else:
                page.insert_text(fitz.Point(rect.x1 + 5, rect.y0), box.get('boxclass', ''), color=(1, 0, 0), fontsize=8)
                page.draw_rect(rect, color=(1, 0, 0), width=2)  # Red rectangle for unclassified boxes with annotation

    # Save the annotated PDF
    file_name="master_annotated"
    output_path = os.path.join("out", f"{file_name}.pdf")
    doc.save(output_path)
    print(f"Annotated PDF saved to: {output_path}")



def highlight_chunks(original_pdf_path: str,
                     pickle_path: str = "out/document_by_tier.pkl",
                     processed_json_path: str = "out/processed_output.json",
                     tier: str = "tier_0",
                     output_path: str | None = None,
                     draw_boxes: bool = True,
                     label_chunks: bool = True) -> str:
    """
    Highlights the chunks stored in ``document_by_tier.pkl`` by drawing rectangles
    on the PDF. For each chunk of the selected tier, a colored bounding rectangle
    (translucent fill + the chunk id/name as a label) is drawn around its content
    on every page it spans; optionally each individual content box is also outlined.
    Consecutive chunks are given different colors so their boundaries are visible.

    Chunk boxes do not carry a page number, so each box is located by matching its
    coordinates against ``processed_output.json`` (the file the chunks were built
    from), disambiguated with the chunk's own ``pages`` list.

    Args:
        original_pdf_path (str): Path to the original PDF file.
        pickle_path (str): Path to the pickled ``document_by_tier`` dict.
        processed_json_path (str): Path to the processed JSON used to build the chunks.
        tier (str): Which tier to highlight: ``"tier_0"``, ``"tier_1"`` or ``"tier_2"``.
        output_path (str | None): Where to save the annotated PDF. Defaults to
            ``out/master_chunks_<tier>.pdf``.
        draw_boxes (bool): Also outline each individual content box. Default True.
        label_chunks (bool): Write the chunk id/name above each chunk. Default True.

    Returns:
        str: The path of the saved annotated PDF.
    """
    # Palette of visually distinct colors; cycled per chunk so neighbours differ.
    PALETTE = [
        (0.90, 0.10, 0.10), (0.10, 0.45, 0.90), (0.10, 0.65, 0.20),
        (0.90, 0.55, 0.00), (0.55, 0.20, 0.75), (0.00, 0.65, 0.65),
        (0.80, 0.30, 0.55), (0.50, 0.45, 0.10), (0.20, 0.30, 0.70),
        (0.70, 0.40, 0.15),
    ]

    # Load the chunks
    with open(pickle_path, "rb") as f:
        documents_by_tier = pickle.load(f)
    if tier not in documents_by_tier:
        raise ValueError(f"Unknown tier {tier!r}. Available tiers: {list(documents_by_tier)}")
    documents = documents_by_tier[tier]

    # Build a coordinate -> page-number(s) index from the processed JSON so that
    # each chunk box (which has no page field) can be placed on the right page.
    with open(processed_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    def box_key(box: dict) -> tuple:
        return (round(box["x0"], 2), round(box["y0"], 2),
                round(box["x1"], 2), round(box["y1"], 2))

    coord_to_pages = defaultdict(set)
    for page in data.get("pages", []):
        page_number = page.get("page_number")
        for box in page.get("boxes", []):
            coord_to_pages[box_key(box)].add(page_number)

    doc = fitz.open(original_pdf_path)

    for idx, document in enumerate(documents):
        boxes = document.metadata.get("content_boxes", [])
        if not boxes:
            continue
        color = PALETTE[idx % len(PALETTE)]
        chunk_pages = set(document.metadata.get("pages", []))

        # Group this chunk's boxes by the page they actually sit on.
        boxes_by_page = defaultdict(list)
        for box in boxes:
            candidates = coord_to_pages.get(box_key(box), set())
            located = (candidates & chunk_pages) or candidates or chunk_pages
            if not located:
                continue
            boxes_by_page[min(located)].append(box)

        # Build the chunk label once.
        chunk_id = str(document.metadata.get("chunk_id") or "")
        chunk_name = str(document.metadata.get("chunk_name") or "")
        label = chunk_id if chunk_id == chunk_name else f"{chunk_id} — {chunk_name}".strip(" —")
        label = label[:70]

        for page_number, page_boxes in boxes_by_page.items():
            page = doc[page_number - 1]  # fitz pages are 0-based

            # Outline each individual content box.
            if draw_boxes:
                for box in page_boxes:
                    page.draw_rect(
                        fitz.Rect(box["x0"], box["y0"], box["x1"], box["y1"]),
                        color=color, width=0.5,
                    )

            # Bounding rectangle enclosing the whole chunk on this page.
            x0 = min(b["x0"] for b in page_boxes)
            y0 = min(b["y0"] for b in page_boxes)
            x1 = max(b["x1"] for b in page_boxes)
            y1 = max(b["y1"] for b in page_boxes)
            union = fitz.Rect(x0 - 2, y0 - 2, x1 + 2, y1 + 2)
            page.draw_rect(union, color=color, width=1.5, fill=color, fill_opacity=0.08)

            if label_chunks:
                page.insert_text(
                    fitz.Point(union.x0, max(union.y0 - 3, 8)),
                    label, color=color, fontsize=7,
                )

    if output_path is None:
        output_path = os.path.join("out", f"master_chunks_{tier}.pdf")
    doc.save(output_path)
    print(f"Chunk-highlighted PDF ({tier}, {len(documents)} chunks) saved to: {output_path}")
    return output_path


