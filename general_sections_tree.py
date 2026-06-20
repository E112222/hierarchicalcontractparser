import json
import os
import re
import sys
from datetime import datetime



class Tee:
    """Redirects output to both console and a file."""
    def __init__(self, *files):
        self.files = files
    
    def write(self, obj):
        for f in self.files:
            f.write(obj)
            f.flush()
    
    def flush(self):
        for f in self.files:
            f.flush()


def extract_text(box:dict)->str:
    """Extracts and merges text from a box."""
    text_content = ""
    if "textlines" in box and box["textlines"]:
        lines = []
        for line in box["textlines"]:
            spans = line.get("spans", [])
            # Join spans in a line
            line_text = "".join([span["text"] for span in spans])
            lines.append(line_text)
        # Join lines with space
        text_content = " ".join(lines).strip()
    return text_content



def merge_boxes(boxes:list)-> (list,int): # type: ignore
    merged = []
    nb_merged=0
    if not boxes:
        return merged, nb_merged
    # Sort boxes primarily by vertical position, then slowly by horizontal
    boxes = sorted(boxes, key=lambda b: (b.get('y0', 0), b.get('x0', 0)))
    current_box = boxes[0]
    for next_box in boxes[1:]:
        cy0, cy1 = current_box.get('y0', 0), current_box.get('y1', 0)
        ny0, ny1 = next_box.get('y0', 0), next_box.get('y1', 0)
        # Calculate vertical overlap
        overlap = max(0, min(cy1, ny1) - max(cy0, ny0))
        min_height = min(cy1 - cy0, ny1 - ny0)
        # If overlap is more than 45% of the smaller box's height, consider them on the same line
        if min_height > 0 and (overlap / min_height) > 0.45:
            is_left = next_box.get('x0', 0) < current_box.get('x0', 0)
            
            current_box['x0'] = min(current_box.get('x0', float('inf')), next_box.get('x0', float('inf')))
            current_box['y0'] = min(current_box.get('y0', float('inf')), next_box.get('y0', float('inf')))
            current_box['x1'] = max(current_box.get('x1', 0), next_box.get('x1', 0))
            current_box['y1'] = max(current_box.get('y1', 0), next_box.get('y1', 0))
            nb_merged += 1
            if "textlines" in next_box:
                if is_left:
                    current_box["textlines"] = (next_box.get("textlines") or []) + (current_box.get("textlines") or []) 
                    print(f"Merging box on the left: {extract_text(next_box)[:50]} with current box: {extract_text(current_box)[:50]}")
                else:
                    current_box["textlines"] = (current_box.get("textlines") or []) + (next_box.get("textlines") or [])
                    print(f"Merging box on the right: {extract_text(next_box)[:50]} with current box: {extract_text(current_box)[:50]}")
        else:
            merged.append(current_box)
            current_box = next_box
    merged.append(current_box)
    return merged, nb_merged



def get_page_headers_boxes(page:dict)->list:
    """Gets all boxes classified as 'section-header' from a page."""
    headers=[]
    for box in page.get("boxes", []):
        if box.get("boxclass") == "section-header":
            headers.append(box)
    return headers


def is_edilex_page(headers_boxes:list)->bool:
    """Determines if a page is in Edilex format based on its section headers."""
    headers_texts = [extract_text(box) for box in headers_boxes]
    pattern = re.compile(r'^\s*(\d+\.){1,3}\d+[A-Za-zÀ-ÿ .\-]*$')
    for t in headers_texts:
        if pattern.search(t):
            return True
    return False



def process_boxes_merging(data:json)->json:
    boxesmerged=0
    print("Starting box merging process...")
    for page in data.get("pages", []):
        #print("-"*150)
        #print(f"Processing page {page.get('page_number', 'unknown')}...")
        page_boxes = page.get("boxes", [])
        page["boxes"], nb_merged = merge_boxes(page_boxes)
        boxesmerged += nb_merged
    print(f"Total boxes merged: {boxesmerged}")
    return data



def process_edilex_reclassification(data:json)-> (json,int,int) : # type: ignore
    """ Reclassifies boxes for Edilex format based on their position and content."""
    fn,fp=0,0
    print("Starting Edilex reclassification process...")
    for page in data.get("pages", []):
        headers_boxes=get_page_headers_boxes(page)
        is_edilex=is_edilex_page(headers_boxes)
        is_edilex_last_page=False
        if page.get("page_number", 0)>1:
            previous_page=data["pages"][page.get("page_number", 0)-2]
            previous_headers_boxes=get_page_headers_boxes(previous_page)
            is_edilex_last_page=is_edilex_page(previous_headers_boxes)
        is_edilex_next_page=False
        if page.get("page_number", 0)<len(data.get("pages", [])):
            next_page=data["pages"][page.get("page_number", 0)]
            next_headers_boxes=get_page_headers_boxes(next_page)
            is_edilex_next_page=is_edilex_page(next_headers_boxes) 
        if is_edilex_last_page and is_edilex_next_page:
            is_edilex=True
        if is_edilex:
            #print(f"Page {page.get('page_number', 'unknown')} is identified as Edilex format.")
            for box in page.get("boxes", []):
                if box.get("boxclass") == "section-header":
                    text=extract_text(box)
                    if re.match(r"^\s*(\d{1,2}(?:\.\d{1,2}){0,3})", text):
                        pass
                    else:
                        y0 = box.get("y0", 0)
                        if y0 < 70:
                            box["boxclass"]="page-header"
                            print(f"Page {page.get('page_number', 'unknown')}, reclassified box :{text} to page-header")
                            fp+=1
                        else:
                            box["boxclass"]="text"
                            print(f"Page {page.get('page_number', 'unknown')}, reclassified box :{text} to text")
                            fp+=1
                if box.get("boxclass") == "text" or box.get("boxclass") == "list-item":
                    text=extract_text(box)
                    if re.match(r"^(?:\d{1,2}\.\d{1,2}\.\d{1,2}|\d{1,2}\.\d{1,2})", text):
                        box["boxclass"]="section-header"
                        print(f"Page {page.get('page_number', 'unknown')}, reclassified box :{text} to section-header")
                        fn+=1
    return data,fp,fn




    
    


def setup_terminal_log():
    log_path = os.path.join(os.path.dirname(__file__), "processing_step2_log.txt")
    log_file = open(log_path, "a", encoding="utf-8")

    sys.stdout = Tee(sys.__stdout__, log_file)
    sys.stderr = Tee(sys.__stderr__, log_file)

    print("\n" + "=" * 100)
    print(f"RUN START: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 100)

    return log_file, log_path



def get_header_boundaries(data, sections_tree):
    """Get page boundaries between headers for more accurate searching."""
    boundaries = {}
    for i, section in enumerate(sections_tree):
        section_num = section[0]
        page_num = section[2]
        # Next section page, or last page if it's the last section
        next_page = sections_tree[i+1][2] if i+1 < len(sections_tree) else len(data.get("pages", []))
        boundaries[section_num] = (page_num, next_page)
    return boundaries


def get_sections(data):
    """ Extracts section headers text, hierarchical numbers, and their page number """
    
    sections_headers_text = []
    sections_numbers = []
    
    for page in data.get("pages", []):
        page_number = page.get("page_number")
        for box in get_page_headers_boxes(page):
            text = extract_text(box)
            if re.match(r"^\d", text):
                sections_headers_text.append([text, page_number])
                sections_numbers.append([re.sub(r'[^0-9.].*', '', text), page_number])
                
    return sections_headers_text, sections_numbers



def get_tree(data,showTree=False):
    """ Constructs a hierarchical tree of sections based on their numbers. Returns the tree structure. 
    IE:[['0.00', '0.00INTERPRÉTATION', 8], ['0.01', '0.01Terminologie', 8], ['0.01.01', '0.01.01Accord Intergouvernemental', 8], ['0.01.02', '0.01.02Addenda', 9]...]"""
    
    sections_headers_text, sections_numbers = get_sections(data)
    sections_tree = [[re.sub(r'[^0-9.].*', '', s[0]),s[0] ,s[1]] for s in sections_headers_text]
    
    if showTree:
        for header in sections_tree:
            header_number,header_text,header_page=header[0],header[1],header[2]
            splited_h_number=header_number.split('.')
            if len(splited_h_number)==2 and splited_h_number[1].isdigit() and int(splited_h_number[1])==0:
                print(f"{header_text}{' '*(150-len(header_text))}Page {header_page}")
            elif len(splited_h_number)==2:
                print(f"|    {header_text}")
            elif len(splited_h_number)==3:
                print(f"|        {header_text}")
    
    return sections_tree


def get_tier0_sections(sections_tree):
    """ Extracts tier 0 sections and their corresponding sublists from the sections tree. """
    return [element for element in sections_tree if re.match(r'^\d+(?:[.\-]\s?|\s)?$', element[0])]
    
def split_suites_tier0(corres_n):
    """ Splits a list of tier 0 section numbers into sublists based on continuity. """
    split,current = [], []
    for i, num in enumerate(corres_n):
        if i == 0 or num > corres_n[i-1]:
            current.append(num)
        else:
            split.append(current)
            current = [num]
    if current:
        split.append(current)
    return split
    
def get_sublists_tier0(tier0_sections):
    raw_numbers = [element for element in tier0_sections if re.match(r'^\d+$', element[0])]
    point_numbers = [element for element in tier0_sections if re.match(r'^\d+\s*\.', element[0])]
    dash_numbers = [element for element in tier0_sections if re.match(r'^\d+\s*\-', element[0])]
    
    raw_subslists = split_suites_tier0(raw_numbers)
    point_sublists = split_suites_tier0(point_numbers)
    dash_sublists = split_suites_tier0(dash_numbers)
    
    return raw_subslists, point_sublists, dash_sublists



def find_missings_in_one_sublist_tier0(sublist):
    for element in sublist:
        element[0]=int(re.sub(r'[^0-9]', '', str(element[0])))
    missing = []
    if sublist[0][0]>1 and sublist[0][0]<200:
        missing.extend([(i,(None,sublist[0][2])) for i in range(1, sublist[0][0])])
    for i in range(len(sublist) - 1):
        current_num,current_str, current_page = sublist[i]
        next_num, next_str, next_page = sublist[i + 1]
        # Check if numbers are consecutive
        if next_num > current_num + 1  and next_num<200:
            for m in range(current_num + 1, next_num):
                # Missing number is m, page is between current_page and next_page
                missing.append((m, (current_page, next_page)))
    return missing

        
def flatten(nested_list):
    flat_list = []
    for item in nested_list:
        if isinstance(item, list):
            flat_list.extend(flatten(item))
        else:
            flat_list.append(item)
    return flat_list


def project_missing_tier0(missing_sections):
    projected_missing = []
    if len(missing_sections)!=0:  
        for sublist in missing_sections:
            if len(sublist)==0:
                continue
            last=sublist[-1]
            last_num, last_page=last[0],last[1][1]
            if last_num<200:
                for i in range(last_num+1,last_num+10):
                    projected_missing.append((i,(last_page,None)))
    return projected_missing
    
     
def get_missing_tier0_sections(raw_sublists, point_sublists, dash_sublists):
    raw_missing = [find_missings_in_one_sublist_tier0(sublist) for sublist in raw_sublists]
    point_missing = [find_missings_in_one_sublist_tier0(sublist) for sublist in point_sublists]
    dash_missing = [find_missings_in_one_sublist_tier0(sublist) for sublist in dash_sublists]
    
    projected_raw_missing = project_missing_tier0(raw_missing)
    projected_point_missing = project_missing_tier0(point_missing)
    projected_dash_missing = project_missing_tier0(dash_missing)
    
    return raw_missing, point_missing, dash_missing, projected_raw_missing, projected_point_missing, projected_dash_missing


def generate_variations_tier0(missing_tier0,type):
    if type=='raw':
        variations = []
        num_set = set()
        num = missing_tier0
        # Generate variations with leading zeros up to 4 digits
        for width in range(1, 5):
            variation = str(num).zfill(width)
            if variation not in num_set:
                variations.append(variation)
                num_set.add(variation)
        return variations
    elif type=='point':
        variations = []
        num_set = set()
        num = missing_tier0
        # Generate variations with leading zeros up to 4 digits and a dot, with or without a space before the dot
        for width in range(1, 5):
            variation1 = str(num).zfill(width) + '.'
            variation2 = str(num).zfill(width) + ' .'
            if variation1 not in num_set:
                variations.append(variation1)
            num_set.add(variation1)
            if variation2 not in num_set:
                variations.append(variation2)
            num_set.add(variation2)
        return variations
    elif type=='dash':
        variations = []
        num_set = set()
        num = missing_tier0
        # Generate variations with leading zeros up to 4 digits and a dash, with or without a space before the dash
        for width in range(1, 5):
            variation1 = str(num).zfill(width) + '-'
            variation2 = str(num).zfill(width) + ' -'
            if variation1 not in num_set:
                variations.append(variation1)
            num_set.add(variation1)
            if variation2 not in num_set:
                variations.append(variation2)
            num_set.add(variation2)
        return variations
    
    
def retrieve_missing_tier0_elements(data, missing, type_element, sections_tree=None, count_results=True):
    r = 0
    boundaries = get_header_boundaries(data, sections_tree) if sections_tree else {}
    
    for element in flatten(missing):
        section_num = element[0]
        strings = generate_variations_tier0(section_num, type_element)
        start_page, end_page = element[1]
        
        # Use header boundaries if available, otherwise use page ranges
        if section_num in boundaries:
            start_page, end_page = boundaries[section_num]
        else:
            # If both pages are set (missing between two sections), use them directly
            # If one is None (projected), apply 5-page window logic
            if start_page is None or end_page is None:
                if start_page is None:
                    start_page = max(0, end_page - 5) if end_page is not None else 0
                if end_page is None:
                    end_page = min(start_page + 5, len(data.get("pages", []))) if start_page is not None else len(data.get("pages", []))
        
        #print(f"  {section_num}")
        
        for page in data.get("pages", []):
            if start_page <= page.get("page_number", 0) < end_page:
                for box in page.get("boxes", []):
                    text = extract_text(box)
                    if any(re.match(rf"^{re.escape(variant)}([ a-zA-Z])", text) for variant in strings) and len(text) <= 120:
                        if box["boxclass"] != "section-header":
                            box["boxclass"] = "section-header"
                            print(f"    ✓ Found in page {page.get('page_number')}: {text}")
                            if count_results:
                                r += 1
    return r
    
    
def try_retrieve_missing_tier0(data, raw_missing, point_missing, dash_missing, projected_raw_missing, projected_point_missing, projected_dash_missing):
    retrieved = 0
    sections_tree = get_tree(data, showTree=False)
    
    #print("\n🔍 Tier 0 - Searching for raw numbered sections...")
    retrieved += retrieve_missing_tier0_elements(data, raw_missing, 'raw', sections_tree, count_results=True)
    
    #print("\n🔍 Tier 0 - Searching for point-numbered sections...")
    retrieved += retrieve_missing_tier0_elements(data, point_missing, 'point', sections_tree, count_results=True)
    
    #print("\n🔍 Tier 0 - Searching for dash-numbered sections...")
    retrieved += retrieve_missing_tier0_elements(data, dash_missing, 'dash', sections_tree, count_results=True)
    
    #print("\n🔍 Tier 0 - Projected sections (not counted in stats)...")
    # for proj in flatten(projected_raw_missing):
    #     print(f"  {proj[0]}")
    retrieve_missing_tier0_elements(data, projected_raw_missing, 'raw', sections_tree, count_results=False)
    # for proj in flatten(projected_point_missing):
    #     print(f"  {proj[0]}")
    retrieve_missing_tier0_elements(data, projected_point_missing, 'point', sections_tree, count_results=False)
    # for proj in flatten(projected_dash_missing):
    #     print(f"  {proj[0]}")
    retrieve_missing_tier0_elements(data, projected_dash_missing, 'dash', sections_tree, count_results=False)
    
    to_retrieve = len(flatten(raw_missing)) + len(flatten(point_missing)) + len(flatten(dash_missing))
    print(f"\n✅ Tier 0 Complete: Retrieved {retrieved} out of {to_retrieve} sections")
    return retrieved, to_retrieve


def retrieve_tier0(data):
    sections_tree=get_tree(data,showTree=False)
    tier0_sections=get_tier0_sections(sections_tree)
    raw_subslists, point_sublists, dash_sublists = get_sublists_tier0(tier0_sections)
    raw_missing, point_missing, dash_missing, projected_raw_missing, projected_point_missing, projected_dash_missing = get_missing_tier0_sections(raw_subslists, point_sublists, dash_sublists)
    retrieved, over =try_retrieve_missing_tier0(data, raw_missing, point_missing, dash_missing, projected_raw_missing, projected_point_missing, projected_dash_missing)
    return retrieved, over

def get_tier1_sections(sections_tree):
    """ Extracts tier 0 sections and their corresponding sublists from the sections tree. """
    return [element for element in sections_tree if re.match(r'^(?:\d+[.]0|0?\d+[.]00)$', element[0])]


def split_suites_tier1(corres_n):
    """ Splits a list of tier 1 section numbers into sublists based on continuity of the first element. """
    split, current = [], []
    for i, num in enumerate(corres_n):
        if i == 0 or int(num[0]) > int(corres_n[i-1][0]) + 0.5:
            current.append(num)
        else:
            split.append(current)
            current = [num]
    if current:
        split.append(current)
    return split

    
def get_sublists_tier1(tier0_sections):
    raw_numbers = [[e[0].split('.')[0],e[0].split('.')[1],e[1],e[2]] for e in tier0_sections]
    raw_subslists = split_suites_tier1(raw_numbers)
    return raw_subslists


def find_missings_in_one_sublist_tier1(sublist):
    for element in sublist:
        element[0]=int(re.sub(r'[^0-9]', '', str(element[0])))
    missing = []
    if sublist[0][0]>1 and sublist[0][0]<200:
        missing.extend([(i,sublist[0][1],(None,sublist[0][3])) for i in range(1, sublist[0][0])])
    for i in range(len(sublist) - 1):
        current_num,current_sec_num,current_str, current_page = sublist[i]
        next_num, next_sec_num, next_str, next_page = sublist[i + 1]
        # Check if numbers are consecutive
        if next_num > current_num + 1  and next_num<200:
            for m in range(current_num + 1, next_num):
                # Missing number is m, page is between current_page and next_page
                missing.append((m,current_sec_num,(current_page, next_page)))
    return missing


def project_missing_tier1(sublist):
    projected_missing = []
    if len(sublist)!=0:  
        if len(sublist)==0:
            return None
        last=sublist[-1]
        last_num, last_page=last[0],last[3]
        if last_num<200:
            for i in range(last_num+1,last_num+10):
                projected_missing.append((i,last[1],(last_page,None)))
    return projected_missing
    
     
def get_missing_tier1_sections(raw_sublists):
    raw_missing = [find_missings_in_one_sublist_tier1(sublist) for sublist in raw_sublists]
    projected_raw_missing = [project_missing_tier1(sublist) for sublist in raw_sublists]
    return raw_missing, projected_raw_missing


def generate_variations_tier1(element):
    first_num=str(element[0])
    variations = []
    # Generate variations with/without leading zero, and with one or two zeros after the dot
    for prefix in [first_num, first_num.zfill(2)]:
        for suffix in ['0', '00']:
            variations.append(f"{prefix}.{suffix}")
    return variations
    
    
def retrieve_missing_tier1_elements(data, missing, sections_tree=None, count_results=True):
    r = 0
    boundaries = get_header_boundaries(data, sections_tree) if sections_tree else {}
    
    for element in flatten(missing):
        section_num, sub_num = element[0], element[1]
        section_id = f"{section_num}.{sub_num}"
        strings = generate_variations_tier1(element)
        start_page, end_page = element[2]
        
        # Use header boundaries if available
        if section_id in boundaries:
            start_page, end_page = boundaries[section_id]
        else:
            # If both pages are set (missing between two sections), use them directly
            # If one is None (projected), apply 5-page window logic
            if start_page is None or end_page is None:
                if start_page is None:
                    start_page = max(0, end_page - 5) if end_page is not None else 0
                if end_page is None:
                    end_page = min(start_page + 5, len(data.get("pages", []))) if start_page is not None else len(data.get("pages", []))
        
        #print(f"  {section_id}")
        
        for page in data.get("pages", []):
            if start_page <= page.get("page_number", 0) < end_page:
                for box in page.get("boxes", []):
                    text = extract_text(box)
                    if any(re.match(rf"^{re.escape(variant)}([ a-zA-Z])", text) for variant in strings) and len(text) <= 120:
                        if box["boxclass"] != "section-header" and box["boxclass"] != "list-item":
                            box["boxclass"] = "section-header"
                            print(f"    ✓ Found in page {page.get('page_number')}: {text}")
                            if count_results:
                                r += 1
    return r
    
    
def try_retrieve_missing_tier1(data, raw_missing, projected_raw_missing):
    retrieved = 0
    sections_tree = get_tree(data, showTree=False)
    
    #print("\n🔍 Tier 1 - Searching for standard sections...")
    retrieved += retrieve_missing_tier1_elements(data, raw_missing, sections_tree, count_results=True)
    
    #print("\n🔍 Tier 1 - Projected sections (not counted in stats)...")
    # for proj in flatten(projected_raw_missing):
    #     print(f"  {proj[0]}.{proj[1]}")
    retrieve_missing_tier1_elements(data, projected_raw_missing, sections_tree, count_results=False)
    
    to_retrieve = len(flatten(raw_missing))
    print(f"\n✅ Tier 1 Complete: Retrieved {retrieved} out of {to_retrieve} sections")
    return retrieved, to_retrieve



def retrieve_tier1(data):
    sections_tree=get_tree(data,showTree=False)
    tier1_sections=get_tier1_sections(sections_tree)
    sublists=get_sublists_tier1(tier1_sections)
    missing, projected_missing=get_missing_tier1_sections(sublists)
    retrived, over =try_retrieve_missing_tier1(data,missing, projected_missing)
    return retrived, over

def get_tier2_sections(sections_tree):
    """ Extracts tier 0 sections and their corresponding sublists from the sections tree. """
    return [element for element in sections_tree if re.match(r'^(?:\d+[.]\d+|0?\d+[.]\d{2,})$', element[0])]


def split_suites_tier2(corres_n):
    """ Splits a list of tier 1 section numbers into sublists based on continuity of the first element. """
    split, current = [], []
    for i, num in enumerate(corres_n):
        if i == 0 or (int(num[0])==int(corres_n[i-1][0]) and int(num[1])>int(corres_n[i-1][1])+0.5):
            current.append(num)
        else:
            split.append(current)
            current = [num]
    if current:
        split.append(current)
    return split

    
def get_sublists_tier2(tier0_sections):
    raw_numbers = [[e[0].split('.')[0],e[0].split('.')[1],e[1],e[2]] for e in tier0_sections]
    raw_subslists = split_suites_tier2(raw_numbers)
    return raw_subslists


def find_missings_in_one_sublist_tier2(sublist):
    for element in sublist:
        element[0]=int(re.sub(r'[^0-9]', '', str(element[0])))
        element[1]=int(re.sub(r'[^0-9]', '', str(element[1])))
    missing = []
    if sublist[0][1]>1 and sublist[0][1]<200:
        missing.extend([(sublist[0][0],i,(None,sublist[0][3])) for i in range(1, sublist[0][1])])
    for i in range(len(sublist) - 1):
        current_num,current_sec_num,current_str, current_page = sublist[i]
        next_num, next_sec_num, next_str, next_page = sublist[i + 1]
        # Check if numbers are consecutive
        if next_sec_num > current_sec_num + 1  and next_sec_num<200:
            for m in range(current_sec_num + 1, next_sec_num):
                # Missing number is m, page is between current_page and next_page
                missing.append((current_num,m,(current_page, next_page)))
    return missing


def project_missing_tier2(sublist):
    projected_missing = []
    if len(sublist)!=0:  
        if len(sublist)==0:
            return None
        last=sublist[-1]
        last_num, last_page=last[1],last[3]
        if last_num<200:
            for i in range(last_num+1,last_num+10):
                projected_missing.append((last[0],i,(last_page,None)))
    return projected_missing
    
     
def get_missing_tier2_sections(raw_sublists):
    raw_missing = [find_missings_in_one_sublist_tier2(sublist) for sublist in raw_sublists]
    projected_raw_missing = [project_missing_tier2(sublist) for sublist in raw_sublists]
    return raw_missing, projected_raw_missing


def generate_variations_tier2(element):
    first_num=str(element[0])
    sec_num=str(element[1])
    variations = []
    # Generate variations with/without leading zero, and with one or two zeros after the dot
    for prefix in [first_num, first_num.zfill(2)]:
        for suffix in [sec_num, sec_num.zfill(2)]:
            variations.append(f"{prefix}.{suffix}")
    return variations
    
    
def retrieve_missing_tier2_elements(data, missing, sections_tree=None, count_results=True):
    r = 0
    boundaries = get_header_boundaries(data, sections_tree) if sections_tree else {}
    
    for element in flatten(missing):
        section_num, sub_num = element[0], element[1]
        section_id = f"{section_num}.{sub_num}"
        strings = generate_variations_tier2(element)
        start_page, end_page = element[2]
        
        # Use header boundaries if available
        if section_id in boundaries:
            start_page, end_page = boundaries[section_id]
        else:
            # If both pages are set (missing between two sections), use them directly
            # If one is None (projected), apply 5-page window logic
            if start_page is None or end_page is None:
                if start_page is None:
                    start_page = max(0, end_page - 5) if end_page is not None else 0
                if end_page is None:
                    end_page = min(start_page + 5, len(data.get("pages", []))) if start_page is not None else len(data.get("pages", []))
        
        #print(f"  {section_id}")
        
        for page in data.get("pages", []):
            if start_page <= page.get("page_number", 0) < end_page:
                for box in page.get("boxes", []):
                    text = extract_text(box)
                    if any(re.match(rf"^{re.escape(variant)}([ a-zA-Z])", text) for variant in strings) and len(text) <= 120:
                        if box["boxclass"] != "section-header":
                            box["boxclass"] = "section-header"
                            print(f"    ✓ Found in page {page.get('page_number')}: {text}")
                            if count_results:
                                r += 1
    return r
    
    
def try_retrieve_missing_tier2(data, raw_missing, projected_raw_missing):
    retrieved = 0
    sections_tree = get_tree(data, showTree=False)
    
    #print("\n🔍 Tier 2 - Searching for standard sections...")
    retrieved += retrieve_missing_tier2_elements(data, raw_missing, sections_tree, count_results=True)
    
    #print("\n🔍 Tier 2 - Projected sections (not counted in stats)...")
    # for proj in flatten(projected_raw_missing):
    #     print(f"  {proj[0]}.{proj[1]}")
    retrieve_missing_tier2_elements(data, projected_raw_missing, sections_tree, count_results=False)
    
    to_retrieve = len(flatten(raw_missing))
    print(f"\n✅ Tier 2 Complete: Retrieved {retrieved} out of {to_retrieve} sections")
    return retrieved, to_retrieve
    return retrieved, to_retrieve


def retrieve_tier2(data):
    sections_tree=get_tree(data,showTree=False)
    tier2_sections=get_tier2_sections(sections_tree)
    sublists=get_sublists_tier2(tier2_sections)
    missing, projected_missing=get_missing_tier2_sections(sublists)
    retrieved, over =try_retrieve_missing_tier2(data,missing, projected_missing)
    return retrieved, over


def get_tier3_sections(sections_tree):
    """ Extracts tier 0 sections and their corresponding sublists from the sections tree. """
    return [element for element in sections_tree if re.match(r'^(?:\d+[.]\d+[.]\d+)$', element[0])]


def split_suites_tier3(corres_n):
    """ Splits a list of tier 1 section numbers into sublists based on continuity of the first element. """
    split, current = [], []
    for i, num in enumerate(corres_n):
        if i == 0 or (int(num[0])==int(corres_n[i-1][0]) and int(num[1])==int(corres_n[i-1][1]) and int(num[2])>int(corres_n[i-1][2])+0.5):
            current.append(num)
        else:
            split.append(current)
            current = [num]
    if current:
        split.append(current)
    return split

    
def get_sublists_tier3(tier0_sections):
    raw_numbers = [[e[0].split('.')[0],e[0].split('.')[1],e[0].split('.')[2],e[1],e[2]] for e in tier0_sections]
    raw_subslists = split_suites_tier3(raw_numbers)
    return raw_subslists


def find_missings_in_one_sublist_tier3(sublist):
    for element in sublist:
        element[0]=int(re.sub(r'[^0-9]', '', str(element[0])))
        element[1]=int(re.sub(r'[^0-9]', '', str(element[1])))
        element[2]=int(re.sub(r'[^0-9]', '', str(element[2])))
    missing = []
    if sublist[0][2]>1 and sublist[0][2]<200:
        missing.extend([(sublist[0][0],sublist[0][1],i,(None,sublist[0][4])) for i in range(1, sublist[0][2])])
    for i in range(len(sublist) - 1):
        current_num,current_sec_num,current_third_num,current_str, current_page = sublist[i]
        next_num, next_sec_num,next_third_num, next_str, next_page = sublist[i + 1]
        # Check if numbers are consecutive
        if next_third_num > current_third_num + 1  and next_third_num<200:
            for m in range(current_third_num + 1, next_third_num):
                # Missing number is m, page is between current_page and next_page
                missing.append((current_num,current_sec_num,m,(current_page, next_page)))
    return missing


def project_missing_tier3(sublist):
    projected_missing = []
    if len(sublist)!=0:  
        if len(sublist)==0:
            return None
        last=sublist[-1]
        last_num, last_page=last[2],last[4]
        if last_num<200:
            for i in range(last_num+1,last_num+10):
                projected_missing.append((last[0],last[1],i,(last_page,None)))
    return projected_missing
    
     
def get_missing_tier3_sections(raw_sublists):
    raw_missing = [find_missings_in_one_sublist_tier3(sublist) for sublist in raw_sublists]
    projected_raw_missing = [project_missing_tier3(sublist) for sublist in raw_sublists]
    return raw_missing, projected_raw_missing


def generate_variations_tier3(element):
    first_num=str(element[0])
    sec_num=str(element[1])
    third_num=str(element[2])
    variations = []
    # Generate variations with/without leading zero, and with one or two zeros after the dot
    for prefix in [first_num, first_num.zfill(2)]:
        for suffix in [sec_num, sec_num.zfill(2)]:
            for third in [third_num, third_num.zfill(2)]:
                variations.append(f"{prefix}.{suffix}.{third}")
    return variations
    
    
def retrieve_missing_tier3_elements(data, missing, sections_tree=None, count_results=True):
    r = 0
    boundaries = get_header_boundaries(data, sections_tree) if sections_tree else {}
    
    for element in flatten(missing):
        section_num, sub_num, third_num = element[0], element[1], element[2]
        section_id = f"{section_num}.{sub_num}.{third_num}"
        strings = generate_variations_tier3(element)
        start_page, end_page = element[3]
        
        # Use header boundaries if available
        if section_id in boundaries:
            start_page, end_page = boundaries[section_id]
        else:
            # If both pages are set (missing between two sections), use them directly
            # If one is None (projected), apply 5-page window logic
            if start_page is None or end_page is None:
                if start_page is None:
                    start_page = max(0, end_page - 5) if end_page is not None else 0
                if end_page is None:
                    end_page = min(start_page + 5, len(data.get("pages", []))) if start_page is not None else len(data.get("pages", []))
        
        #print(f"  {section_id}")
        
        for page in data.get("pages", []):
            if start_page <= page.get("page_number", 0) < end_page:
                for box in page.get("boxes", []):
                    text = extract_text(box)
                    if any(re.match(rf"^{re.escape(variant)}([ a-zA-Z])", text) for variant in strings) and len(text) <= 150:
                        if box["boxclass"] != "section-header":
                            box["boxclass"] = "section-header"
                            print(f"    ✓ Found in page {page.get('page_number')}: {text}")
                            if count_results:
                                r += 1
    return r
    
    
def try_retrieve_missing_tier3(data, raw_missing, projected_raw_missing):
    retrieved = 0
    sections_tree = get_tree(data, showTree=False)
    
    #print("\n🔍 Tier 3 - Searching for standard sections...")
    retrieved += retrieve_missing_tier3_elements(data, raw_missing, sections_tree, count_results=True)
    
    #print("\n🔍 Tier 3 - Projected sections (not counted in stats)...")
    # for proj in flatten(projected_raw_missing):
    #     print(f"  {proj[0]}.{proj[1]}.{proj[2]}")
    retrieve_missing_tier3_elements(data, projected_raw_missing, sections_tree, count_results=False)
    
    to_retrieve = len(flatten(raw_missing))
    print(f"\n✅ Tier 3 Complete: Retrieved {retrieved} out of {to_retrieve} sections")
    return retrieved, to_retrieve


def retrieve_tier3(data):
    sections_tree=get_tree(data,showTree=False)
    tier3_sections=get_tier3_sections(sections_tree)
    sublists=get_sublists_tier3(tier3_sections)
    missing, projected_missing=get_missing_tier3_sections(sublists)
    retrieved, over =try_retrieve_missing_tier3(data,missing, projected_missing)
    return retrieved, over


def complete_headers_text(data):
    """Completes section headers by merging with adjacent boxes on the same line."""
    retrieved_count = 0
    for page in data.get("pages", []):
        for box in page.get("boxes", []):
            if box.get("boxclass") == "section-header":
                text = extract_text(box)
                if not re.search(r"[a-zA-Z]", text):
                    # Find the closest box on the same line (y coordinate)
                    header_y = box.get("y0", None)
                    header_x = box.get("x0", None)
                    if header_y is not None and header_x is not None:
                        min_dist = float("inf")
                        closest_box = None
                        for other_box in page.get("boxes", []):
                            if other_box is box:
                                continue
                            other_y = other_box.get("y0", None)
                            other_x = other_box.get("x0", None)
                            if other_y is not None and abs(other_y - header_y) < 5:  # Tolerance for same line
                                dist = abs(other_x - header_x)
                                if dist > 0 and dist < min_dist:
                                    min_dist = dist
                                    closest_box = other_box
                        if closest_box:
                            # Merge textlines from closest box into header box
                            box["textlines"].extend(closest_box.get("textlines", []))
                            # Update x1 to the maximum of both boxes
                            box["x1"] = max(box.get("x1", 0), closest_box.get("x1", 0))
                            # Remove the merged box from page
                            page["boxes"].remove(closest_box)
                            retrieved_count += 1
    return data, retrieved_count


def process(data):
    """Process data through all tiers to retrieve and complete section headers."""
    total_retrieved = 0
    total_to_retrieve = 0
    
    print("\n" + "="*80)
    print("PROCESSING DOCUMENT")
    print("="*80)
    
    # Tier 0
    retrieved, to_retrieve = retrieve_tier0(data)
    total_retrieved += retrieved
    total_to_retrieve += to_retrieve
    
    # Tier 1
    retrieved, to_retrieve = retrieve_tier1(data)
    total_retrieved += retrieved
    total_to_retrieve += to_retrieve
    
    # Tier 2
    retrieved, to_retrieve = retrieve_tier2(data)
    total_retrieved += retrieved
    total_to_retrieve += to_retrieve
    
    # Tier 3
    retrieved, to_retrieve = retrieve_tier3(data)
    total_retrieved += retrieved
    total_to_retrieve += to_retrieve
    
    # Complete headers
    #print("\n🔍 Completing partial section headers...")
    data, retrieved_headers_texts = complete_headers_text(data)
    #if retrieved_headers_texts > 0:
        #print(f"✅ Completed {retrieved_headers_texts} partial headers")
    
    return data, total_retrieved, total_to_retrieve, retrieved_headers_texts


