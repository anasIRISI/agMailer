"""Validate PDF attachments without rejecting harmless viewer preferences."""
import io

from pypdf import PdfReader
from pypdf.generic import ArrayObject, DictionaryObject, NullObject


class PDFValidationError(ValueError):
    pass


def _destination(value):
    """A named destination or a page/view array is navigation, not executable code."""
    if hasattr(value, 'get_object'):
        value = value.get_object()
    if isinstance(value, str):
        return bool(value)
    return (
        isinstance(value, ArrayObject)
        and len(value) >= 2
        and value[1] in ('/XYZ', '/Fit', '/FitH', '/FitV', '/FitR', '/FitB', '/FitBH', '/FitBV')
    )


def _safe_open_action(value):
    if hasattr(value, 'get_object'):
        value = value.get_object()
    if value is None or isinstance(value, NullObject):
        return True
    if isinstance(value, DictionaryObject):
        # Permit only local page navigation, without a chained action.
        return value.get('/S') == '/GoTo' and '/Next' not in value and _destination(value.get('/D'))
    return _destination(value)


def validate_pdf(content: bytes):
    try:
        # Non-strict parsing repairs recoverable cross-reference/export defects.
        # It does not execute PDF actions or rewrite the uploaded bytes.
        reader = PdfReader(io.BytesIO(content), strict=False)
        if reader.is_encrypted:
            raise PDFValidationError('Ce PDF est chiffré ou protégé. Exportez une copie PDF sans protection, puis réimportez-la.')
        if not len(reader.pages):
            raise PDFValidationError('Ce PDF ne contient aucune page.')
        root = reader.trailer['/Root']
        names = root.get('/Names', {})
        if hasattr(names, 'get_object'):
            names = names.get_object()
        if not isinstance(names, dict) and not isinstance(names, NullObject):
            raise PDFValidationError('La structure de ce PDF est illisible. Exportez-le à nouveau au format PDF.')
        has_javascript = isinstance(names, dict) and '/JavaScript' in names
        if not _safe_open_action(root.get('/OpenAction')) or '/AA' in root or has_javascript:
            raise PDFValidationError('Ce PDF contient une action automatique ou du JavaScript. Exportez une version PDF statique, puis réimportez-la.')
    except PDFValidationError:
        raise
    except Exception:
        raise PDFValidationError('Impossible de lire ce PDF. Vérifiez qu’il s’ouvre dans votre lecteur PDF, puis exportez-le à nouveau si nécessaire.') from None
