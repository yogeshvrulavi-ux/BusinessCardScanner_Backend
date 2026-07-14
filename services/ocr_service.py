import os
import shutil
import logging
import re
import cv2
import numpy as np
import pytesseract
from PIL import Image
from utils.image_utils import preprocess_for_ocr
from utils.parser_utils import parse_business_card

logger = logging.getLogger(__name__)

# Configure Tesseract path dynamically on Windows
DEFAULT_TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.getenv("TESSERACT_CMD"):
    pytesseract.pytesseract.tesseract_cmd = os.getenv("TESSERACT_CMD")
    logger.info(f"Tesseract command set from TESSERACT_CMD env: {pytesseract.pytesseract.tesseract_cmd}")
elif os.name == "nt":
    # Prefer explicit default path if it exists
    if os.path.exists(DEFAULT_TESSERACT_PATH):
        pytesseract.pytesseract.tesseract_cmd = DEFAULT_TESSERACT_PATH
        logger.info(f"Using default Tesseract path: {DEFAULT_TESSERACT_PATH}")
    else:
        # Fallback to common locations search
        common_paths = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\\Tesseract-OCR\\tesseract.exe"),
        ]
        for path in common_paths:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                logger.info(f"Tesseract path resolved automatically: {path}")
                break

# Mock business card data for demonstration fallback/reference
MOCK_CARD_DATA = """
John Anderson
Chief Technology Officer
TechVision Solutions Inc.

john.anderson@techvision.com
+1 (415) 555-0147
www.techvision.com
123 Innovation Drive, San Francisco, CA 94105
"""

def generate_dynamic_mock_data(filename: str) -> str:
    """Generate realistic, card-specific mock data based on the filename or path."""
    if not filename:
        return MOCK_CARD_DATA
        
    # Get base name without directory and extension
    base_name = os.path.basename(filename)
    base_name = os.path.splitext(base_name)[0]
    
    # Check if the filename is generic (e.g., DSC_0001, IMG_1234, photo, card, scan)
    generic_patterns = [r'^img_\d+', r'^dsc_\d+', r'^photo', r'^card', r'^scan', r'^image', r'^\d+$']
    is_generic = any(re.match(pattern, base_name.lower()) for pattern in generic_patterns) or len(base_name.strip()) < 3
    
    if is_generic:
        # Deterministically select from a list of high-quality predefined business card templates
        presets = [
            {
                "name": "Yogesh VR",
                "designation": "Workspace owner",
                "company": "CardScan",
                "email": "yogeshvanaparthi@gmail.com",
                "phone": "+91 98849 93074",
                "website": "cardsyncai.netlify.app",
                "address": "India"
            },
            {
                "name": "Sarah Jenkins",
                "designation": "Head of Design",
                "company": "PixelCraft Studio",
                "email": "sarah@pixelcraft.design",
                "phone": "+1 (212) 555-0199",
                "website": "www.pixelcraft.design",
                "address": "789 Broadway, Floor 4, New York, NY 10003"
            },
            {
                "name": "Marcus Vance",
                "designation": "Director of Growth",
                "company": "Apex Marketing Group",
                "email": "marcus.vance@apexmarketing.com",
                "phone": "+1 (312) 555-0183",
                "website": "www.apexmarketing.com",
                "address": "333 Michigan Avenue, Chicago, IL 60601"
            },
            {
                "name": "Elena Rostova",
                "designation": "Senior Software Architect",
                "company": "CloudSphere Solutions",
                "email": "elena@cloudsphere.net",
                "phone": "+1 (206) 555-0134",
                "website": "www.cloudsphere.net",
                "address": "1001 Western Ave, Seattle, WA 98104"
            },
            {
                "name": "Liam Gallagher",
                "designation": "General Partner",
                "company": "Oasis Ventures",
                "email": "liam@oasisventures.vc",
                "phone": "+1 (650) 555-0177",
                "website": "www.oasisventures.vc",
                "address": "3000 Sand Hill Road, Menlo Park, CA 94025"
            },
            {
                "name": "Aisha Patel",
                "designation": "Executive Coordinator",
                "company": "GreenSpace Foods",
                "email": "aisha.patel@greenspacefoods.org",
                "phone": "+1 (510) 555-0155",
                "website": "www.greenspacefoods.org",
                "address": "2100 Milvia Street, Berkeley, CA 94704"
            },
            {
                "name": "David Vance",
                "designation": "Operations Manager",
                "company": "Steelworks Logistics",
                "email": "d.vance@steelworkslogistics.com",
                "phone": "+1 (219) 555-0112",
                "website": "www.steelworkslogistics.com",
                "address": "800 Industrial Highway, Gary, IN 46406"
            },
            {
                "name": "John Anderson",
                "designation": "Chief Technology Officer",
                "company": "TechVision Solutions Inc.",
                "email": "john.anderson@techvision.com",
                "phone": "+1 (415) 555-0147",
                "website": "www.techvision.com",
                "address": "123 Innovation Drive, San Francisco, CA 94105"
            }
        ]
        
        idx = abs(hash(base_name)) % len(presets)
        preset = presets[idx]
        return f"""
{preset['name']}
{preset['designation']}
{preset['company']}

{preset['email']}
{preset['phone']}
{preset['website']}
{preset['address']}
"""

    # Parse filename words
    words_clean = re.sub(r'[-_.]', ' ', base_name)
    words = [w.strip() for w in words_clean.split() if w.strip()]
    
    if len(words) >= 2:
        name = f"{words[0].capitalize()} {words[1].capitalize()}"
        company_name = " ".join([w.capitalize() for w in words[2:]]) if len(words) > 2 else f"{words[1].capitalize()} Corp"
    else:
        name = words[0].capitalize() if words else "Alex Rivera"
        company_name = "CardSync Network"
        
    company_slug = "".join([c for c in company_name.lower() if c.isalnum()])
    if not company_slug:
        company_slug = "network"
        
    name_slug = name.lower().replace(" ", ".")
    email = f"{name_slug}@{company_slug}.com"
    website = f"www.{company_slug}.com"
    
    # Generate a deterministic phone number
    phone_hash = str(abs(hash(name)))
    while len(phone_hash) < 10:
        phone_hash += "0"
    phone = f"+1 ({phone_hash[:3]}) {phone_hash[3:6]}-{phone_hash[6:10]}"
    
    designation = "Corporate Partner"
    address = f"100 {company_name} Plaza, Silicon Valley, CA 94025"
    
    return f"""
{name}
{designation}
{company_name}

{email}
{phone}
{website}
{address}
"""

def clean_ocr_text(text: str) -> str:
    """Post-process OCR text to remove garbage symbols and normalize spacing."""
    # Keep alphanumeric characters, spaces, and common punctuation for contacts
    # Ignore purely decorative or garbled symbols
    cleaned = re.sub(r'[^\w\s\.\,\@\-\+\(\)\:\/]', '', text)
    
    # Normalize excessive newlines and spaces
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    cleaned = re.sub(r' {2,}', ' ', cleaned)
    
    return cleaned.strip()

def similarity_ratio(s1: str, s2: str) -> float:
    """Calculate character overlap ratio between two strings to detect duplicates."""
    s1_clean = "".join(c for c in s1.lower() if c.isalnum())
    s2_clean = "".join(c for c in s2.lower() if c.isalnum())
    if not s1_clean or not s2_clean:
        return 0.0
    from collections import Counter
    c1 = Counter(s1_clean)
    c2 = Counter(s2_clean)
    shared = sum((c1 & c2).values())
    total = max(len(s1_clean), len(s2_clean))
    return shared / total

def merge_text_lines(line_list: list[str]) -> list[str]:
    """Intelligently merge and deduplicate lines of text from multiple passes."""
    cleaned_lines = []
    
    # Basic cleanup and normalization
    for line in line_list:
        line_str = line.strip()
        if len(line_str) < 2:
            continue
        cleaned_lines.append(line_str)
        
    # Deduplicate based on substring containment and character similarity
    merged_lines = []
    for line in cleaned_lines:
        lower_line = line.lower()
        
        # Check if line is a substring of an existing merged line or vice versa
        is_duplicate = False
        for i, existing in enumerate(merged_lines):
            lower_existing = existing.lower()
            
            # 1. Substring check: if one is completely contained in the other
            if lower_line in lower_existing:
                is_duplicate = True
                break
            elif lower_existing in lower_line:
                # Replace shorter line with the longer, more complete version
                merged_lines[i] = line
                is_duplicate = True
                break
                
            # 2. Character similarity overlap check (e.g. > 85% similarity)
            if similarity_ratio(line, existing) > 0.85:
                is_duplicate = True
                # Keep the one containing email/phone tokens or with longer string length
                has_email_phone_new = ('@' in line or any(c.isdigit() for c in line))
                has_email_phone_ext = ('@' in existing or any(c.isdigit() for c in existing))
                if has_email_phone_new and not has_email_phone_ext:
                    merged_lines[i] = line
                elif len(line) > len(existing):
                    merged_lines[i] = line
                break
                
        if not is_duplicate:
            merged_lines.append(line)
            
    return merged_lines

def ocr_with_confidence(pil_img: Image.Image, config: str, min_conf: float = 40.0) -> list[str]:
    """Run OCR and return reconstructed lines, ignoring low confidence words."""
    try:
        data = pytesseract.image_to_data(pil_img, config=config, output_type=pytesseract.Output.DICT)
    except Exception as e:
        logger.warning(f"image_to_data failed: {e}. Falling back to image_to_string.")
        # Fallback to string if data fails
        text = pytesseract.image_to_string(pil_img, config=config)
        return [l.strip() for l in text.split("\n") if l.strip()]
        
    # Group words by block, paragraph, and line
    n_boxes = len(data['text'])
    lines_dict = {}
    
    for i in range(n_boxes):
        text_val = data['text'][i].strip()
        if not text_val:
            continue
            
        try:
            conf = float(data['conf'][i])
        except (ValueError, TypeError):
            conf = -1.0
            
        # -1 confidence means it's a structural element rather than a word
        if conf == -1.0:
            continue
            
        # Ignore low-confidence OCR words (e.g. noise / hallucinations)
        if conf < min_conf:
            logger.info(f"[OCR Confidence Filter] Discarded low-confidence word '{text_val}' (conf: {conf}%)")
            continue
            
        block_num = data['block_num'][i]
        par_num = data['par_num'][i]
        line_num = data['line_num'][i]
        
        key = (block_num, par_num, line_num)
        if key not in lines_dict:
            lines_dict[key] = []
            
        lines_dict[key].append(text_val)
        
    # Reconstruct lines
    reconstructed_lines = []
    for key in sorted(lines_dict.keys()):
        words_list = lines_dict[key]
        line_str = " ".join(words_list).strip()
        if line_str:
            reconstructed_lines.append(line_str)
            
    return reconstructed_lines

def ocr_with_configs(img: np.ndarray, psm_list: list[int]) -> list[str]:
    """Run Tesseract on the given image with multiple PSM configurations and return unique lines."""
    lines = []
    try:
        # Convert numpy array to PIL Image format
        pil_img = Image.fromarray(img) if len(img.shape) == 2 else Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        
        for psm in psm_list:
            config = f"--oem 3 --psm {psm}"
            try:
                # Call confidence-based extractor instead of image_to_string
                reconstructed = ocr_with_confidence(pil_img, config=config, min_conf=40.0)
                lines.extend(reconstructed)
            except Exception as e:
                logger.warning(f"OCR with psm={psm} failed: {e}")
    except Exception as e:
        logger.error(f"Failed to convert image for Tesseract config runs: {e}")
        
    return lines

def is_sufficient_ocr_result(text: str) -> bool:
    """Evaluate if the extracted text has enough fields to be returned early."""
    if not text or not text.strip():
        return False
    parsed = parse_business_card(text)
    # Check if we got a name and at least one contact channel (phone or email)
    has_name = len(parsed.get("name", "").strip()) >= 3
    has_contact = len(parsed.get("emails", [])) > 0 or len(parsed.get("phones", [])) > 0
    return has_name and has_contact

def process_card_image(image_path: str, original_filename: str = None) -> str:
    """
    Process the business card image and extract text.
    Uses an adaptive multi-pass OCR pipeline to extract text efficiently.
    """
    try:
        logger.info(f"Starting adaptive multi-pass OCR pipeline for: {image_path}")
        
        # --- Upfront Tesseract availability check ---
        # The per-pass OCR functions catch TesseractNotFoundError internally,
        # so the exception never bubbles up.  Detect the missing binary early
        # and short-circuit to mock data instead of running empty passes.
        try:
            pytesseract.get_tesseract_version()
        except pytesseract.TesseractNotFoundError:
            logger.warning(
                "Tesseract OCR is not installed. Install from https://github.com/UB-Mannheim/tesseract/wiki"
            )
            return ""
        
        # Load original image
        original_img = cv2.imread(image_path)
        if original_img is None:
            raise ValueError(f"Could not read image file: {image_path}")
            
        all_lines = []
        
        # --- PASS 1: Advanced Preprocessed Binary Image ---
        logger.info("Pass 1: Preprocessing image and running OCR on final binary image")
        try:
            # Utilize the highly-tuned advanced preprocessing pipeline (shadow removal, deskew, etc.)
            binary_img = preprocess_for_ocr(image_path)
            pass1_lines = ocr_with_configs(binary_img, [3, 4])
            all_lines.extend(pass1_lines)
            
            merged_pass1 = merge_text_lines(all_lines)
            raw_pass1 = "\n".join(merged_pass1)
            cleaned_pass1 = clean_ocr_text(raw_pass1)
            
            if is_sufficient_ocr_result(cleaned_pass1):
                logger.info("Pass 1 extraction was highly successful! Returning results early.")
                return cleaned_pass1
        except Exception as e:
            logger.warning(f"Pass 1 processing failed: {e}. Falling back to Pass 2.")
            
        # --- PASS 2 (Fallback): Grayscale Image ---
        logger.info("Pass 2: Fallback OCR on grayscale image")
        resized_img = cv2.resize(original_img, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        gray_img = cv2.cvtColor(resized_img, cv2.COLOR_BGR2GRAY)
        
        pass2_lines = ocr_with_configs(gray_img, [4, 11])
        all_lines.extend(pass2_lines)
        
        merged_pass2 = merge_text_lines(all_lines)
        raw_pass2 = "\n".join(merged_pass2)
        cleaned_pass2 = clean_ocr_text(raw_pass2)
        
        if is_sufficient_ocr_result(cleaned_pass2):
            logger.info("Pass 2 fallback extraction was successful! Returning results early.")
            return cleaned_pass2
            
        # --- PASS 3 (Fallback): Contrast Enhanced & Bilateral Filtered Image ---
        logger.info("Pass 3: Fallback OCR on contrast-enhanced grayscale image")
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        contrast_img = clahe.apply(gray_img)
        # Sharpen
        gaussian = cv2.GaussianBlur(contrast_img, (0, 0), 2.0)
        sharpened_img = cv2.addWeighted(contrast_img, 1.5, gaussian, -0.5, 0)
        filtered_img = cv2.bilateralFilter(sharpened_img, 9, 75, 75)
        
        pass3_lines = ocr_with_configs(filtered_img, [4, 11])
        all_lines.extend(pass3_lines)
        
        merged_pass3 = merge_text_lines(all_lines)
        raw_pass3 = "\n".join(merged_pass3)
        cleaned_pass3 = clean_ocr_text(raw_pass3)
        
        if is_sufficient_ocr_result(cleaned_pass3):
            logger.info("Pass 3 fallback extraction was successful! Returning results.")
            return cleaned_pass3
            
        # --- PASS 4 (Fallback): Region Split Sections ---
        logger.info("Pass 4: Fallback OCR on region-split sections")
        h, w = gray_img.shape[:2]
        regions = {
            "left": gray_img[:, :w // 2],
            "right": gray_img[:, w // 2:],
            "top": gray_img[:h // 2, :],
            "bottom": gray_img[h // 2:, :]
        }
        for region_name, region_img in regions.items():
            all_lines.extend(ocr_with_configs(region_img, [6, 11]))
            
        merged_all = merge_text_lines(all_lines)
        cleaned_text = clean_ocr_text("\n".join(merged_all))
        
        if not cleaned_text.strip():
            logger.warning("OCR returned empty text.")
            return ""
            
        logger.info("OCR Adaptive Pipeline completed successfully with fallback passes.")
        return cleaned_text
    except pytesseract.TesseractNotFoundError:
        logger.warning("Tesseract OCR is not installed. Returning empty OCR text.")
        return ""
    except Exception as e:
        logger.error(f"OCR processing failed: {e}", exc_info=True)
        raise
