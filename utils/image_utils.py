import cv2
import numpy as np
import logging
import os
import uuid

logger = logging.getLogger(__name__)

# Toggle DEBUG_MODE to save intermediate processed images to disk for tuning and inspection
DEBUG_MODE = True
DEBUG_DIR = "debug_output"

def save_debug_image(step_name: str, img: np.ndarray, run_id: str):
    """Save intermediate processing stages to visualize pipeline improvements."""
    if not DEBUG_MODE:
        return
    os.makedirs(DEBUG_DIR, exist_ok=True)
    filepath = os.path.join(DEBUG_DIR, f"{run_id}_{step_name}.jpg")
    cv2.imwrite(filepath, img)
    logger.debug(f"Saved debug image: {filepath}")

def remove_shadows(img: np.ndarray) -> np.ndarray:
    """Normalize background illumination to remove shadows and dark gradients."""
    rgb_planes = cv2.split(img)
    result_planes = []
    for plane in rgb_planes:
        dilated_img = cv2.dilate(plane, np.ones((7,7), np.uint8))
        bg_img = cv2.medianBlur(dilated_img, 21)
        diff_img = 255 - cv2.absdiff(plane, bg_img)
        norm_img = cv2.normalize(diff_img, None, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX, dtype=cv2.CV_8UC1)
        result_planes.append(norm_img)
    return cv2.merge(result_planes)

def deskew_image(img: np.ndarray) -> np.ndarray:
    """Detect text skew and rotate image to align text horizontally accurately."""
    # Convert to grayscale and invert to get white text on black background
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img.copy()
        
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    
    # Dilate horizontally to connect text into distinct blocks/lines
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (30, 5))
    dilate = cv2.dilate(thresh, kernel, iterations=1)
    
    # Find all contours (text blocks)
    contours, _ = cv2.findContours(dilate, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    
    angles = []
    for contour in contours:
        # Filter out small noise contours
        if cv2.contourArea(contour) < 100:
            continue
        rect = cv2.minAreaRect(contour)
        angle = rect[-1]
        
        # minAreaRect returns angles in range [-90, 0)
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
        angles.append(angle)
        
    if not angles:
        return img
        
    # Take median angle of all text blocks to avoid outliers
    median_angle = np.median(angles)
    
    # Ignore negligible angles
    if abs(median_angle) < 0.5:
        return img
        
    # Rotate the image around its center
    (h, w) = img.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, median_angle, 1.0)
    
    # Use BORDER_REPLICATE to avoid harsh black edges pulling OCR context
    rotated = cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    
    logger.info(f"Deskewed image by {median_angle:.2f} degrees")
    return rotated

def sharpen_image(img: np.ndarray) -> np.ndarray:
    """Apply an unsharp mask to sharpen text edges, improving OCR definition."""
    gaussian = cv2.GaussianBlur(img, (0, 0), 2.0)
    return cv2.addWeighted(img, 1.5, gaussian, -0.5, 0)

def mask_qr_code(img: np.ndarray, binary: np.ndarray) -> np.ndarray:
    """Detect QR codes and mask them out with white pixels so OCR ignores them."""
    try:
        qr_decoder = cv2.QRCodeDetector()
        # OpenCV's QRCodeDetector requires a BGR or grayscale image
        img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img.copy()
        ret_qr, decoded_info, points, _ = qr_decoder.detectAndDecodeMulti(img_gray)
        
        if ret_qr and points is not None:
            for bbox in points:
                x_min = int(np.min(bbox[:, 0]))
                y_min = int(np.min(bbox[:, 1]))
                x_max = int(np.max(bbox[:, 0]))
                y_max = int(np.max(bbox[:, 1]))
                padding = 15
                # Mask out the QR code region in the binary image with white
                cv2.rectangle(binary, 
                              (max(0, x_min - padding), max(0, y_min - padding)), 
                              (min(binary.shape[1], x_max + padding), min(binary.shape[0], y_max + padding)), 
                              255, -1)
            logger.info("QR Code detected and masked out.")
    except Exception as e:
        logger.warning(f"QR code masking failed: {e}")
    return binary

def mask_large_contours(binary: np.ndarray) -> np.ndarray:
    """Find and mask large solid regions (like logos or decorative boxes) that confuse OCR."""
    # Find contours on inverted binary (where text/logos are white, background is black)
    inv_binary = cv2.bitwise_not(binary)
    contours, _ = cv2.findContours(inv_binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    img_area = binary.shape[0] * binary.shape[1]
    masked_binary = binary.copy()
    
    for contour in contours:
        area = cv2.contourArea(contour)
        # If a single contour is extremely large (e.g., > 15% of total image area), 
        # it is almost certainly a border or background banner, not text.
        if area > img_area * 0.15:
            # Mask it out with white (background color for OCR)
            cv2.drawContours(masked_binary, [contour], -1, 255, thickness=cv2.FILLED)
            
    return masked_binary

def preprocess_for_ocr(image_path: str) -> np.ndarray:
    """
    Comprehensive, highly-tuned preprocessing pipeline for OCR:
    1. Upscaling for DPI enhancement
    2. Shadow/Illumination removal
    3. Rotation / Deskewing
    4. Grayscale conversion
    5. Contrast Enhancement (CLAHE)
    6. Edge Sharpening
    7. Bilateral Filtering (Edge-preserving noise reduction)
    8. Adaptive Thresholding
    9. Mask out non-text regions (QR Codes, Logos)
    """
    run_id = str(uuid.uuid4())[:6]
    logger.info(f"Starting advanced preprocessing pipeline [Run {run_id}] for: {image_path}")
    
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError("Could not read image file.")
        
    save_debug_image("01_original", img, run_id)
    
    # 1. Resize (Upscale to improve small text detection, Tesseract likes 30px+ height text)
    img = cv2.resize(img, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    save_debug_image("02_resized", img, run_id)
    
    # Keep a color copy for QR detection later
    color_img = img.copy()
    
    # 2. Shadow removal
    img = remove_shadows(img)
    save_debug_image("03_no_shadows", img, run_id)
    
    # 3. Deskew / Alignment
    img = deskew_image(img)
    save_debug_image("04_deskewed", img, run_id)
    
    # 4. Grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 5. Contrast Enhancement (CLAHE)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    gray = clahe.apply(gray)
    save_debug_image("05_clahe", gray, run_id)
    
    # 6. Sharpen
    gray = sharpen_image(gray)
    save_debug_image("06_sharpened", gray, run_id)
    
    # 7. Noise reduction - Using Bilateral Filter instead of FastNlMeans
    # Bilateral filter is excellent at keeping edges (text) sharp while removing background noise
    gray = cv2.bilateralFilter(gray, 9, 75, 75)
    save_debug_image("07_bilateral_filter", gray, run_id)
    
    # 8. Adaptive Thresholding for Binarization
    # Tesseract performs absolutely best on high-contrast black text on a pure white background
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 5
    )
    
    # 9. Region-Based Cleaning
    # Mask QR codes
    binary = mask_qr_code(color_img, binary)
    
    # Mask large non-text blocks (logos)
    binary = mask_large_contours(binary)
    save_debug_image("08_binary_final", binary, run_id)
    
    return binary
