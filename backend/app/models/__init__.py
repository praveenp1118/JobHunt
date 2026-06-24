# Import all models here so Alembic autogenerate can detect them
from app.models.user import User, UserCredentials, UserPreferences, UserRole, UserPlan
from app.models.wallet import Wallet, WalletTransaction, ActionPricing
from app.models.domain import IndustryVertical, FunctionalDiscipline, CountryMaster, UserFeed, UserTargetCompany
from app.models.cv import MasterCV, MasterCVVersion, DomainCV, DomainCVVersion, TailoredCV, ChangeLog
from app.models.job import Job, EmailThread
from app.models.admin import RunLog, ErrorLog, InviteCode

__all__ = [
    "User", "UserCredentials", "UserPreferences", "UserRole", "UserPlan",
    "Wallet", "WalletTransaction", "ActionPricing",
    "IndustryVertical", "FunctionalDiscipline", "CountryMaster", "UserFeed", "UserTargetCompany",
    "MasterCV", "MasterCVVersion", "DomainCV", "DomainCVVersion", "TailoredCV", "ChangeLog",
    "Job", "EmailThread",
    "RunLog", "ErrorLog", "InviteCode",
]
