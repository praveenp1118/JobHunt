"""
Seed script — run once after migrations.
Creates:
  - Admin user (Praveen)
  - Industry verticals (36)
  - Functional disciplines (15)
  - Country rules (NL, EU, SG, Dubai, India)
  - Action pricing (Wallet plan)
  - Platform feeds + target companies

Usage (inside backend container):
  python -m app.seeds
"""
import asyncio
import uuid
from passlib.context import CryptContext

from app.database import AsyncSessionLocal
from app.config import settings
from app.models.user import User, UserCredentials, UserPreferences, UserRole, UserPlan
from app.models.wallet import Wallet, WalletTransaction, ActionPricing
from app.models.domain import IndustryVertical, FunctionalDiscipline, CountryMaster, UserFeed, UserTargetCompany

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Industry verticals ────────────────────────────────────────────────────────
INDUSTRY_VERTICALS = [
    {"code": "FP", "label": "Fintech & Payments",         "detection_keywords": "payments,fintech,BNPL,neobank,card,acquiring,issuing,PCI,financial crime"},
    {"code": "EC", "label": "eCommerce & Marketplace",    "detection_keywords": "marketplace,GMV,ecommerce,seller,buyer,cart,checkout,fulfillment,SKU"},
    {"code": "AI", "label": "AI & Data Products",         "detection_keywords": "LLM,AI,ML,machine learning,model,inference,RAG,GenAI,NLP,vector"},
    {"code": "BS", "label": "B2B SaaS & Platform",        "detection_keywords": "SaaS,B2B,enterprise,ARR,churn,NRR,MRR,PLG,CRM,API platform"},
    {"code": "SC", "label": "Supply Chain & Operations",  "detection_keywords": "supply chain,logistics,fulfillment,warehouse,WMS,routing,inventory,3PL"},
    {"code": "HD", "label": "HealthTech & Digital Health", "detection_keywords": "health,clinical,EMR,EHR,telemedicine,FDA,HIPAA,patient,care"},
    {"code": "ED", "label": "EdTech & Learning",          "detection_keywords": "education,learning,LMS,courses,students,curriculum,edtech"},
    {"code": "BL", "label": "Banking & Financial Services", "detection_keywords": "banking,retail banking,core banking,loans,deposits,KYC,AML,Basel"},
    {"code": "IS", "label": "InsurTech",                  "detection_keywords": "insurance,underwriting,claims,actuarial,InsurTech,policy"},
    {"code": "WT", "label": "WealthTech & Investment",    "detection_keywords": "wealth,investment,portfolio,trading,brokerage,robo-advisor,AUM"},
    {"code": "CW", "label": "Crypto & Web3",              "detection_keywords": "crypto,blockchain,DeFi,NFT,Web3,smart contract,token,wallet"},
    {"code": "RO", "label": "Retail & Commerce",          "detection_keywords": "retail,omnichannel,POS,brick and mortar,inventory,merchandising"},
    {"code": "CF", "label": "FMCG & Consumer Goods",      "detection_keywords": "FMCG,consumer goods,CPG,brand,shelf,distribution,trade marketing"},
    {"code": "LF", "label": "Luxury & Lifestyle",         "detection_keywords": "luxury,premium,lifestyle,fashion,brand experience,exclusivity"},
    {"code": "FB", "label": "Food & Beverage Tech",       "detection_keywords": "food delivery,restaurant,QSR,food tech,dark kitchen,ordering"},
    {"code": "LL", "label": "Logistics & Last Mile",      "detection_keywords": "logistics,last mile,delivery,fleet,route optimization,courier"},
    {"code": "MI", "label": "Manufacturing & Industry",   "detection_keywords": "manufacturing,factory,IoT,industrial,OEM,production,quality"},
    {"code": "EU", "label": "Energy & Utilities",         "detection_keywords": "energy,utilities,grid,renewable,solar,EV,smart meter"},
    {"code": "AG", "label": "AgriTech",                   "detection_keywords": "agriculture,farming,crop,agritech,precision farming,supply chain"},
    {"code": "DT", "label": "Developer Tools & DevOps",   "detection_keywords": "developer tools,DevOps,CI/CD,platform engineering,infrastructure,SDK"},
    {"code": "CY", "label": "Cybersecurity",              "detection_keywords": "security,cybersecurity,SIEM,zero trust,threat,compliance,SOC"},
    {"code": "CI", "label": "Cloud & Infrastructure",     "detection_keywords": "cloud,AWS,Azure,GCP,infrastructure,Kubernetes,serverless"},
    {"code": "IH", "label": "IoT & Hardware",             "detection_keywords": "IoT,hardware,embedded,firmware,sensors,device,connected"},
    {"code": "DR", "label": "Deep Tech & Research",       "detection_keywords": "deep tech,R&D,research,quantum,semiconductor,photonics"},
    {"code": "CA", "label": "Consumer Apps & Social",     "detection_keywords": "consumer app,social,DAU,MAU,engagement,retention,growth"},
    {"code": "ME", "label": "Media & Content",            "detection_keywords": "media,content,streaming,OTT,publishing,advertising,creator"},
    {"code": "GI", "label": "Gaming & Interactive",       "detection_keywords": "gaming,game,interactive,esports,virtual,AR,VR,metaverse"},
    {"code": "TV", "label": "Travel & Hospitality",       "detection_keywords": "travel,hotel,booking,OTA,hospitality,airline,GDS"},
    {"code": "PR", "label": "PropTech & Real Estate",     "detection_keywords": "real estate,property,proptech,mortgage,rental,CRE"},
    {"code": "BP", "label": "BioTech & Life Sciences",    "detection_keywords": "biotech,pharma,life sciences,clinical trials,drug discovery"},
    {"code": "CS", "label": "ClimateTech & Sustainability", "detection_keywords": "climate,sustainability,carbon,ESG,clean tech,net zero"},
    {"code": "GP", "label": "GovTech & Public Sector",    "detection_keywords": "government,public sector,civic tech,GovTech,digital transformation"},
    {"code": "HR", "label": "HRTech & Future of Work",    "detection_keywords": "HR,HRtech,recruitment,ATS,payroll,workforce,people analytics"},
    {"code": "LC", "label": "LegalTech",                  "detection_keywords": "legal,legaltech,contract,compliance,e-discovery,law"},
    {"code": "MA", "label": "MarTech & AdTech",           "detection_keywords": "marketing,MarTech,AdTech,CRM,CDP,attribution,programmatic"},
    {"code": "DA", "label": "Data & Analytics Platforms", "detection_keywords": "data platform,analytics,BI,data warehouse,ETL,dbt,Snowflake"},
]

# ── Functional disciplines ────────────────────────────────────────────────────
FUNCTIONAL_DISCIPLINES = [
    {"code": "PL", "label": "Platform & API Products",       "detection_keywords": "platform,API,developer,integration,ecosystem,SDK"},
    {"code": "GR", "label": "Growth & Monetisation",         "detection_keywords": "growth,monetisation,revenue,funnel,conversion,pricing,PLG"},
    {"code": "CU", "label": "Consumer & UX Products",        "detection_keywords": "consumer,UX,user experience,engagement,retention,DAU"},
    {"code": "ML", "label": "AI & ML Product Management",    "detection_keywords": "AI product,ML,model,inference,AI/ML PM,data product"},
    {"code": "DP", "label": "Data & Analytics PM",           "detection_keywords": "data PM,analytics,BI,dashboard,insights,data product"},
    {"code": "IV", "label": "Infra & DevTools PM",           "detection_keywords": "infrastructure,developer tools,DevOps,SRE,platform engineering"},
    {"code": "EB", "label": "Enterprise & B2B Sales-led",    "detection_keywords": "enterprise,B2B,sales-led,RFP,procurement,account management"},
    {"code": "OA", "label": "Operations & Automation",       "detection_keywords": "operations,automation,workflow,efficiency,process,ops PM"},
    {"code": "IE", "label": "Integration & Ecosystem",       "detection_keywords": "integration,ecosystem,partner,marketplace,connector,middleware"},
    {"code": "ZO", "label": "Zero to One & New Ventures",    "detection_keywords": "0 to 1,zero to one,new product,venture,greenfield,startup"},
    {"code": "TT", "label": "Turnaround & Transformation",   "detection_keywords": "turnaround,transformation,restructure,cost reduction,digital transformation"},
    {"code": "IM", "label": "International Expansion",       "detection_keywords": "international,expansion,localisation,market entry,global,multi-market"},
    {"code": "MG", "label": "M&A & Integration",             "detection_keywords": "M&A,acquisition,integration,due diligence,PMI,merger"},
    {"code": "PB", "label": "P&L Ownership & Biz Building",  "detection_keywords": "P&L,profit and loss,revenue,business owner,general manager,commercial"},
    {"code": "MN", "label": "Marketplace & Network Effects", "detection_keywords": "marketplace,network effects,two-sided,liquidity,supply,demand"},
]

# ── Country rules ─────────────────────────────────────────────────────────────
COUNTRY_RULES = [
    {
        "country_code": "NL",
        "country_name": "Netherlands",
        "privacy_law": "GDPR",
        "phone_on_cv": False,
        "remove_photo": True,
        "remove_dob": True,
        "remove_marital_status": True,
        "relocation_note": "Open to relocation to Netherlands",
        "lines_to_add": '["GDPR: Data processed lawfully for recruitment purposes only."]',
        "is_approved": True,
    },
    {
        "country_code": "EU",
        "country_name": "EU (General)",
        "privacy_law": "GDPR",
        "phone_on_cv": False,
        "remove_photo": True,
        "remove_dob": True,
        "remove_marital_status": True,
        "relocation_note": "Open to relocation within EU",
        "lines_to_add": '["GDPR: Data processed lawfully for recruitment purposes only."]',
        "is_approved": True,
    },
    {
        "country_code": "SG",
        "country_name": "Singapore",
        "privacy_law": "PDPA",
        "phone_on_cv": True,
        "remove_photo": False,
        "remove_dob": False,
        "remove_marital_status": False,
        "relocation_note": "Open to relocating to Singapore",
        "lines_to_add": '[]',
        "is_approved": True,
    },
    {
        "country_code": "DU",
        "country_name": "Dubai / UAE",
        "privacy_law": "UAE PDPL",
        "phone_on_cv": True,
        "remove_photo": False,
        "remove_dob": False,
        "remove_marital_status": False,
        "relocation_note": "Open to relocating to Dubai",
        "lines_to_add": '[]',
        "is_approved": True,
    },
    {
        "country_code": "IN",
        "country_name": "India",
        "privacy_law": "DPDPA 2023",
        "phone_on_cv": True,
        "remove_photo": False,
        "remove_dob": False,
        "remove_marital_status": False,
        "relocation_note": None,
        "lines_to_add": '[]',
        "is_approved": True,
    },
]

# ── Action pricing (Wallet plan) ──────────────────────────────────────────────
ACTION_PRICING = [
    {"action_key": "jd_parse",          "price_paise": 100,  "description": "Parse JD from any source"},
    {"action_key": "score_s1",          "price_paise": 100,  "description": "Base fit score — master CV vs JD"},
    {"action_key": "score_s2_s3",       "price_paise": 150,  "description": "Tailored score + factual integrity"},
    {"action_key": "domain_cv_gen",     "price_paise": 300,  "description": "Generate domain CV with change log"},
    {"action_key": "tailor_cl_email",   "price_paise": 250,  "description": "Tailor CV + cover letter + email draft (batched)"},
    {"action_key": "interview_prep",    "price_paise": 200,  "description": "Company brief + questions + STAR stories + salary benchmark"},
    {"action_key": "followup_draft",    "price_paise": 50,   "description": "Draft follow-up email"},
    {"action_key": "gmail_classify",    "price_paise": 10,   "description": "Classify recruiter email (batched, per email)"},
    {"action_key": "apify_job",         "price_paise": 25,   "description": "Per job found via Apify scraping"},
]

# ── Platform target companies ─────────────────────────────────────────────────
PLATFORM_COMPANIES = [
    # NL
    {"company_name": "Adyen",        "market": "NL", "career_page_url": "https://careers.adyen.com"},
    {"company_name": "Booking.com",  "market": "NL", "career_page_url": "https://careers.booking.com"},
    {"company_name": "TomTom",       "market": "NL", "career_page_url": "https://careers.tomtom.com"},
    {"company_name": "ASML",         "market": "NL", "career_page_url": "https://www.asml.com/en/careers"},
    {"company_name": "Philips",      "market": "NL", "career_page_url": "https://www.careers.philips.com"},
    {"company_name": "ING",          "market": "NL", "career_page_url": "https://www.ing.jobs"},
    {"company_name": "Coolblue",     "market": "NL", "career_page_url": "https://www.coolblue.nl/vacatures"},
    {"company_name": "Picnic",       "market": "NL", "career_page_url": "https://picnic.app/nl/vacatures"},
    {"company_name": "Mollie",       "market": "NL", "career_page_url": "https://jobs.mollie.com"},
    {"company_name": "Databricks",   "market": "EU", "career_page_url": "https://www.databricks.com/company/careers"},
    {"company_name": "Workato",      "market": "EU", "career_page_url": "https://www.workato.com/careers"},
    # Dubai
    {"company_name": "Noon",         "market": "Dubai", "career_page_url": "https://careers.noon.com"},
    {"company_name": "Careem",       "market": "Dubai", "career_page_url": "https://careers.careem.com"},
    {"company_name": "Talabat",      "market": "Dubai", "career_page_url": "https://careers.talabat.com"},
    {"company_name": "Dubizzle",     "market": "Dubai", "career_page_url": "https://dubizzle.com/careers"},
    {"company_name": "Tabby",        "market": "Dubai", "career_page_url": "https://tabby.ai/careers"},
    # Singapore
    {"company_name": "Grab",         "market": "SG", "career_page_url": "https://grab.careers"},
    {"company_name": "Shopee / Sea", "market": "SG", "career_page_url": "https://careers.shopee.sg"},
    {"company_name": "Lazada",       "market": "SG", "career_page_url": "https://careers.lazada.com"},
    {"company_name": "Gojek",        "market": "SG", "career_page_url": "https://www.gojek.com/careers"},
    # India
    {"company_name": "PhonePe",      "market": "IN", "career_page_url": "https://careers.phonepe.com"},
    {"company_name": "Razorpay",     "market": "IN", "career_page_url": "https://razorpay.com/jobs"},
    {"company_name": "Meesho",       "market": "IN", "career_page_url": "https://meesho.io/careers"},
]

# ── Platform feeds ────────────────────────────────────────────────────────────
PLATFORM_FEEDS = [
    {"feed_type": "rss",   "name": "Indeed NL",      "url_or_actor": "https://nl.indeed.com/rss?q=head+of+product&l=Netherlands"},
    {"feed_type": "rss",   "name": "Indeed AE",      "url_or_actor": "https://ae.indeed.com/rss?q=head+of+product&l=Dubai"},
    {"feed_type": "rss",   "name": "Indeed SG",      "url_or_actor": "https://sg.indeed.com/rss?q=head+of+product+ai&l=Singapore"},
    {"feed_type": "rss",   "name": "Indeed IN",      "url_or_actor": "https://in.indeed.com/rss?q=head+of+product+AI&l=Bengaluru"},
    {"feed_type": "rss",   "name": "Jobicy NL",      "url_or_actor": "https://jobicy.com/feed/job_feed?search_keywords=head+of+product&search_region=netherlands"},
    {"feed_type": "apify", "name": "LinkedIn Jobs",  "url_or_actor": "apify/linkedin-jobs-scraper"},
    {"feed_type": "apify", "name": "Google Jobs",    "url_or_actor": "bebity/google-jobs-scraper"},
]


async def seed():
    async with AsyncSessionLocal() as session:
        print("🌱 Starting seed...")

        # ── Admin user ────────────────────────────────────────────────────────
        from sqlalchemy import select
        result = await session.execute(
            select(User).where(User.email == settings.admin_email)
        )
        existing_admin = result.scalar_one_or_none()

        if not existing_admin:
            admin = User(
                id=uuid.uuid4(),
                email=settings.admin_email,
                hashed_password=pwd_context.hash(settings.admin_initial_password),
                name="Praveen Prakash",
                role=UserRole.admin,
                plan=UserPlan.default,
                is_active=True,
                is_verified=True,
                is_superuser=False,
            )
            session.add(admin)
            await session.flush()

            # Wallet with ₹20 starter gift
            wallet = Wallet(user_id=admin.id, balance_paise=2000)
            session.add(wallet)
            await session.flush()

            # Starter gift transaction
            txn = WalletTransaction(
                wallet_id=wallet.id,
                user_id=admin.id,
                transaction_type="gift",
                description="Welcome gift on signup",
                amount_paise=2000,
                balance_after_paise=2000,
            )
            session.add(txn)

            # User credentials (empty — admin fills in Settings)
            creds = UserCredentials(user_id=admin.id)
            session.add(creds)

            # Default preferences
            prefs = UserPreferences(user_id=admin.id)
            session.add(prefs)

            print(f"✅ Admin user created: {settings.admin_email}")
        else:
            admin = existing_admin
            print(f"⏭️  Admin user already exists: {settings.admin_email}")

        # ── Industry verticals ────────────────────────────────────────────────
        for iv in INDUSTRY_VERTICALS:
            result = await session.execute(
                select(IndustryVertical).where(IndustryVertical.code == iv["code"])
            )
            if not result.scalar_one_or_none():
                session.add(IndustryVertical(
                    **iv,
                    is_active=True,
                    is_approved=True,
                    approved_by=admin.id,
                ))
        print(f"✅ {len(INDUSTRY_VERTICALS)} industry verticals seeded")

        # ── Functional disciplines ────────────────────────────────────────────
        for fd in FUNCTIONAL_DISCIPLINES:
            result = await session.execute(
                select(FunctionalDiscipline).where(FunctionalDiscipline.code == fd["code"])
            )
            if not result.scalar_one_or_none():
                session.add(FunctionalDiscipline(
                    **fd,
                    is_active=True,
                    is_approved=True,
                    approved_by=admin.id,
                ))
        print(f"✅ {len(FUNCTIONAL_DISCIPLINES)} functional disciplines seeded")

        # ── Country rules ─────────────────────────────────────────────────────
        for cr in COUNTRY_RULES:
            result = await session.execute(
                select(CountryMaster).where(CountryMaster.country_code == cr["country_code"])
            )
            if not result.scalar_one_or_none():
                session.add(CountryMaster(
                    **cr,
                    is_active=True,
                    approved_by=admin.id,
                ))
        print(f"✅ {len(COUNTRY_RULES)} country rules seeded")

        # ── Action pricing ────────────────────────────────────────────────────
        for ap in ACTION_PRICING:
            result = await session.execute(
                select(ActionPricing).where(ActionPricing.action_key == ap["action_key"])
            )
            if not result.scalar_one_or_none():
                session.add(ActionPricing(**ap))
        print(f"✅ {len(ACTION_PRICING)} action pricing entries seeded")

        # ── Platform companies (linked to admin as placeholder user) ──────────
        for co in PLATFORM_COMPANIES:
            result = await session.execute(
                select(UserTargetCompany).where(
                    UserTargetCompany.company_name == co["company_name"],
                    UserTargetCompany.is_platform == True,
                )
            )
            if not result.scalar_one_or_none():
                session.add(UserTargetCompany(
                    user_id=admin.id,
                    is_platform=True,
                    is_active=True,
                    **co,
                ))
        print(f"✅ {len(PLATFORM_COMPANIES)} platform companies seeded")

        # ── Platform feeds ────────────────────────────────────────────────────
        for feed in PLATFORM_FEEDS:
            result = await session.execute(
                select(UserFeed).where(
                    UserFeed.name == feed["name"],
                    UserFeed.is_platform == True,
                )
            )
            if not result.scalar_one_or_none():
                session.add(UserFeed(
                    user_id=admin.id,
                    is_platform=True,
                    is_active=True,
                    **feed,
                ))
        print(f"✅ {len(PLATFORM_FEEDS)} platform feeds seeded")

        await session.commit()
        print("🎉 Seed complete!")


if __name__ == "__main__":
    asyncio.run(seed())
