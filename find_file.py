import os
import glob

def file_to_send(subject: str, sourceMap: dict, roleMap: dict = None):
    # Returns file path as string
    subject = subject.lower().strip()

    # 1. Exact match
    if subject in sourceMap:
        return sourceMap[subject]

    # 2. Extract individual words
    words = set(subject.split())

    # 3. Fuzzy keyword matching
    if roleMap:
        for role, keywords in roleMap.items():
            if role in sourceMap:
                if any(keyword.lower() in words for keyword in keywords):
                    return sourceMap[role]

    return ""

def get_sourceMap_dir(directory: str = "."):
    sourceMap = {}
    for filepath in glob.glob(os.path.join(directory, "*.docx")):
        filename = os.path.splitext(os.path.basename(filepath))[0]
        role = filename.lower().strip()
        sourceMap[role] = filepath
    return sourceMap

# MUST match (case insensitive) with the docx file name
roleMap = {
    "workday": ["l2", "workday"],
    "veeva quality / safety / clinical / rim roles": ["veeva"]
}

sourceMap = get_sourceMap_dir(".")