"""One-off: create the Razorpay TEST Plan for AIJobsHunt Pro (₹500/mo, GST-inclusive).
Run once, paste the printed plan_id into RAZORPAY_PLAN_ID. TEST keys only.

  docker-compose exec backend python -m app.scripts.create_razorpay_plan
"""
import razorpay

from app.config import settings


def main():
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise SystemExit("Set RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET (test keys) first.")
    if settings.razorpay_key_id.startswith("rzp_live_"):
        raise SystemExit("Refusing to run with a LIVE key — use rzp_test_ keys for Stage 1-2.")

    client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))
    plan = client.plan.create({
        "period": "monthly",
        "interval": 1,
        "item": {
            "name": "AIJobsHunt Pro",
            "amount": 50000,       # paise = ₹500, INCLUSIVE of 18% GST (decision locked)
            "currency": "INR",
            "description": "AIJobsHunt Pro — platform fee, BYOK AI at cost. Auto-renews monthly.",
        },
        "notes": {"env": "test", "product": "aijobshunt_pro"},
    })
    print("✅ Razorpay TEST plan created.")
    print(f"   plan_id = {plan['id']}")
    print("   → paste into RAZORPAY_PLAN_ID in your .env")


if __name__ == "__main__":
    main()
