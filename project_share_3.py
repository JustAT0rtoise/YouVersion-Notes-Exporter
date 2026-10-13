import csv
import os
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

from youversion.clients import SyncClient


OUTPUT_FILE = "andbible-bookmarks.csv"
DEFAULT_DOCUMENT_NAME = "MyBible-ESV" #  The bible version you want each note to "be under."

HEADERS = [
    "osisRef",
    "bibleRef",
    "document",
    "book",
    "chapterStart",
    "verseStart",
    "chapterEnd",
    "verseEnd",
    "id",
    "ordinalStart",
    "ordinalEnd",
    "createdAt",
    "lastUpdatedOn",
    "startOffset",
    "endOffset",
    "labels",
    "notes",
    "customIcon",
]


def normalize_iso(dt: str | None) -> str:
    if not dt:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    # Best effort cleanup of YouVersion timestamps like:
    # 2025-01-15T10:30:00.123Z -> 2025-01-15T10:30:00Z
    dt = dt.strip()
    if "." in dt:
        dt = dt.split(".", 1)[0] + "Z"
    return dt.replace(" ", "T").replace("+00:00", "Z")


def safe_list(value):
    if not value:
        return []
    if isinstance(value, list):
        return value
    return [value]

def get_data_of_usfm(usfm) -> dict[str, str] | None:
    if usfm == None:
        return None

    parts = usfm.split('.')
    if len(parts) < 3:
        return None
        
    return {
        "book": parts[0],
        "chapter": parts[1],
        "verse": parts[2]
    }
    
def get_formatted_labels(labels: tuple | None) -> str:
    if labels is None:
        return ""
    
    # The correct formatting for a SINGULAR label in AndBible notes is <label>  (NOTE: not a string!)
    # The correct formatting for MULTIPLE labels in AndBible notes is "<label>;<label>;..."
    # This handles both cases:
    return ";".join(labels)

def get_default_minimal_note_array(note_id, created_at, updated_at, labels, content):
    return get_note_array("", "", "", "", "", "", "", "", note_id, "", "", created_at, updated_at, "", "", labels, content, "")

def get_note_array(osisRef, bibleRef, document, book, chapter_start, verse_start, chapter_end, verse_end, note_id, created_at, updated_at, labels, content) -> [str]:
    return [
        osisRef, #osisRef
        bibleRef, #bibleRef
        document, #document
        book, #book
        chapter_start, #chapterStart
        verse_start, #verseStart
        chapter_end, #chapterEnd
        verse_end, #verseEnd
        note_id, #id
        "", #ordinalStart
        "", #ordinalEnd
        created_at, #createdAt
        updated_at, #lastUpdatedOn
        "", #startOffset
        "", #endOffset
        labels, #labels
        content, #notes
        "", #customIcon
    ]

def compose_string_list_of_secondary_references(references_table) -> str | None:
    if len(references_table) <= 1:
        return None
        
    human_verse_list: [str] = []
    
    # Skip first reference
    for i, ref in enumerate(references_table[1:]):
        human_ref = ref.get("human", "")
        
        human_verse_list.append(human_ref)
        
    secondary_ref_string = ", ".join(human_verse_list)
    return secondary_ref_string

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

username = os.getenv("YOUVERSION_USERNAME")
password = os.getenv("YOUVERSION_PASSWORD")

if not username or not password:
    raise RuntimeError("Missing username/password environment variables.")

client = SyncClient(username, password)

with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(HEADERS)

    index = 1
    #while True:
    while index == 1: # For testing
        notes = client.notes(index)

        if isinstance(notes, dict) and notes.get("error"):
            break

        if not notes:
            break

        for note in notes:
            obj = note.model_dump()# if hasattr(note, "model_dump") else {}
            extras = obj.get("extras", {})
            
            note_id = obj.get("id", "")
            content = extras.get("content", "") #obj.get("content") or getattr(note, "content", "N/A")
            created_at = normalize_iso(obj.get("created_dt"))
            updated_at = normalize_iso(obj.get("updated_dt") or obj.get("created_dt"))
            labels = extras.get("labels", None)
            
            content_formatted = content.strip()
            
            labels_formatted = get_formatted_labels(labels)
            
            print("labels formatted:",labels_formatted)
            references = extras.get("references", None) # or getattr(extras, "references", [])
            print("References:", references)
 
            if references == None:
                print("No references found for note!")
                # Export notes even if they have no reference data
                default_note_array = get_default_minimal_note_array(note_id, created_at, updated_at, labels_formatted, content_formatted)
                
                writer.writerow(default_note_array)
                continue
            
            # TODO: This part forward needs some nice, beautiful, abstraction. Very much MVP (minimal viable product) in terms of code cleanliness.
            
            # The first reference will be our "base," or the reference of which verse data will be written in the CSV. All other references are assumed to be cross-refs or linked verses, and will be referenced in the markdown_note.
            
            base_ref = references[0]
            
            human_ref = base_ref.get("human", "")
            usfm_refs = safe_list(base_ref.get("usfm"))
                
            # If a note spans different non-linear verse segments, they will be split up into separate reference objects.
            # When in a singular ref object, all the usfm_refs are linear, so we can get verseStart and verseEnd by taking the first and last index.
            
            secondary_verse_references = compose_string_list_of_secondary_references(references)
            
            markdown_note = content_formatted
            
            if not secondary_verse_references is None:
                markdown_note = (
                        f"{content_formatted}\n\n"
                        f"**Related verses**: {secondary_verse_references}. "
                )
            
            areMultipleVersesHighlighted = len(usfm_refs) > 1
            
            note_array = None
            
            if areMultipleVersesHighlighted:
                first_usfm_ref = usfm_refs[0]
                last_usfm_ref = usfm_refs[len(usfm_refs) - 1]
                
                first_usfm_data = get_data_of_usfm(first_usfm_ref)
                last_usfm_data = get_data_of_usfm(last_usfm_ref)
                
                if first_usfm_data == None or last_usfm_data == None:
                    print("Null first/last usfm data, returning default!")
                    default_note_array = get_default_minimal_note_array(note_id, created_at, updated_at, labels_formatted, content_formatted)
                    writer.writerow(default_note_array)
                    continue
                
                # Define osisRef based on whether or not there are multiple usfm.
                
                osisRef = "-".join([first_usfm_ref, last_usfm_ref])
                book = first_usfm_data.get("book")
                chapter = first_usfm_data.get("chapter")
                first_verse = first_usfm_data.get("verse")
                last_verse = last_usfm_data.get("verse")
                
                note_array = get_note_array(osisRef, human_ref, DEFAULT_DOCUMENT_NAME, book, chapter, first_verse, chapter, last_verse, note_id, created_at, updated_at, labels_formatted, markdown_note)
            else:
                usfm_ref = usfm_refs[0]
                
                usfm_data = get_data_of_usfm(usfm_ref)
                
                if usfm_data == None:
                    print("Null first/last usfm data, returning default!")
                    default_note_array = get_default_minimal_note_array(note_id, created_at, updated_at, labels_formatted, content_formatted)
                    writer.writerow(default_note_array)
                    continue
                
                osisRef = usfm_ref
                book = usfm_data.get("book")
                chapter = usfm_data.get("chapter")
                verse = usfm_data.get("verse")
                
                note_array = get_note_array(osisRef, human_ref, DEFAULT_DOCUMENT_NAME, book, chapter, verse, chapter, verse, note_id, created_at, updated_at, labels_formatted, markdown_note)
            
            writer.writerow(note_array)
            
            print("Note finished\n")

        print(f"Page {index} complete")
        index += 1

print(f"Done. Wrote {OUTPUT_FILE}")