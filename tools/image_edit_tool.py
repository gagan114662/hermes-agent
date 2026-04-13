"""
Image editing tools using Pillow.

Provides basic image manipulation operations: resize, crop, annotate, and format conversion.

Available tools:
- image_resize: Resize images with optional aspect ratio preservation
- image_crop: Crop rectangular regions from images
- image_annotate: Add text annotations to images
- image_convert: Convert between image formats

All operations preserve EXIF data where possible and handle common formats
(PNG, JPEG, WEBP, GIF, BMP, TIFF).

Env vars:
    None required (Pillow is the only dependency)
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _expand_path(path_str: str) -> str:
    """Expand home directory and resolve to absolute path."""
    expanded = os.path.expanduser(path_str)
    resolved = os.path.realpath(expanded)
    return resolved


def _get_image_info(image_path: str) -> Dict[str, Any]:
    """Get width, height, format, and size in bytes for an image."""
    from PIL import Image

    path = Path(_expand_path(image_path))
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    with Image.open(path) as img:
        width, height = img.size
        image_format = img.format or "UNKNOWN"

    size_bytes = path.stat().st_size

    return {
        "width": width,
        "height": height,
        "format": image_format,
        "size_bytes": size_bytes,
    }


def image_resize(
    input_path: str,
    output_path: str,
    width: Optional[int] = None,
    height: Optional[int] = None,
    maintain_aspect_ratio: bool = True,
) -> str:
    """
    Resize an image to the specified dimensions.

    If maintain_aspect_ratio is True and only one dimension is provided,
    the other is calculated proportionally.

    Args:
        input_path: Source image path
        output_path: Output image path
        width: Target width in pixels (optional)
        height: Target height in pixels (optional)
        maintain_aspect_ratio: If True, maintain aspect ratio when resizing

    Returns:
        JSON with output_path, dimensions, format, and size_bytes
    """
    try:
        from PIL import Image

        input_path_expanded = _expand_path(input_path)
        output_path_expanded = _expand_path(output_path)

        # Ensure output directory exists
        Path(output_path_expanded).parent.mkdir(parents=True, exist_ok=True)

        if not Path(input_path_expanded).exists():
            raise FileNotFoundError(f"Input image not found: {input_path}")

        if width is None and height is None:
            raise ValueError("At least one of width or height must be specified")

        with Image.open(input_path_expanded) as img:
            original_width, original_height = img.size

            # Calculate target dimensions
            if maintain_aspect_ratio:
                if width is not None and height is None:
                    # Calculate height from width
                    aspect_ratio = original_height / original_width
                    height = int(width * aspect_ratio)
                elif height is not None and width is None:
                    # Calculate width from height
                    aspect_ratio = original_width / original_height
                    width = int(height * aspect_ratio)
                # If both are specified, use them as-is (don't maintain aspect)
            else:
                # If aspect ratio not maintained and only one dimension given, error
                if width is None or height is None:
                    raise ValueError(
                        "Both width and height required when maintain_aspect_ratio=False"
                    )

            # Perform resize
            resized = img.resize((width, height), Image.Resampling.LANCZOS)

            # Save with quality preservation
            save_kwargs = {}
            if output_path_expanded.lower().endswith(('.jpg', '.jpeg')):
                save_kwargs['quality'] = 95
                save_kwargs['optimize'] = True

            resized.save(output_path_expanded, **save_kwargs)

        # Get output image info
        info = _get_image_info(output_path_expanded)
        info["output_path"] = output_path_expanded

        logger.info(
            "Image resized: %s (%dx%d) -> %s (%dx%d)",
            input_path, original_width, original_height,
            output_path, width, height
        )

        return json.dumps(info)

    except Exception as e:
        error_msg = f"Error resizing image: {str(e)}"
        logger.error("%s", error_msg, exc_info=True)
        return json.dumps({"error": error_msg})


def image_crop(
    input_path: str,
    output_path: str,
    left: int,
    top: int,
    right: int,
    bottom: int,
) -> str:
    """
    Crop a rectangular region from an image.

    Args:
        input_path: Source image path
        output_path: Output image path
        left: Left edge x-coordinate (pixels)
        top: Top edge y-coordinate (pixels)
        right: Right edge x-coordinate (pixels)
        bottom: Bottom edge y-coordinate (pixels)

    Returns:
        JSON with output_path, dimensions, format, and size_bytes
    """
    try:
        from PIL import Image

        input_path_expanded = _expand_path(input_path)
        output_path_expanded = _expand_path(output_path)

        # Ensure output directory exists
        Path(output_path_expanded).parent.mkdir(parents=True, exist_ok=True)

        if not Path(input_path_expanded).exists():
            raise FileNotFoundError(f"Input image not found: {input_path}")

        if not (isinstance(left, int) and isinstance(top, int) and
                isinstance(right, int) and isinstance(bottom, int)):
            raise ValueError("left, top, right, bottom must be integers")

        if left >= right or top >= bottom:
            raise ValueError("Invalid crop box: left < right and top < bottom required")

        with Image.open(input_path_expanded) as img:
            original_width, original_height = img.size

            # Validate crop box is within image bounds
            if left < 0 or top < 0 or right > original_width or bottom > original_height:
                raise ValueError(
                    f"Crop box out of bounds. Image is {original_width}x{original_height}, "
                    f"crop box is ({left}, {top}, {right}, {bottom})"
                )

            # Perform crop
            cropped = img.crop((left, top, right, bottom))

            # Save with quality preservation
            save_kwargs = {}
            if output_path_expanded.lower().endswith(('.jpg', '.jpeg')):
                save_kwargs['quality'] = 95
                save_kwargs['optimize'] = True

            cropped.save(output_path_expanded, **save_kwargs)

        # Get output image info
        info = _get_image_info(output_path_expanded)
        info["output_path"] = output_path_expanded

        logger.info(
            "Image cropped: %s -> %s (box: %d,%d,%d,%d)",
            input_path, output_path, left, top, right, bottom
        )

        return json.dumps(info)

    except Exception as e:
        error_msg = f"Error cropping image: {str(e)}"
        logger.error("%s", error_msg, exc_info=True)
        return json.dumps({"error": error_msg})


def image_annotate(
    input_path: str,
    output_path: str,
    text: str,
    position: str = "bottom",
    font_size: int = 24,
    color: str = "white",
    background_color: str = "black",
) -> str:
    """
    Add text annotation to an image.

    Text is rendered at the specified position with a background color behind it.

    Args:
        input_path: Source image path
        output_path: Output image path
        text: Text to add
        position: Text position - "top", "bottom", or "center" (default: "bottom")
        font_size: Font size in pixels (default: 24)
        color: Text color as CSS color name or hex code (default: "white")
        background_color: Background color as CSS color name or hex code (default: "black")

    Returns:
        JSON with output_path, dimensions, format, and size_bytes
    """
    try:
        from PIL import Image, ImageDraw, ImageFont

        input_path_expanded = _expand_path(input_path)
        output_path_expanded = _expand_path(output_path)

        # Ensure output directory exists
        Path(output_path_expanded).parent.mkdir(parents=True, exist_ok=True)

        if not Path(input_path_expanded).exists():
            raise FileNotFoundError(f"Input image not found: {input_path}")

        if position not in ("top", "bottom", "center"):
            raise ValueError("position must be 'top', 'bottom', or 'center'")

        with Image.open(input_path_expanded) as img:
            # Convert to RGB if necessary (for formats that don't support text)
            if img.mode in ('RGBA', 'LA', 'PA'):
                img = img.convert('RGB')
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            # Create a copy to annotate
            annotated = img.copy()
            draw = ImageDraw.Draw(annotated)

            # Try to load a nice font, fall back to default
            font = None
            try:
                # Try common system font paths
                font_paths = [
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux
                    "/System/Library/Fonts/Helvetica.ttc",  # macOS
                    "C:\\Windows\\Fonts\\arial.ttf",  # Windows
                ]
                for font_path in font_paths:
                    if Path(font_path).exists():
                        font = ImageFont.truetype(font_path, font_size)
                        break
            except Exception:
                pass

            if font is None:
                # Fall back to default font
                font = ImageFont.load_default()

            # Get text bounding box to size background
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]

            # Add padding around text
            padding = 10
            img_width, img_height = annotated.size

            # Calculate position
            if position == "top":
                x = (img_width - text_width) // 2
                y = padding
            elif position == "center":
                x = (img_width - text_width) // 2
                y = (img_height - text_height) // 2
            else:  # "bottom"
                x = (img_width - text_width) // 2
                y = img_height - text_height - padding

            # Draw background
            bg_bbox = [
                x - padding,
                y - padding,
                x + text_width + padding,
                y + text_height + padding,
            ]
            draw.rectangle(bg_bbox, fill=background_color)

            # Draw text
            draw.text((x, y), text, fill=color, font=font)

            # Save with quality preservation
            save_kwargs = {}
            if output_path_expanded.lower().endswith(('.jpg', '.jpeg')):
                save_kwargs['quality'] = 95
                save_kwargs['optimize'] = True

            annotated.save(output_path_expanded, **save_kwargs)

        # Get output image info
        info = _get_image_info(output_path_expanded)
        info["output_path"] = output_path_expanded
        info["text_added"] = text
        info["position"] = position

        logger.info(
            "Text annotation added: %s -> %s (text: %r, pos: %s)",
            input_path, output_path, text[:50], position
        )

        return json.dumps(info)

    except Exception as e:
        error_msg = f"Error annotating image: {str(e)}"
        logger.error("%s", error_msg, exc_info=True)
        return json.dumps({"error": error_msg})


def image_convert(
    input_path: str,
    output_path: str,
    quality: int = 85,
) -> str:
    """
    Convert an image between formats.

    Output format is determined from the output_path extension.
    Supports: PNG, JPEG, WEBP, GIF, BMP, TIFF

    Args:
        input_path: Source image path
        output_path: Output image path (format inferred from extension)
        quality: JPEG quality (1-100, default: 85). Ignored for other formats.

    Returns:
        JSON with output_path, dimensions, format, and size_bytes
    """
    try:
        from PIL import Image

        input_path_expanded = _expand_path(input_path)
        output_path_expanded = _expand_path(output_path)

        # Ensure output directory exists
        Path(output_path_expanded).parent.mkdir(parents=True, exist_ok=True)

        if not Path(input_path_expanded).exists():
            raise FileNotFoundError(f"Input image not found: {input_path}")

        # Determine output format from extension
        ext = Path(output_path_expanded).suffix.lower()
        valid_formats = {
            '.jpg': 'JPEG',
            '.jpeg': 'JPEG',
            '.png': 'PNG',
            '.webp': 'WEBP',
            '.gif': 'GIF',
            '.bmp': 'BMP',
            '.tiff': 'TIFF',
            '.tif': 'TIFF',
        }

        if ext not in valid_formats:
            raise ValueError(
                f"Unsupported output format '{ext}'. "
                f"Supported: {', '.join(valid_formats.keys())}"
            )

        output_format = valid_formats[ext]

        if not (1 <= quality <= 100):
            raise ValueError(f"quality must be between 1 and 100, got {quality}")

        with Image.open(input_path_expanded) as img:
            # Convert to appropriate mode for target format
            if output_format == 'JPEG':
                # JPEG doesn't support transparency
                if img.mode in ('RGBA', 'LA', 'PA'):
                    # Create white background
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = background
                elif img.mode != 'RGB':
                    img = img.convert('RGB')
            elif output_format == 'PNG':
                if img.mode not in ('RGB', 'RGBA', 'L', 'LA'):
                    img = img.convert('RGBA')
            elif output_format == 'WEBP':
                if img.mode not in ('RGB', 'RGBA'):
                    img = img.convert('RGBA')
            elif output_format == 'GIF':
                # GIF requires conversion to palette mode
                if img.mode not in ('P', 'L'):
                    img = img.convert('P')

            # Save with appropriate quality settings
            save_kwargs = {'format': output_format}
            if output_format == 'JPEG':
                save_kwargs['quality'] = quality
                save_kwargs['optimize'] = True
            elif output_format == 'WEBP':
                save_kwargs['quality'] = quality
            elif output_format == 'PNG':
                save_kwargs['optimize'] = True

            img.save(output_path_expanded, **save_kwargs)

        # Get output image info
        info = _get_image_info(output_path_expanded)
        info["output_path"] = output_path_expanded
        info["original_format"] = Path(input_path_expanded).suffix.upper()

        logger.info(
            "Image converted: %s (%s) -> %s (%s)",
            input_path, info["original_format"],
            output_path, output_format
        )

        return json.dumps(info)

    except Exception as e:
        error_msg = f"Error converting image: {str(e)}"
        logger.error("%s", error_msg, exc_info=True)
        return json.dumps({"error": error_msg})


def _check_image_edit() -> bool:
    """Check if Pillow is available."""
    try:
        from PIL import Image
        return True
    except ImportError:
        return False


# =============================================================================
# Registry
# =============================================================================
from tools.registry import registry

IMAGE_RESIZE_SCHEMA = {
    "name": "image_resize",
    "description": "Resize an image to specified dimensions. Can maintain aspect ratio when only one dimension is provided.",
    "parameters": {
        "type": "object",
        "properties": {
            "input_path": {
                "type": "string",
                "description": "Path to the source image file",
            },
            "output_path": {
                "type": "string",
                "description": "Path where the resized image will be saved",
            },
            "width": {
                "type": "integer",
                "description": "Target width in pixels (optional)",
            },
            "height": {
                "type": "integer",
                "description": "Target height in pixels (optional)",
            },
            "maintain_aspect_ratio": {
                "type": "boolean",
                "description": "If true and only one dimension given, scale proportionally (default: true)",
            },
        },
        "required": ["input_path", "output_path"],
    },
}

IMAGE_CROP_SCHEMA = {
    "name": "image_crop",
    "description": "Crop a rectangular region from an image.",
    "parameters": {
        "type": "object",
        "properties": {
            "input_path": {
                "type": "string",
                "description": "Path to the source image file",
            },
            "output_path": {
                "type": "string",
                "description": "Path where the cropped image will be saved",
            },
            "left": {
                "type": "integer",
                "description": "Left edge x-coordinate in pixels",
            },
            "top": {
                "type": "integer",
                "description": "Top edge y-coordinate in pixels",
            },
            "right": {
                "type": "integer",
                "description": "Right edge x-coordinate in pixels",
            },
            "bottom": {
                "type": "integer",
                "description": "Bottom edge y-coordinate in pixels",
            },
        },
        "required": ["input_path", "output_path", "left", "top", "right", "bottom"],
    },
}

IMAGE_ANNOTATE_SCHEMA = {
    "name": "image_annotate",
    "description": "Add text annotation to an image with customizable position, font size, and colors.",
    "parameters": {
        "type": "object",
        "properties": {
            "input_path": {
                "type": "string",
                "description": "Path to the source image file",
            },
            "output_path": {
                "type": "string",
                "description": "Path where the annotated image will be saved",
            },
            "text": {
                "type": "string",
                "description": "Text to add to the image",
            },
            "position": {
                "type": "string",
                "enum": ["top", "bottom", "center"],
                "description": "Where to place the text (default: bottom)",
            },
            "font_size": {
                "type": "integer",
                "description": "Font size in pixels (default: 24)",
            },
            "color": {
                "type": "string",
                "description": "Text color as CSS color name or hex code (default: white)",
            },
            "background_color": {
                "type": "string",
                "description": "Background color as CSS color name or hex code (default: black)",
            },
        },
        "required": ["input_path", "output_path", "text"],
    },
}

IMAGE_CONVERT_SCHEMA = {
    "name": "image_convert",
    "description": "Convert an image between formats (PNG, JPEG, WEBP, GIF, BMP, TIFF). Format is determined from output path extension.",
    "parameters": {
        "type": "object",
        "properties": {
            "input_path": {
                "type": "string",
                "description": "Path to the source image file",
            },
            "output_path": {
                "type": "string",
                "description": "Path where the converted image will be saved. Format inferred from extension.",
            },
            "quality": {
                "type": "integer",
                "description": "JPEG/WEBP quality (1-100, default: 85). Ignored for other formats.",
            },
        },
        "required": ["input_path", "output_path"],
    },
}


def _handle_image_resize(args: Dict[str, Any], **kw: Any) -> str:
    return image_resize(
        input_path=args["input_path"],
        output_path=args["output_path"],
        width=args.get("width"),
        height=args.get("height"),
        maintain_aspect_ratio=args.get("maintain_aspect_ratio", True),
    )


def _handle_image_crop(args: Dict[str, Any], **kw: Any) -> str:
    return image_crop(
        input_path=args["input_path"],
        output_path=args["output_path"],
        left=args["left"],
        top=args["top"],
        right=args["right"],
        bottom=args["bottom"],
    )


def _handle_image_annotate(args: Dict[str, Any], **kw: Any) -> str:
    return image_annotate(
        input_path=args["input_path"],
        output_path=args["output_path"],
        text=args["text"],
        position=args.get("position", "bottom"),
        font_size=args.get("font_size", 24),
        color=args.get("color", "white"),
        background_color=args.get("background_color", "black"),
    )


def _handle_image_convert(args: Dict[str, Any], **kw: Any) -> str:
    return image_convert(
        input_path=args["input_path"],
        output_path=args["output_path"],
        quality=args.get("quality", 85),
    )


registry.register(
    name="image_resize",
    toolset="image_edit",
    schema=IMAGE_RESIZE_SCHEMA,
    handler=_handle_image_resize,
    check_fn=_check_image_edit,
    emoji="📐",
)

registry.register(
    name="image_crop",
    toolset="image_edit",
    schema=IMAGE_CROP_SCHEMA,
    handler=_handle_image_crop,
    check_fn=_check_image_edit,
    emoji="✂️",
)

registry.register(
    name="image_annotate",
    toolset="image_edit",
    schema=IMAGE_ANNOTATE_SCHEMA,
    handler=_handle_image_annotate,
    check_fn=_check_image_edit,
    emoji="🖊️",
)

registry.register(
    name="image_convert",
    toolset="image_edit",
    schema=IMAGE_CONVERT_SCHEMA,
    handler=_handle_image_convert,
    check_fn=_check_image_edit,
    emoji="🎨",
)
