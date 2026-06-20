import pymupdf4llm
from pathlib import Path



def read_pdf(file_path:str, 
             json_output:bool=False, 
             md_output:bool=False, 
             txt_output:bool=False):
    """
    Reads a PDF file and extracts its text content using the pymupdf4llm library. 
    The function can output the extracted content in Markdown, plain text, and JSON formats.

    Args:
        file_path (str): The path to the PDF file.
        json_output (bool): Whether to output the extracted content in JSON format. Default is False.
        md_output (bool): Whether to output the extracted content in Markdown format. Default is False.
        txt_output (bool): Whether to output the extracted content in plain text format. Default is False.

    Returns:
        tuple: A tuple containing the extracted content in the specified formats. The output will be a tuple containing the Markdown, plain text, and JSON outputs, respectively.
    """
    md_out, txt_out, json_out = None, None, None
    output_dir = Path("out")
    output_dir.mkdir(parents=True, exist_ok=True)

    if md_output:
        md_out=pymupdf4llm.to_markdown(file_path, 
                                   header=False, 
                                   footer=False, 
                                   ocr_language="eng+fra",
                                   write_images=True,
                                   image_path="./out",
                                   image_format="png",
                                   dpi=300,
                                   )
    
    if txt_output:
        txt_out=pymupdf4llm.to_text(file_path, 
                                   header=False, 
                                   footer=False, 
                                   ocr_language="eng+fra",
                                   write_images=True,
                                   image_path="./out",
                                   image_format="png",
                                   dpi=300,
                                   )
    
    if json_output:
        json_out=pymupdf4llm.to_json(file_path, 
                                   ocr_language="eng+fra",
                                   write_images=True,
                                   image_path="./out",
                                   image_format="png",
                                   dpi=300,
                                   )
    
    if md_out is not None:
        (output_dir / "output.md").write_bytes(md_out.encode("utf-8"))
    if txt_out is not None:
        (output_dir / "output.txt").write_bytes(txt_out.encode("utf-8"))
    if json_out is not None:
        (output_dir / "output.json").write_bytes(json_out.encode("utf-8"))

    
    return md_out, txt_out, json_out





