# Backward compatibility — use wst.document instead
from wst.document import extract_doc_info as extract_pdf_info
from wst.document import write_doc_metadata as write_pdf_metadata

__all__ = ["extract_pdf_info", "write_pdf_metadata"]
