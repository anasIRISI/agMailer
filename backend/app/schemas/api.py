from pydantic import BaseModel, Field, field_validator, ConfigDict
from email_validator import validate_email, EmailNotValidError

def clean_email(value: str) -> str:
    try:
        return validate_email(value.strip(), check_deliverability=False).normalized.lower()
    except EmailNotValidError as exc:
        raise ValueError('Adresse email invalide.') from exc

class RecipientInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: str
    entreprise: str = Field(default='', max_length=300)
    nom_recruteur: str = Field(default='', max_length=300)
    poste: str = Field(default='', max_length=300)
    excluded: bool = False
    letter_document_id: int | None = None
    _email = field_validator('email')(clean_email)

class TemplateInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1, max_length=100000)
    signature: str = Field(default='', max_length=5000)
    is_html: bool = False

    @field_validator('subject')
    @classmethod
    def subject_header(cls, value):
        if '\r' in value or '\n' in value:
            raise ValueError('L’objet doit tenir sur une ligne.')
        return value

class CampaignInput(TemplateInput):
    recipient_ids: list[int] = Field(min_length=1, max_length=10000)
    document_ids: list[int] = Field(default_factory=list, max_length=10)
    simulation: bool = True
    daily_limit: int = Field(default=30, ge=1, le=500)
    campaign_limit: int = Field(default=100, ge=1, le=10000)
    delay_seconds: int = Field(default=60, ge=10, le=86400)

class PreviewInput(TemplateInput):
    recipient_id: int

class ActionInput(BaseModel):
    confirm: bool = False

class SettingsInput(BaseModel):
    daily_limit: int = Field(default=30, ge=1, le=500)
    delay_seconds: int = Field(default=60, ge=10, le=86400)
