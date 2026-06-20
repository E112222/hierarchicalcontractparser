import json
import re
import sys
import os
from langchain_core.documents import Document


def get_page_headers_boxes(page: dict) -> list[dict]:
    """ Retrieves all section-header boxes from a page. """
    return [box for box in page.get("boxes", []) if box.get("boxclass") == "section-header"]

def extract_text(box: dict) -> str:
    """Extracts and merges text from a box."""
    if "textlines" in box and box["textlines"]:
        lines = ["".join(span["text"] for span in line.get("spans", [])) for line in box["textlines"]]
        return " ".join(lines).strip()
    return ""

def get_sections_numbers(header:str) -> str:
    """ Extracts hierarchical numbers from a section header text """
    # Regex to match XX, XX., XX.XX, XX.XX.XX where X is digit or uppercase letter and sep is . - _
    pattern = r'^.{0,5}([0-9]+[.\-_])*[0-9]+'
    match = re.match(pattern, header)
    if match:
        return match.group(0).strip()
    return ""

def filter_sections_headers(sections_headers: list[list[str]]) -> list[list[str]]:
    """ Filters out section headers that do not have a valid hierarchical number. """
    filtered_headers = []
    filterout_keywords = ["Régie","PAGE","Contrat","DEVIS","TABLE DES MATIÈRES","SOMMAIRE","avant-propos","avant propos","formulaire","préambule"]
    for header in sections_headers:
        text=header[1]
        if any(keyword in text for keyword in filterout_keywords) and header[0]=="":
            continue
        else:
            filtered_headers.append(header)
    return filtered_headers

def get_sections_headers(data: dict) -> list[list[str]]:
    """ Extracts section headers text, hierarchical numbers, and their page number """
    sections_headers_text = []
    for page in data.get("pages", []):
        page_number = page.get("page_number")
        for box in get_page_headers_boxes(page):
            text = extract_text(box)
            sections_headers_text.append([text, page_number])
    for header in sections_headers_text:
        header[0]=header[0].strip()
        header.insert(0,get_sections_numbers(header[0]))
    
    filtered_headers = filter_sections_headers(sections_headers_text)
    
    ## Logic to keep unnumbered headers only if they are in a sequence of 3 or more, otherwise they are likely to be noise
    result = []
    unumbered_buffer = []
    for header in filtered_headers:
        if header[0] == "":
            unumbered_buffer.append(header)
        else:
            if len(unumbered_buffer) >= 3:
                result.extend(unumbered_buffer)
            unumbered_buffer = []
            result.append(header)
            
    if len(unumbered_buffer) >= 3:
        result.extend(unumbered_buffer)
        
    return result

def parse_section_number(number_str: str) -> list:
    """ Parses a section number string into a list of parts (numbers/letters). """
    # Split by common separators: . - _
    parts = re.split(r'[\.\-_]', number_str.strip())
    result = []
    for part in parts:
        part = part.strip()
        if part:
            result.append(part)  # Keep as string to preserve leading zeros
    return result

def build_hierarchy_list(sections_headers: list[list[str]]) -> list[dict]:
    """
    Builds a hierarchical list of sections and subsections based on their hierarchical numbers.

    Logic: Sections like X.00 are top-level, and X.01, X.02, etc. are their children.
    Further subsections like X.01.01 are children of X.01.

    Each section_header is [number, text, page_number]
    Returns a nested list of dicts with structure:
    {
        'number': '1.2',
        'text': 'Section Title',
        'page': 5,
        'level': 2,
        'children': [...]
    }
    """

    # Build a dictionary to quickly find nodes by their number
    nodes_by_number = {}
    root = []

    for header in sections_headers:
        number = header[0]
        text = header[1]
        page = header[2]

        parts = parse_section_number(number)
        level = len(parts)

        node = {
            'number': number,
            'text': text,
            'page': page,
            'level': level,
            'children': []
        }

        # Store node by its number for quick lookup
        nodes_by_number[number] = node

        # Determine parent based on the hierarchy logic
        if level == 2 and parts[1] == '00':
            # Sections like X.00 are top-level
            root.append(node)
        elif level == 2 and parts[1] != '00':
            # Sections like X.01, X.02 are children of X.00 or X (e.g. A5)
            parent_number_00 = f"{parts[0]}.00"
            parent_number_base = parts[0]
            if parent_number_base in nodes_by_number:
                nodes_by_number[parent_number_base]['children'].append(node)
            elif parent_number_00 in nodes_by_number:
                nodes_by_number[parent_number_00]['children'].append(node)
            else:
                # Parent not found, add to root
                root.append(node)
        elif level >= 3:
            # Sections like X.01.01 are children of X.01
            parent_number_expanded = ".".join(parts[:-1]) # General approach for deeper levels like A5.2.2
            parent_number_legacy = f"{parts[0]}.{parts[1]}"
            if parent_number_expanded in nodes_by_number:
                nodes_by_number[parent_number_expanded]['children'].append(node)
            elif parent_number_legacy in nodes_by_number:
                nodes_by_number[parent_number_legacy]['children'].append(node)
            else:
                # Parent not found, add to root
                root.append(node)
        else:
            # Other cases, like level 1 (e.g., A5), add to root
            root.append(node)

    return root

def print_hierarchy(hierarchy: list[dict], indent: int = 0) -> None:
    """ Pretty print the hierarchical structure. """
    for node in hierarchy:
        prefix = "│   " * indent + "├── "
        print(f"{prefix} {node['text']} (p.{node['page']})")
        if node['children']:
            print_hierarchy(node['children'], indent + 1)
            
            
def write_trees_in_txt_file(JSON_PATH: str, txtpath: str) -> None:
    """ Writes the hierarchical trees of sections and subsections for all contracts in a txt file. """
    
    print("Writing hierarchical trees to txt file...")
    for file in os.listdir(JSON_PATH):
        jsonpath = os.path.join(JSON_PATH, file)
        with open(jsonpath, 'r', encoding='utf-8') as f:
            data = json.load(f) 

        sections_headers=get_sections_headers(data)
        hierarchy = build_hierarchy_list(sections_headers)
        
        with open(txtpath, 'a', encoding='utf-8') as f:
            f.write("="*200+"\n")
            f.write("Contract : " +str(file) + '\n' + "\n")
            original_stdout = sys.stdout
            sys.stdout = f
            print_hierarchy(hierarchy)
            sys.stdout = original_stdout
            f.write("\n"+"\n")     
    print("Done writing trees to txt file.")
        










def extract_box_text(box: dict) -> str:
    """Extract all text from a box's textlines."""
    texts = []
    textlines = box.get("textlines")
    if textlines:
        for textline in textlines:
            line_text = "".join(span.get("text", "") for span in textline.get("spans", []))
            texts.append(line_text)
    return " ".join(texts).strip()



def chunk_tier_0(data: dict, hierarchy: list[dict]) -> list[Document]:
    """Parse and extract chunks corresponding to top-level sections (e.g., 1.00, 2.00) and their content, excluding headers of sub-sections."""
    EXCLUDED_BOXCLASSES = {"page-header", "page-footer", "footnote"}
    # Extract top-level sections (those in the root of the hierarchy)
    top_level_sections = hierarchy    
    chunks = []
    current_boxes = []
    current_pages = set()
    current_section_number = "Preambule"
    current_section_header_text = "Preambule"    
    for page in data.get("pages", []):
        page_number = page.get("page_number")
        for box in page.get("boxes", []):
            boxclass = box.get("boxclass", "")
            # Skip excluded box types
            if boxclass in EXCLUDED_BOXCLASSES:
                continue
            # If it's a section-header
            if boxclass == "section-header":
                header_text = extract_box_text(box)
                # This is the number of the NEW section starting here
                section_number = get_sections_numbers(header_text)
                # Check if this new section is a top-level section
                is_top_level = False
                if section_number:
                    is_top_level = any(section_number == sec.get('number') for sec in top_level_sections)
                else:
                    is_top_level = any(header_text == sec.get('text') for sec in top_level_sections)
                if is_top_level:
                    # Save the chunk for the PREVIOUS section (found in current_section_number)
                    merged_text = "\n".join(extract_box_text(b) for b in current_boxes) if current_boxes else ""
                    # Find children for the PREVIOUS section
                    children = []
                    if current_section_number and current_section_number != "Preambule":
                        for node in top_level_sections:
                                # For numbered sections, match by number, for unnumbered match by text
                                if (node.get('number') and node.get('number') == current_section_number) or \
                                   (not node.get('number') and node.get('text') == current_section_header_text):
                                    children = [child['text'] for child in node.get('children', [])]
                                    break              
                    chunks.append({
                        "text": merged_text,
                        "chunk_id": current_section_number,
                        "chunk_name": current_section_header_text,
                        "pages": sorted(list(current_pages)),
                        "children": children,
                        "parent": None,
                        "content_boxes": current_boxes,
                        "textlength": len(merged_text),
                    })    
                    # Reset for the new section
                    current_boxes = []
                    current_pages = set()
                    current_section_number = section_number if section_number else f"{header_text}_p{page_number}"
                    current_section_header_text = header_text
                    continue  
                # Skip adding the header box to the content ONLY if it was a tier-0 header.
                # Since it's NOT a tier 0 header, it is a sub-section header. We WANT to append it so we don't lose text.
                current_boxes.append(box)
                current_pages.add(page_number)
                continue
            # Accumulate non-excluded, non-header boxes
            current_boxes.append(box)
            current_pages.add(page_number)
    # Don't forget the last chunk (belongs to the last active section)
    if current_boxes:
        merged_text = "\n".join(extract_box_text(b) for b in current_boxes)
        children = []
        if current_section_number and current_section_number != "Preambule":
            for node in top_level_sections:
                if (node.get('number') and node.get('number') == current_section_number) or \
                   (not node.get('number') and node.get('text') == current_section_header_text):
                    children = [child['text'] for child in node.get('children', [])]
                    break            
        chunks.append({
            "text": merged_text,
            "chunk_id": current_section_number,
            "chunk_name": current_section_header_text,
            "pages": sorted(list(current_pages)),
            "children": children,
            "parent": None,
            "content_boxes": current_boxes,
            "textlength": len(merged_text),
        })
    # Create Document objects
    documents = []
    for chunk in chunks:
        documents.append(
            Document(
                page_content=chunk["text"],
                metadata={
                    "chunk_id": chunk["chunk_id"],
                    "chunk_name": chunk["chunk_name"],
                    "pages": chunk["pages"],
                    "children": chunk["children"],
                    "parent": chunk["parent"],
                    "content_boxes": chunk["content_boxes"],
                    "textlength": chunk["textlength"],
                }
            )
        )
    return documents




def chunk_tier_1(data: dict, hierarchy: list[dict]) -> list[Document]:
    """Parse and extract chunks corresponding to tier-1 sections (e.g., 1.01, 2.01) and their content, excluding headers of sub-sections."""
    EXCLUDED_BOXCLASSES = {"page-header", "page-footer", "footnote"}
    # Extract tier-0 sections
    tier_0_sections = hierarchy
    # Extract tier-1 sections (children of top-level sections)
    tier_1_sections = []
    for tier_0 in hierarchy:
        tier_1_sections.extend(tier_0.get("children", []))
    chunks = []
    current_boxes = []
    current_pages = set()
    current_section_number = "Preambule"
    current_section_header_text = "Preambule"
    for page in data.get("pages", []):
        page_number = page.get("page_number")
        for box in page.get("boxes", []):
            boxclass = box.get("boxclass", "")
            # Skip excluded box types
            if boxclass in EXCLUDED_BOXCLASSES:
                continue
            # If it's a section-header
            if boxclass == "section-header":
                header_text = extract_box_text(box)
                # This is the number of the NEW section starting here
                section_number = get_sections_numbers(header_text)   
                # Check if this new section is a tier-0 or tier-1 section
                is_tier_0 = False
                if section_number:
                    is_tier_0 = any(section_number == sec.get('number') for sec in tier_0_sections)
                else:
                    is_tier_0 = any(header_text == sec.get('text') for sec in tier_0_sections)
                is_tier_1 = False
                if section_number:
                    is_tier_1 = any(section_number == sec.get('number') for sec in tier_1_sections)
                else:
                    is_tier_1 = any(header_text == sec.get('text') for sec in tier_1_sections)      
                if is_tier_0 or is_tier_1:
                    # Save the chunk for the PREVIOUS section (found in current_section_number)
                    is_current_tier_1 = False
                    if current_section_number == "Preambule":
                        is_current_tier_1 = True
                    else:
                        for node in tier_1_sections:
                            if (node.get('number') and node.get('number') == current_section_number) or \
                               (not node.get('number') and node.get('text') == current_section_header_text):
                                is_current_tier_1 = True
                                break
                    if is_current_tier_1 and (current_boxes or current_section_number == "Preambule"):
                        merged_text = "\n".join(extract_box_text(b) for b in current_boxes) if current_boxes else ""  
                        # Find children for the PREVIOUS section
                        children = []
                        parent = None
                        if current_section_number != "Preambule":
                            for node in tier_1_sections:
                                if (node.get('number') and node.get('number') == current_section_number) or \
                                   (not node.get('number') and node.get('text') == current_section_header_text):
                                    children = [child['text'] for child in node.get('children', [])]
                                    break                      
                            for t0 in hierarchy:
                                for child in t0.get('children', []):
                                    if (child.get('number') and child.get('number') == current_section_number) or \
                                       (not child.get('number') and child.get('text') == current_section_header_text):
                                        parent = t0.get('text')
                                        break
                                if parent: break
                        chunks.append({
                            "text": merged_text,
                            "chunk_id": current_section_number,
                            "chunk_name": current_section_header_text,
                            "pages": sorted(list(current_pages)),
                            "children": children,
                            "parent": parent,
                            "content_boxes": current_boxes,
                            "textlength": len(merged_text),
                        })     
                    # Reset for the new section
                    current_boxes = []
                    current_pages = set()
                    current_section_number = section_number if section_number else f"{header_text}_p{page_number}"
                    current_section_header_text = header_text         
                    if is_tier_1:
                        # Also include the header itself so text isn't lost
                        current_boxes.append(box)
                        current_pages.add(page_number)
                    continue        
                # Skip adding the header box to the content ONLY if it was another header we don't care about?
                # Actually, if it's NOT a tier 0 or tier 1 header, it might be a tier 2 header. We WANT to append it so we don't lose text.
                current_boxes.append(box)
                current_pages.add(page_number)
                continue       
            # Accumulate non-excluded, non-header boxes
            current_boxes.append(box)
            current_pages.add(page_number)   
    # Don't forget the last chunk (belongs to the last active section)
    is_current_tier_1 = False
    if current_section_number == "Preambule":
        is_current_tier_1 = True
    else:
        for node in tier_1_sections:
            if (node.get('number') and node.get('number') == current_section_number) or \
               (not node.get('number') and node.get('text') == current_section_header_text):
                is_current_tier_1 = True
                break
    if is_current_tier_1 and current_boxes:
        merged_text = "\n".join(extract_box_text(b) for b in current_boxes)   
        children = []
        parent = None
        if current_section_number != "Preambule":
            for node in tier_1_sections:
                if (node.get('number') and node.get('number') == current_section_number) or \
                   (not node.get('number') and node.get('text') == current_section_header_text):
                    children = [child['text'] for child in node.get('children', [])]
                    break                  
            for t0 in hierarchy:
                for child in t0.get('children', []):
                    if (child.get('number') and child.get('number') == current_section_number) or \
                       (not child.get('number') and child.get('text') == current_section_header_text):
                        parent = t0.get('text')
                        break
                if parent: break
        chunks.append({
            "text": merged_text,
            "chunk_id": current_section_number,
            "chunk_name": current_section_header_text,
            "pages": sorted(list(current_pages)),
            "children": children,
            "parent": parent,
            "content_boxes": current_boxes,
            "textlength": len(merged_text),
        }) 
    # Create Document objects
    documents = []
    for chunk in chunks:
        documents.append(
            Document(
                page_content=chunk["text"],
                metadata={
                    "chunk_id": chunk["chunk_id"],
                    "chunk_name": chunk["chunk_name"],
                    "pages": chunk["pages"],
                    "children": chunk["children"],
                    "parent": chunk["parent"],
                    "content_boxes": chunk["content_boxes"],
                    "textlength": chunk["textlength"],
                }
            )
        )
    return documents[1:]  # Exclude the first chunk which is the preamble (already included in tier 0)




def chunk_tier_2(data: dict, hierarchy: list[dict]) -> list[Document]:
    """Parse and extract chunks corresponding to tier-2 sections (e.g., 1.01.01, 2.01.01) and their content, excluding headers of sub-sections."""
    EXCLUDED_BOXCLASSES = {"page-header", "page-footer", "footnote"}
    # Extract tier-0 and tier-1 sections as well to stop accumulating
    tier_0_sections = hierarchy
    tier_1_sections = []
    for tier_0 in hierarchy:
        tier_1_sections.extend(tier_0.get("children", []))    
    # Extract tier-2 sections (children of tier-1 sections)
    tier_2_sections = []
    for tier_1 in tier_1_sections:
        tier_2_sections.extend(tier_1.get("children", []))  
    chunks = []
    current_boxes = []
    current_pages = set()
    current_section_number = "Preambule"
    current_section_header_text = "Preambule" 
    for page in data.get("pages", []):
        page_number = page.get("page_number")
        for box in page.get("boxes", []):
            boxclass = box.get("boxclass", "")
            # Skip excluded box types
            if boxclass in EXCLUDED_BOXCLASSES:
                continue
            # If it's a section-header
            if boxclass == "section-header":
                header_text = extract_box_text(box)
                # This is the number of the NEW section starting here
                section_number = get_sections_numbers(header_text)
                # Check if this new section is a tier-0, tier-1 or tier-2 section
                is_tier_0 = False
                if section_number:
                    is_tier_0 = any(section_number == sec.get('number') for sec in tier_0_sections)
                else:
                    is_tier_0 = any(header_text == sec.get('text') for sec in tier_0_sections)
                is_tier_1 = False
                if section_number:
                    is_tier_1 = any(section_number == sec.get('number') for sec in tier_1_sections)
                else:
                    is_tier_1 = any(header_text == sec.get('text') for sec in tier_1_sections)
                is_tier_2 = False
                if section_number:
                    is_tier_2 = any(section_number == sec.get('number') for sec in tier_2_sections)
                else:
                    is_tier_2 = any(header_text == sec.get('text') for sec in tier_2_sections)  
                if is_tier_2 or is_tier_1 or is_tier_0:
                    # Save the chunk for the PREVIOUS section (found in current_section_number)
                    is_current_tier_2 = False
                    if current_section_number == "Preambule":
                        is_current_tier_2 = True
                    else:
                        for node in tier_2_sections:
                            if (node.get('number') and node.get('number') == current_section_number) or \
                               (not node.get('number') and node.get('text') == current_section_header_text):
                                is_current_tier_2 = True
                                break
                    if is_current_tier_2 and (current_boxes or current_section_number == "Preambule"):
                        merged_text = "\n".join(extract_box_text(b) for b in current_boxes) if current_boxes else ""
                        # Find children for the PREVIOUS section
                        children = []
                        parent = None
                        if current_section_number != "Preambule":
                            for node in tier_2_sections:
                                # For numbered sections, match by number, for unnumbered match by text
                                if (node.get('number') and node.get('number') == current_section_number) or \
                                   (not node.get('number') and node.get('text') == current_section_header_text):
                                    children = [child['text'] for child in node.get('children', [])]
                                    break            
                            for t0 in hierarchy:
                                for t1 in t0.get('children', []):
                                    for child in t1.get('children', []):
                                        if (child.get('number') and child.get('number') == current_section_number) or \
                                           (not child.get('number') and child.get('text') == current_section_header_text):
                                            parent = t1.get('text')
                                            break
                                    if parent: break
                                if parent: break
                        chunks.append({
                            "text": merged_text,
                            "chunk_id": current_section_number,
                            "chunk_name": current_section_header_text,
                            "pages": sorted(list(current_pages)),
                            "children": children,
                            "parent": parent,
                            "content_boxes": current_boxes,
                            "textlength": len(merged_text),
                        })  
                    # Reset for the new section
                    current_boxes = []
                    current_pages = set()
                    current_section_number = section_number if section_number else f"{header_text}_p{page_number}"
                    current_section_header_text = header_text  
                    if is_tier_2:
                        # We want to include the section header itself so text isn't lost.
                        current_boxes.append(box)
                        current_pages.add(page_number)
                    continue
                # Skip adding the header box to the content ONLY if it was another header we don't care about?
                # Actually, if it's NOT a tier 0, 1 or 2 header, it might be a tier 3 header. We WANT to append it so we don't lose text.
                current_boxes.append(box)
                current_pages.add(page_number)
                continue   
            # Accumulate non-excluded, non-header boxes
            current_boxes.append(box)
            current_pages.add(page_number)
    # Don't forget the last chunk (belongs to the last active section)
    is_current_tier_2 = False
    if current_section_number == "Preambule":
        is_current_tier_2 = True
    else:
        for node in tier_2_sections:
            if (node.get('number') and node.get('number') == current_section_number) or \
               (not node.get('number') and node.get('text') == current_section_header_text):
                is_current_tier_2 = True
                break
    if is_current_tier_2 and current_boxes:
        merged_text = "\n".join(extract_box_text(b) for b in current_boxes)
        children = []
        parent = None
        if current_section_number != "Preambule":
            for node in tier_2_sections:
                if (node.get('number') and node.get('number') == current_section_number) or \
                   (not node.get('number') and node.get('text') == current_section_header_text):
                    children = [child['text'] for child in node.get('children', [])]
                    break             
            for t0 in hierarchy:
                for t1 in t0.get('children', []):
                    for child in t1.get('children', []):
                        if (child.get('number') and child.get('number') == current_section_number) or \
                           (not child.get('number') and child.get('text') == current_section_header_text):
                            parent = t1.get('text')
                            break
                    if parent: break
                if parent: break
        chunks.append({
            "text": merged_text,
            "chunk_id": current_section_number,
            "chunk_name": current_section_header_text,
            "pages": sorted(list(current_pages)),
            "children": children,
            "parent": parent,
            "content_boxes": current_boxes,
            "textlength": len(merged_text),
        })
    # Create Document objects
    documents = []
    for chunk in chunks:
        documents.append(
            Document(
                page_content=chunk["text"],
                metadata={
                    "chunk_id": chunk["chunk_id"],
                    "chunk_name": chunk["chunk_name"],
                    "pages": chunk["pages"],
                    "children": chunk["children"],
                    "parent": chunk["parent"],
                    "content_boxes": chunk["content_boxes"],
                    "textlength": chunk["textlength"],
                }
            )
        )
    return documents[1:]  # Exclude the first chunk which is the preamble (already included in tier 0)



def chunkize_contract(JSON_FILE_PATH: str) -> dict[str, list[Document]]:
    """ Main function to chunkize a contract into tier 0, tier 1, and tier 2 chunks based on the hierarchical structure. """
    with open(JSON_FILE_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    sections_headers=get_sections_headers(data)
    hierarchy = build_hierarchy_list(sections_headers)
    tier_0_docs=chunk_tier_0(data, hierarchy)
    tier_1_docs=chunk_tier_1(data, hierarchy)
    tier_2_docs=chunk_tier_2(data, hierarchy)
    documents_by_tier = {
        "tier_0": tier_0_docs,
        "tier_1": tier_1_docs,
        "tier_2": tier_2_docs
    }
    return documents_by_tier










        
    