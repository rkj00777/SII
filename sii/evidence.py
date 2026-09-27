import hashlib,re
from datetime import datetime

def hash_content(content): return hashlib.sha256(content).hexdigest()

def classify_evidence(title, url, published_at=None):
    t=(title or '').lower()
    if any(x in t for x in ['annual report','financial result','integrated filing','shareholding','corporate action','xbrl']): tier='FULL'
    elif any(x in t for x in ['investor presentation','earnings call','order','capacity','announcement']): tier='PARTIAL'
    else:tier='MIN'
    return {'tier':tier,'source_url':url,'published_at':published_at,'available_at':published_at or datetime.utcnow()}

def extract_numeric(text, labels):
    for label in labels:
        m=re.search(rf'{re.escape(label)}[^0-9-]{{0,80}}(-?[0-9]+(?:\.[0-9]+)?)',text,re.I)
        if m:return float(m.group(1))
    return None
