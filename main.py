import os
import json
import pickle



from read_pdf import read_pdf
from visualize_pdf import build_pdf_visualization, highlight_chunks
from general_sections_tree import process_boxes_merging, process_edilex_reclassification, process
from chunkize import chunkize_contract




if __name__ == "__main__":

    # Path to the PDF file
    PDF_PATH = "master.pdf"
    md_out, txt_out, json_out = read_pdf(PDF_PATH, json_output=True, md_output=True, txt_output=True)

    # Build the first visualization of the PDF using the extracted JSON output
    JSON_FILE_PATH = "out/output.json"
    build_pdf_visualization(PDF_PATH, JSON_FILE_PATH)

    # Get the contract sections tree    
    with open(os.path.join(JSON_FILE_PATH), "r", encoding="utf-8") as f:
                    data = json.load(f)           
    processed_data = process_boxes_merging(data)
    processed_data,fp,fn = process_edilex_reclassification(processed_data)
    data, total_retrieved, total_to_retrieve, retrieved_headers_texts = process(processed_data)
    with open(os.path.join("out/processed_output.json"), "w", encoding="utf-8") as f:        
        json.dump(data, f, indent=4, ensure_ascii=False)

    # Chunkize the contract based on the processed JSON output
    document_by_tier = chunkize_contract("out/processed_output.json")
    
    # Save the resulting dict as a pickle
    with open(os.path.join("out","document_by_tier.pkl"), "wb") as f:
        pickle.dump(document_by_tier, f)
    
    # Visualize the chunkization results by highlighting the chunks in the original PDF
    highlight_chunks("master.pdf", tier="tier_0")
    highlight_chunks("master.pdf", tier="tier_1")
    highlight_chunks("master.pdf", tier="tier_2")
 