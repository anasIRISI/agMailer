import re
import html
import bleach
from email.message import EmailMessage
from email.utils import formatdate
from app.core.config import DATA_DIR, MAX_ATTACHMENTS

FALLBACKS = {'entreprise': 'votre entreprise', 'nom_recruteur': 'Madame, Monsieur', 'poste': 'informatique'}

def sanitize_html(value):
    return bleach.clean(value, tags=['p', 'br', 'strong', 'em', 'b', 'i', 'ul', 'ol', 'li'], attributes={}, strip=True)

def plain_text(value):
    value = re.sub(r'<(?:br\s*/?|/p|/li)>', '\n', value, flags=re.I)
    return html.unescape(bleach.clean(value, tags=[], strip=True)).strip()

def render(subject, body, signature, recipient, is_html=False):
    values = {key: getattr(recipient, key, '') or fallback for key, fallback in FALLBACKS.items()}
    def substitute(text, escaped=False):
        def replace(match):
            key = match.group(1).strip()
            if key not in values:
                raise ValueError(f'Variable inconnue : {key}')
            return html.escape(values[key]) if escaped else values[key]
        return re.sub(r'{{\s*([^{}]+?)\s*}}', replace, text)
    rendered_subject = substitute(subject)
    if '\n' in rendered_subject or '\r' in rendered_subject:
        raise ValueError('Une variable contient un saut de ligne dans l’objet.')
    text = substitute(body, is_html)
    if signature:
        text += ('<br><br>' if is_html else '\n\n') + substitute(signature, is_html)
    return rendered_subject, sanitize_html(text) if is_html else text

def build_message(delivery, sender, documents):
    message = EmailMessage()
    message['From'] = sender
    message['To'] = delivery.email
    message['Subject'] = delivery.subject
    message['Date'] = formatdate(localtime=False)
    message['Message-ID'] = delivery.message_id
    message.set_content(plain_text(delivery.body) if delivery.is_html else delivery.body)
    if delivery.is_html:
        message.add_alternative(sanitize_html(delivery.body), subtype='html')
    if sum(doc.size for doc in documents) > MAX_ATTACHMENTS:
        raise ValueError('Les pièces jointes dépassent 15 Mo.')
    for doc in documents:
        path = DATA_DIR / 'documents' / doc.storage_name
        content = path.read_bytes()
        import hashlib
        if hashlib.sha256(content).hexdigest() != doc.sha256:
            raise ValueError('Une pièce jointe a été modifiée sur le disque.')
        message.add_attachment(content, maintype='application', subtype='pdf', filename=doc.name)
    return message
