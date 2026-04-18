"""SSIM structural similarity calculation using OpenCV."""

from __future__ import annotations

import numpy as np


def ssim(img_a: np.ndarray, img_b: np.ndarray) -> float:
    """Compute the structural similarity (SSIM) between two images.

    Both images must be BGR or grayscale numpy arrays.  If they differ in
    size, they are resized to the smaller dimensions before comparison.

    Returns:
        A float in [0, 1] where 1 means identical.
    """
    a = _to_gray(img_a)
    b = _to_gray(img_b)

    # Resize to matching dimensions (use the smaller)
    if a.shape != b.shape:
        target_h = min(a.shape[0], b.shape[0])
        target_w = min(a.shape[1], b.shape[1])
        a = _resize(a, target_w, target_h)
        b = _resize(b, target_w, target_h)

    return _compute_ssim(a, b)


def ssim_bytes(a: bytes, b: bytes) -> float:
    """Compute SSIM between two PNG/JPEG byte strings.

    Args:
        a: First image as bytes.
        b: Second image as bytes.

    Returns:
        SSIM score in [0, 1].
    """
    arr_a = _bytes_to_ndarray(a)
    arr_b = _bytes_to_ndarray(b)
    return ssim(arr_a, arr_b)


def _to_gray(img: np.ndarray) -> np.ndarray:
    """Convert BGR image to grayscale if needed."""
    if img.ndim == 3 and img.shape[2] == 3:
        try:
            import cv2

            return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        except ImportError:
            return np.dot(img[..., :3], [0.114, 0.587, 0.299]).astype(np.uint8)
    return img


def _resize(img: np.ndarray, w: int, h: int) -> np.ndarray:
    """Resize image to target dimensions."""
    try:
        import cv2

        return cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
    except ImportError:
        y_indices = np.linspace(0, img.shape[0] - 1, h).astype(int)
        x_indices = np.linspace(0, img.shape[1] - 1, w).astype(int)
        return img[np.ix_(y_indices, x_indices)]


def _bytes_to_ndarray(data: bytes) -> np.ndarray:
    """Decode image bytes to numpy array."""
    import cv2

    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Failed to decode image bytes")
    return img


def _compute_ssim(a: np.ndarray, b: np.ndarray) -> float:
    """Compute SSIM using Gaussian-weighted statistics.

    Uses the standard formula from Wang et al. (2004) with a sliding
    Gaussian window of size 11x11 and sigma 1.5.
    """
    C1 = (0.01 * 255) ** 2
    C2 = (0.03 * 255) ** 2

    a = a.astype(np.float64)
    b = b.astype(np.float64)

    # Use Gaussian blur for local statistics
    try:
        import cv2

        mu_a = cv2.GaussianBlur(a, (11, 11), 1.5)
        mu_b = cv2.GaussianBlur(b, (11, 11), 1.5)
    except ImportError:
        mu_a = _uniform_filter(a, 11)
        mu_b = _uniform_filter(b, 11)

    mu_a_sq = mu_a * mu_a
    mu_b_sq = mu_b * mu_b
    mu_ab = mu_a * mu_b

    try:
        import cv2

        sigma_a_sq = cv2.GaussianBlur(a * a, (11, 11), 1.5) - mu_a_sq
        sigma_b_sq = cv2.GaussianBlur(b * b, (11, 11), 1.5) - mu_b_sq
        sigma_ab = cv2.GaussianBlur(a * b, (11, 11), 1.5) - mu_ab
    except ImportError:
        sigma_a_sq = _uniform_filter(a * a, 11) - mu_a_sq
        sigma_b_sq = _uniform_filter(b * b, 11) - mu_b_sq
        sigma_ab = _uniform_filter(a * b, 11) - mu_ab

    numerator = (2 * mu_ab + C1) * (2 * sigma_ab + C2)
    denominator = (mu_a_sq + mu_b_sq + C1) * (sigma_a_sq + sigma_b_sq + C2)

    ssim_map = numerator / denominator
    return float(np.mean(ssim_map))


def _uniform_filter(img: np.ndarray, size: int) -> np.ndarray:
    """Simple uniform (mean) filter using cumulative sums."""
    pad = size // 2
    padded = np.pad(img, pad, mode="reflect")
    cumsum = np.cumsum(np.cumsum(padded, axis=0), axis=1)

    h, w = img.shape
    result = (
        cumsum[size : size + h, size : size + w]
        - cumsum[:h, size : size + w]
        - cumsum[size : size + h, :w]
        + cumsum[:h, :w]
    ) / (size * size)
    return result
