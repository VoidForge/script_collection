"""
Image Classification Script (OpenCLIP version)
Reads each image from Ori/ and copies it to the most similar category folder
(classified/anon, classified/saki, classified/mutsumi, classified/soyo, classified/tomori).
Images that don't fit any category go to classified/other/.

Uses OpenCLIP (MobileCLIP2) for feature extraction and weighted k-Nearest Neighbor (kNN)
classification: similarity is computed against every reference image individually, the top-k
neighbors are selected, and each neighbor votes for its category weighted by its similarity.

Last Modified: 2026-05-19
Directed by vv
Coded by DeepSeek V4 Pro
Advised by Gemini Pro (free version, accessed on 2026-05-19)
"""

"""
Requirements:
- Python >=3.12
- numpy, Pillow, torch, timm, open-clip-torch (import as open_clip)
"""

import os
import shutil
import time
import numpy as np
from PIL import Image
from collections import defaultdict
from typing import Optional, Dict, Tuple, List

import torch
import open_clip
from timm.utils.model import reparameterize_model

# ============================================================
# Configuration
# ============================================================
DATA_DIR = "data"

OTHER_DIR_NAME = "other"

SOURCE_DIR_NAME = "Ori"

CATEGORY_LIST = ["anon", "saki", "mutsumi", "soyo", "tomori", "black_cat", "jiuke"]

OUTPUT_BASE_NAME = "classified"

SOURCE_DIR = os.path.join(DATA_DIR, SOURCE_DIR_NAME)

# Reference folders used ONLY for computing reference embeddings
CATEGORY_DIRS = [
    os.path.join(DATA_DIR, name)
    for name in CATEGORY_LIST
]

# Destination base — classified images are copied here
OUTPUT_BASE = os.path.join(DATA_DIR, OUTPUT_BASE_NAME)

SIMILARITY_THRESHOLD = 0.9   # If top-1 cosine similarity is below this -> "other"
K = 3                         # Number of nearest neighbors for weighted voting

# Valid image extensions
EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'}

# ============================================================
# OpenCLIP Model Configuration
# ============================================================
CLIP_MODEL_NAME = "MobileCLIP2-S4"          # open_clip model name
CLIP_PRETRAINED = "dfndr2b"              # pretrained weights tag
REPARAMETERIZE = True                       # reparameterize for better inference speed

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
MAX_RETRIES = 3
RETRY_DELAY = 2                 # seconds between retries

# ============================================================
# Model Loading
# ============================================================
def load_model(model_name: str, pretrained: str, device: str) -> Tuple[torch.nn.Module, callable]:
    """Load the OpenCLIP model and its preprocess transform."""
    print(f"Loading OpenCLIP model '{model_name}' (pretrained='{pretrained}') on {device}...")
    try:
        model, _, preprocess = open_clip.create_model_and_transforms(
            model_name, pretrained=pretrained
        )
        model = model.to(device)
        model.eval()

        if REPARAMETERIZE:
            print("  Reparameterizing model for inference performance...")
            model = reparameterize_model(model)

        print(f"Model loaded successfully.")
        return model, preprocess
    except Exception as e:
        print(f"ERROR: Failed to load model '{model_name}': {e}")
        raise


# ============================================================
# Embedding Extraction via OpenCLIP
# ============================================================
def get_image_embedding(
    model: torch.nn.Module,
    preprocess: callable,
    image_path: str,
    device: str = DEVICE,
) -> Optional[np.ndarray]:
    """
    Get a normalized embedding vector for an image using OpenCLIP.
    Returns None on failure after retries.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            image = Image.open(image_path).convert("RGB")
            image_tensor = preprocess(image).unsqueeze(0).to(device)

            with torch.no_grad(), torch.amp.autocast(device):
                image_features = model.encode_image(image_tensor)

            # Normalize to unit vector
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)

            vec = image_features.cpu().numpy().flatten()
            return vec

        except Exception as e:
            if attempt < MAX_RETRIES:
                print(f"  Retry {attempt}/{MAX_RETRIES} for {image_path}: {e}")
                time.sleep(RETRY_DELAY * attempt)
            else:
                print(f"  Warning: Could not process {image_path} after {MAX_RETRIES} attempts: {e}")
                return None

    return None


# ============================================================
# Reference Embedding Collection
# ============================================================
def gather_reference_embeddings(
    model: torch.nn.Module,
    preprocess: callable,
    device: str = DEVICE,
) -> Tuple[np.ndarray, List[str]]:
    """
    Collect every reference image's normalized embedding along with its category label.

    Returns:
        ref_embeddings: 2D numpy array of shape (num_refs, embedding_dim).
                        Each row is a unit-normalized embedding vector.
        ref_labels: List of category name strings, one per row in ref_embeddings.
    """
    all_embeddings = []
    all_labels = []

    for folder in CATEGORY_DIRS:
        if not os.path.isdir(folder):
            print(f"  Skipping missing folder: {folder}")
            continue

        category = os.path.basename(folder)
        image_files = [
            f for f in os.listdir(folder)
            if os.path.splitext(f)[1].lower() in EXTENSIONS
        ]
        if not image_files:
            print(f"  No images in '{folder}', skipping.")
            continue

        for fname in image_files:
            full_path = os.path.join(folder, fname)
            print(f"  Embedding reference: {full_path}")
            feat = get_image_embedding(model, preprocess, full_path, device)
            if feat is not None:
                all_embeddings.append(feat)
                all_labels.append(category)

    if all_embeddings:
        ref_matrix = np.stack(all_embeddings, axis=0)  # shape: (N, D)
        print(f"\n  Total reference embeddings collected: {ref_matrix.shape[0]}")
        print(f"  Categories present: {sorted(set(all_labels))}")
        return ref_matrix, all_labels
    else:
        print("  No valid reference embeddings collected.")
        return np.array([]), []


# ============================================================
# Classification (Weighted kNN)
# ============================================================
def classify_image(
    model: torch.nn.Module,
    preprocess: callable,
    image_path: str,
    ref_embeddings: np.ndarray,
    ref_labels: List[str],
    device: str = DEVICE,
) -> Tuple[Optional[str], float]:
    """
    Classify an image using weighted k-Nearest Neighbors.

    1. Extract the query image's embedding.
    2. Compute cosine similarity against every reference embedding.
    3. Select the top-k most similar references.
    4. If the top-1 similarity is below SIMILARITY_THRESHOLD, return "other".
    5. Otherwise, each of the top-k neighbors votes for its category,
       weighted by its similarity score. The category with the highest
       accumulated weight wins.

    Returns:
        best_category: The predicted category name (or OTHER_DIR_NAME).
        top_1_similarity: The cosine similarity of the single nearest neighbor.
    """
    if ref_embeddings.shape[0] == 0:
        return None, 0.0

    feat = get_image_embedding(model, preprocess, image_path, device)
    if feat is None:
        return None, 0.0

    # Cosine similarity: both ref_embeddings and feat are already L2-normalized
    similarities = np.dot(ref_embeddings, feat)  # shape (N,)

    # Determine effective k (in case we have fewer refs than K)
    k_effective = min(K, len(similarities))

    # Get indices of the top-k similarities (unsorted by partition, then sort)
    top_k_indices = np.argpartition(similarities, -k_effective)[-k_effective:]
    top_k_indices = top_k_indices[np.argsort(similarities[top_k_indices])[::-1]]

    top_1_sim = float(similarities[top_k_indices[0]])

    # Threshold check on top-1 similarity
    if top_1_sim < SIMILARITY_THRESHOLD:
        return OTHER_DIR_NAME, top_1_sim

    # Weighted voting among top-k neighbors
    category_weights: Dict[str, float] = defaultdict(float)
    for idx in top_k_indices:
        cat = ref_labels[idx]
        sim = float(similarities[idx])
        category_weights[cat] += sim

    # Category with the highest accumulated similarity weight
    best_cat = max(category_weights, key=category_weights.get)

    return best_cat, top_1_sim


# ============================================================
# Main
# ============================================================
def main():
    print("=" * 60)
    print("Image Classification Script (OpenCLIP — Weighted kNN)")
    print(f"Model: {CLIP_MODEL_NAME} (pretrained={CLIP_PRETRAINED})")
    print(f"Device: {DEVICE}")
    print(f"k = {K},  threshold = {SIMILARITY_THRESHOLD}")
    print("=" * 60)

    # --- Validate source directory ---
    if not os.path.isdir(SOURCE_DIR):
        print(f"ERROR: Source directory '{SOURCE_DIR}' not found.")
        return

    # --- Build output directory paths ---
    output_dirs = {
        cat: os.path.join(OUTPUT_BASE, cat) for cat in CATEGORY_LIST
    }
    output_dirs[OTHER_DIR_NAME] = os.path.join(OUTPUT_BASE, OTHER_DIR_NAME)

    # --- Ensure all output directories exist ---
    for dir_path in output_dirs.values():
        os.makedirs(dir_path, exist_ok=True)

    # --- Collect existing destination files (for skip logic) ---
    existing_files = set()
    for dir_path in output_dirs.values():
        if os.path.isdir(dir_path):
            for fname in os.listdir(dir_path):
                existing_files.add(fname)
    print(f"\nExisting destination files tracked: {len(existing_files)}")

    # --- Load OpenCLIP model ---
    print(f"\nLoading OpenCLIP model '{CLIP_MODEL_NAME}'...")
    model, preprocess = load_model(CLIP_MODEL_NAME, CLIP_PRETRAINED, DEVICE)

    # --- Gather reference embeddings ---
    print("\nGathering reference embeddings from reference folders...")
    ref_embeddings, ref_labels = gather_reference_embeddings(model, preprocess, DEVICE)
    if ref_embeddings.shape[0] == 0:
        print("ERROR: No reference embeddings could be collected.")
        return

    # --- Gather source images ---
    source_images = [
        f for f in os.listdir(SOURCE_DIR)
        if os.path.splitext(f)[1].lower() in EXTENSIONS
    ]
    print(f"\nProcessing {len(source_images)} images from '{SOURCE_DIR}'...\n")

    # --- Classify and copy ---
    results = defaultdict(list)
    skipped = 0
    copied = 0
    errors = 0

    for i, fname in enumerate(source_images):
        src_path = os.path.join(SOURCE_DIR, fname)
        idx_str = f"[{i+1:4d}/{len(source_images)}]"

        if fname in existing_files:
            print(f"  {idx_str} SKIP: {fname} (already exists in destination)")
            skipped += 1
            continue

        category, similarity = classify_image(
            model, preprocess, src_path, ref_embeddings, ref_labels, DEVICE
        )
        if category is None:
            errors += 1
            continue

        dest_dir = output_dirs[category]
        dest_path = os.path.join(dest_dir, fname)

        try:
            shutil.copy2(src_path, dest_path)
            print(f"  {idx_str} COPY: {fname} -> {category}/ (top-1 sim={similarity:.3f})")
            results[category].append(fname)
            copied += 1
            existing_files.add(fname)
        except Exception as e:
            print(f"  {idx_str} ERROR: {fname} - {e}")
            errors += 1

    # --- Summary ---
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for cat, dir_path in output_dirs.items():
        count = len(results.get(cat, []))
        print(f"  {dir_path}: {count} images")
    print(f"\n  Copied:     {copied}")
    print(f"  Skipped:    {skipped}")
    print(f"  Errors:     {errors}")
    remaining = len([f for f in os.listdir(SOURCE_DIR)
                     if os.path.splitext(f)[1].lower() in EXTENSIONS])
    print(f"  Remaining in '{SOURCE_DIR}': {remaining}")


if __name__ == "__main__":
    main()