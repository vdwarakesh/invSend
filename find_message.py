TEMPLATE_FILE_NAME = "template.docx"

import re
from docx import Document

def message_to_send(subject: str, sourceMap: dict, roleMap: dict = None):
    subject = subject.lower().strip()

    # 1. Exact match
    if subject in sourceMap:
        return sourceMap[subject]

    # 2. Extract individual words
    words = set(re.findall(r"\b\w+\b", subject))

    # 3. Fuzzy keyword matching
    if roleMap:
        for role, keywords in roleMap.items():
            if role in sourceMap:
                if any(keyword.lower() in words for keyword in keywords):
                    return sourceMap[role]

    return ""

def get_sourceMap_file(doc:str):
    """
    Role: Text raw mapping
    """
    doc = Document(doc)
    content = "\n".join(p.text for p in doc.paragraphs)
    results = re.split(r"(?im)(?=^kripesh)", content)
    sourceMap = {}
    for result in results:
        resSplit = result.split("\n")
        for line in resSplit:
            if line.lower().startswith("role"):
                role = re.split(r"[:=-]", line, maxsplit=1)[1]
                sourceMap[role.lower().strip()] = result.strip()
                break
    return sourceMap

# MUST match (case insensitive) with the role in template.docx
roleMap = {
    "l2 support - workday": ["l2","workday"],
    "veeva quality / safety / clinical / rim roles": ["veeva"]
}

sourceMap = get_sourceMap_file(TEMPLATE_FILE_NAME)