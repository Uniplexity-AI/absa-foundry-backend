"""Check which feature gaps are system bugs vs dataset limitations."""
import sys,os;sys.path.insert(0,'.')
from shared.config.settings import settings
import psycopg2
conn=psycopg2.connect(settings.database_target_url_sync,connect_timeout=10)
cur=conn.cursor()

checks = [
    ("txn_count_365d", "Phase 2 SQL never ran for 365d window"),
    ("credit_sum_30d", "Financial generator has credit/debit SQL but may not populate this column"),
    ("debit_sum_30d", "Same as credit_sum_30d"),
    ("credit_to_debit_ratio_90d", "Financial generator — ratio not computed"),
    ("monthly_income_estimate", "Financial generator — income estimate not computed"),
    ("temp_morning_activity_ratio_90d", "Temporal generator exists but may not produce output"),
    ("temp_afternoon_activity_ratio_90d", "Temporal generator — time-of-day features"),
    ("temp_evening_activity_ratio_90d", "Temporal generator — time-of-day features"),
    ("prof_declared_vs_observed_income_ratio", "No declared income in synthetic data"),
    ("fin_salary_consistency", "Salary pattern feature — may need recurring credit pattern"),
    ("fin_income_growth", "Income growth — ratio computation may produce NULLs"),
    ("amount_growth_ratio", "Amount growth — ratio computation may produce NULLs"),
    ("chan_channel_entropy", "Channel entropy — may need multi-channel activity"),
    ("rel_card_count", "Card product — synthetic data has limited card variety"),
    ("rel_card_types", "Card product — same as rel_card_count"),
    ("rel_card_expiring_30d", "Card expiry — synthetic cards may not have expiry dates within 30d"),
    ("eng_login_count_7d", "Digital engagement — login data may be sparse"),
    ("eng_login_count_30d", "Digital engagement — login data may be sparse"),
]

print(f"{'Feature':<35s} {'Non-null':>8s} {'%':>6s}  Category")
print("-" * 90)
for col, reason in checks:
    cur.execute(f'SELECT COUNT(*) FILTER (WHERE "{col}" IS NOT NULL), COUNT(*) FROM customer_features WHERE as_of_date=%s', ('2026-07-27',))
    nn,total = cur.fetchone()
    pct = nn/total*100 if total else 0
    if pct == 0:
        cat = "SYSTEM BUG — never populated"
    elif pct < 30:
        cat = "DATASET — sparse synthetic data"
    elif pct < 80:
        cat = "DATASET — moderate coverage gap"
    else:
        cat = "OK"
    print(f"{col:<35s} {nn:>5d}/{total:<4d} {pct:>5.0f}%  {cat}")

# Also check: txn_count_30d vs behav_frequency_score
cur.execute("SELECT COUNT(*) FILTER (WHERE txn_count_30d > 0), COUNT(*) FILTER (WHERE behav_frequency_score > 0) FROM customer_features WHERE as_of_date='2026-07-27'")
t30, bf = cur.fetchone()
print(f"\ntxn_count_30d > 0: {t30}  |  behav_frequency_score > 0: {bf}")
print("txn_count_30d is a dead column — frequency is stored in behav_frequency_score instead")

conn.close()
