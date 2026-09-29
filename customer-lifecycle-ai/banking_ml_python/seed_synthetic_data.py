#!/usr/bin/env python3
"""
Seed PostgreSQL with a *minimal* synthetic dataset to exercise the full ETL.

Default footprint is small on purpose:
  - 15 customers
  - ~4 months of history (covers 30d / 90d feature windows)
  - ~90 days forward (covers churn labels; a few CLV fee rows)
  - light transaction volume

Enough to run every SQL path without loading 2 years of data.

Usage:
  export PGHOST=localhost PGPORT=5432 PGDATABASE=absa_dw PGUSER=... PGPASSWORD=...

  python seed_synthetic_data.py
  python seed_synthetic_data.py --customers 15 --snapshot 2024-06-01

Then:
  python test_extract.py --limit 5 --snapshot 2024-06-01
  python run_extract.py --mode training --models all --snapshot 2024-06-01
"""
from __future__ import annotations

import argparse
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dateutil.relativedelta import relativedelta

from config.db import get_conn, get_connection_params
from config.settings import SQL_DIR

# Minimal windows that still hit 30d / 90d feature logic and churn forward horizon
DEFAULT_HISTORY_MONTHS = 4
DEFAULT_FORWARD_DAYS = 90

SEXES = ["M", "F"]
SEGMENTS = ["RETAIL", "AFFLUENT", "SME", "YOUTH", "MASS"]
RISK_LEVELS = ["LOW", "MEDIUM", "HIGH"]
CREDIT_RATINGS = ["A", "B", "C", "D", "E"]
CHANNELS = ["BRANCH", "ONLINE", "MOBILE", "AGENT", "CALL_CENTRE"]
REGIONS = ["Lusaka", "Copperbelt", "Southern", "Eastern", "Northern", "Central"]
TOWNS = ["Lusaka", "Ndola", "Kitwe", "Livingstone", "Chipata", "Kabwe", "Solwezi"]
JOBS = ["Teacher", "Nurse", "Engineer", "Trader", "Driver", "Clerk", "Manager", "Farmer"]
EMP_TYPES = ["PERMANENT", "CONTRACT", "SELF_EMPLOYED", "CASUAL"]
EMP_STATUS = ["ACTIVE", "ACTIVE", "ACTIVE", "ON_LEAVE"]
NARRATIVES_CREDIT = [
    "SALARY PAYMENT",
    "WAGES DEPOSIT",
    "PAYROLL TRANSFER",
    "CASH DEPOSIT",
    "MOBILE MONEY IN",
    "RTGS CREDIT",
]
NARRATIVES_DEBIT = [
    "POS PURCHASE",
    "ATM WITHDRAWAL",
    "UTILITY PAYMENT",
    "MOBILE MONEY OUT",
    "TRANSFER TO OTHER BANK",
    "SWIFT PAYMENT",
    "AIRTIME PURCHASE",
]
OTHER_BANKS = ["ZANACO", "STANBIC", "FNB", "INVESTRUST", None, None]
CARD_GRADES = ["A", "B", "C", "D", None]


def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def month_start(d: date) -> date:
    return d.replace(day=1)


def create_schema() -> None:
    ddl = (SQL_DIR / "00_create_synthetic_schema.sql").read_text()
    print("Creating synthetic schema...")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(ddl)
        conn.commit()
    print("  Schema ready.")


def truncate_all() -> None:
    tables = [
        "a_brains_trans_zam_base_entries_zm",
        "ebox_loan_details",
        "s_caas_sparrow_zam_base_crdrep",
        "a_africa_zam_base_customer_employment_daily_zm",
        "a_africa_zam_base_customers_new",
        "a_africa_zam_base_customer",
    ]
    with get_conn() as conn:
        with conn.cursor() as cur:
            for t in tables:
                cur.execute(f"TRUNCATE TABLE {t} CASCADE")
        conn.commit()
    print("  Tables truncated.")


def generate_customers(n: int, rng: random.Random) -> list[dict]:
    # Fixed mix so every behaviour path is covered even with small N
    profiles_cycle = ["active", "salary", "quiet", "dormant_risk"]
    customers = []
    for i in range(1, n + 1):
        cid = f"C{i:05d}"
        profile = profiles_cycle[(i - 1) % len(profiles_cycle)]
        customers.append(
            {
                "customer_number": cid,
                "length_years": rng.randint(0, 10),
                "length_months": rng.randint(0, 11),
                "sex": rng.choice(SEXES),
                "market_segment": rng.choice(SEGMENTS),
                "risk_level": rng.choice(RISK_LEVELS),
                "risk_score": round(rng.uniform(100, 900), 2),
                "credit_rating": rng.choice(CREDIT_RATINGS),
                "solicitation_channel": rng.choice(CHANNELS),
                "current_count": rng.randint(0, 2),
                "savings_count": rng.randint(0, 2),
                "investment_count": rng.randint(0, 1),
                "secured_count": rng.randint(0, 1),
                "unsecured_count": rng.randint(0, 2),
                "trade_or_insurance_count": rng.randint(0, 1),
                "district_or_region": rng.choice(REGIONS),
                "town_or_city": rng.choice(TOWNS),
                "country": "Zambia",
                "gross_income": round(rng.uniform(2000, 25000), 2),
                "other_income": round(rng.uniform(0, 3000), 2),
                "job_title": rng.choice(JOBS),
                "employment_type": rng.choice(EMP_TYPES),
                "employment_status": rng.choice(EMP_STATUS),
                "designation": rng.choice(["Junior", "Senior", "Lead", "Officer"]),
                "nature_of_business": rng.choice(["Services", "Trade", "Agriculture", "Mining"]),
                "profile": profile,
            }
        )
    return customers


def insert_customers(customers: list[dict]) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            for c in customers:
                cur.execute(
                    """
                    INSERT INTO a_africa_zam_base_customer
                        (customer_number, length_years, length_months)
                    VALUES (%(customer_number)s, %(length_years)s, %(length_months)s)
                    """,
                    c,
                )
                cur.execute(
                    """
                    INSERT INTO a_africa_zam_base_customers_new (
                        customer_number, sex, market_segment, risk_level, risk_score,
                        credit_rating, solicitation_channel,
                        current_count, savings_count, investment_count,
                        secured_count, unsecured_count, trade_or_insurance_count
                    ) VALUES (
                        %(customer_number)s, %(sex)s, %(market_segment)s, %(risk_level)s,
                        %(risk_score)s, %(credit_rating)s, %(solicitation_channel)s,
                        %(current_count)s, %(savings_count)s, %(investment_count)s,
                        %(secured_count)s, %(unsecured_count)s, %(trade_or_insurance_count)s
                    )
                    """,
                    c,
                )
                cur.execute(
                    """
                    INSERT INTO a_africa_zam_base_customer_employment_daily_zm (
                        customer_number, district_or_region, town_or_city, country,
                        gross_income, other_income, job_title, employment_type,
                        employment_status, designation, nature_of_business
                    ) VALUES (
                        %(customer_number)s, %(district_or_region)s, %(town_or_city)s,
                        %(country)s, %(gross_income)s, %(other_income)s, %(job_title)s,
                        %(employment_type)s, %(employment_status)s, %(designation)s,
                        %(nature_of_business)s
                    )
                    """,
                    c,
                )
        conn.commit()
    print(f"  Inserted {len(customers)} customers.")


def _add_txn(rows, cid, acct, d, amount, narrative, rng):
    rows.append(
        {
            "customer_number": cid,
            "account_number": acct,
            "bus_date": d,
            "posting_date": d,
            "local_amount": amount,
            "transaction_code": "CR" if amount > 0 else "DR",
            "process_code": "SYN",
            "narrative": narrative,
            "terminal_number": f"T{rng.randint(1, 20):03d}",
            "branch_number": f"B{rng.randint(1, 10):03d}",
            "source_system": "SYNTH",
        }
    )


def generate_transactions(
    customers: list[dict],
    hist_start: date,
    snapshot_end: date,
    forward_end: date,
    rng: random.Random,
) -> list[dict]:
    """Sparse but deliberate txns so every feature window has something to aggregate."""
    rows: list[dict] = []
    hist_days = max((snapshot_end - hist_start).days, 1)
    fut_days = max((forward_end - snapshot_end).days, 1)

    for c in customers:
        cid = c["customer_number"]
        acct = f"A{cid[1:]}"
        profile = c["profile"]

        # --- History: a handful of points in 30d / 90d / older buckets ---
        if profile == "active":
            anchors = [5, 15, 25, 45, 70, 100]  # days before snapshot_end
            last_gap = rng.randint(1, 10)
        elif profile == "salary":
            anchors = [3, 10, 33, 63, 95]  # roughly monthly + recent
            last_gap = rng.randint(1, 8)
        elif profile == "quiet":
            anchors = [40, 80]
            last_gap = rng.randint(35, 80)
        else:  # dormant_risk — old activity only, high recency
            anchors = [min(hist_days - 1, 200), min(hist_days - 1, 250)]
            last_gap = rng.randint(min(hist_days - 1, 220), min(hist_days, 300))

        # Force last txn date (controls recency_days)
        last_txn = snapshot_end - timedelta(days=min(last_gap, hist_days))
        if last_txn < hist_start:
            last_txn = hist_start
        dates = {last_txn}
        for days_ago in anchors:
            d = snapshot_end - timedelta(days=days_ago)
            if hist_start <= d <= snapshot_end:
                dates.add(d)

        for d in sorted(dates):
            if profile == "salary" and d.day <= 7:
                amt = round(c["gross_income"] * rng.uniform(0.85, 1.05), 2)
                narr = rng.choice(["SALARY PAYMENT", "WAGES DEPOSIT", "PAYROLL TRANSFER"])
            elif rng.random() < 0.4:
                amt = round(rng.uniform(50, 5000), 2)
                narr = rng.choice(NARRATIVES_CREDIT)
            else:
                amt = -round(rng.uniform(20, 3000), 2)
                if rng.random() < 0.1:
                    amt = -round(rng.uniform(10000, 20000), 2)  # large outflow
                narr = rng.choice(NARRATIVES_DEBIT)
            _add_txn(rows, cid, acct, d, amt, narr, rng)

        # --- Forward (post-snapshot): enough for churn gap logic ---
        if profile in ("active", "salary"):
            fut_offsets = [10, 25, 50]
        elif profile == "quiet":
            fut_offsets = [40]
        else:
            fut_offsets = []  # no future activity → dormancy can trigger

        for off in fut_offsets:
            if off > fut_days:
                continue
            d = snapshot_end + timedelta(days=off)
            amt = round(rng.uniform(-1500, 2000), 2) or 100.0
            narr = rng.choice(NARRATIVES_CREDIT if amt > 0 else NARRATIVES_DEBIT)
            _add_txn(rows, cid, acct, d, amt, narr, rng)

    return rows


def insert_transactions(rows: list[dict]) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            for r in rows:
                cur.execute(
                    """
                    INSERT INTO a_brains_trans_zam_base_entries_zm (
                        customer_number, account_number, bus_date, posting_date,
                        local_amount, transaction_code, process_code, narrative,
                        terminal_number, branch_number, source_system
                    ) VALUES (
                        %(customer_number)s, %(account_number)s, %(bus_date)s, %(posting_date)s,
                        %(local_amount)s, %(transaction_code)s, %(process_code)s, %(narrative)s,
                        %(terminal_number)s, %(branch_number)s, %(source_system)s
                    )
                    """,
                    r,
                )
        conn.commit()
    print(f"  Inserted {len(rows)} transactions.")


def generate_loans(
    customers: list[dict],
    hist_start: date,
    snapshot_end: date,
    forward_end: date,
    rng: random.Random,
) -> list[dict]:
    """Few fee rows in history + a couple after snapshot for CLV targets."""
    rows = []
    hist_days = max((snapshot_end - hist_start).days, 1)
    fut_days = max((forward_end - snapshot_end).days, 1)

    for c in customers:
        cid = c["customer_number"]
        base = {
            "customer_number": cid,
            "net_monthly_sal": round(c["gross_income"] * rng.uniform(0.7, 1.0), 2),
            "interest_rate": round(rng.uniform(8, 28), 4),
            "outstanding_mortgage": (
                round(rng.uniform(10000, 150000), 2) if rng.random() < 0.25 else None
            ),
            "other_bank_name": rng.choice(OTHER_BANKS),
            "other_bank_cde": None,
            "campaign_cde": f"CAMP{rng.randint(1, 10):02d}" if rng.random() < 0.4 else None,
            "barclaycard_grade": rng.choice(CARD_GRADES),
        }
        if base["other_bank_name"]:
            base["other_bank_cde"] = base["other_bank_name"][:4]

        # 2–4 historical fee events
        for days_ago in (10, 40, 80)[: rng.randint(2, 3)]:
            d = snapshot_end - timedelta(days=min(days_ago, hist_days))
            if d < hist_start:
                d = hist_start
            rows.append(
                {
                    **base,
                    "event_start_date": d,
                    "load_date": d,
                    "fee_amt": round(rng.uniform(5, 150), 2),
                    "insurance_amt": round(rng.uniform(0, 30), 2) if rng.random() < 0.3 else 0,
                }
            )

        # 1–2 future fee events (CLV label)
        if rng.random() < 0.75:
            for off in (20, 60)[: rng.randint(1, 2)]:
                if off > fut_days:
                    continue
                d = snapshot_end + timedelta(days=off)
                rows.append(
                    {
                        **base,
                        "event_start_date": d,
                        "load_date": d,
                        "fee_amt": round(rng.uniform(5, 180), 2),
                        "insurance_amt": 0,
                    }
                )
    return rows


def insert_loans(rows: list[dict]) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            for r in rows:
                cur.execute(
                    """
                    INSERT INTO ebox_loan_details (
                        customer_number, event_start_date, load_date, fee_amt, insurance_amt,
                        net_monthly_sal, interest_rate, outstanding_mortgage,
                        other_bank_name, other_bank_cde, campaign_cde, barclaycard_grade
                    ) VALUES (
                        %(customer_number)s, %(event_start_date)s, %(load_date)s,
                        %(fee_amt)s, %(insurance_amt)s, %(net_monthly_sal)s, %(interest_rate)s,
                        %(outstanding_mortgage)s, %(other_bank_name)s, %(other_bank_cde)s,
                        %(campaign_cde)s, %(barclaycard_grade)s
                    )
                    """,
                    r,
                )
        conn.commit()
    print(f"  Inserted {len(rows)} loan/fee rows.")


def generate_cards(
    customers: list[dict],
    hist_start: date,
    snapshot_end: date,
    rng: random.Random,
) -> list[dict]:
    rows = []
    for c in customers:
        if rng.random() < 0.5:
            continue
        cid = c["customer_number"]
        open_d = snapshot_end - timedelta(days=rng.randint(20, max((snapshot_end - hist_start).days, 20)))
        if open_d < hist_start:
            open_d = hist_start
        close_d = None
        if rng.random() < 0.2:
            close_d = open_d + timedelta(days=rng.randint(30, 90))
            if close_d > snapshot_end:
                close_d = snapshot_end - timedelta(days=1)
        rows.append(
            {
                "customer_number": cid,
                "crd_acct_num": f"CARD{cid[1:]}",
                "eff_sta_dte": open_d,
                "eff_end_dte": close_d,
            }
        )
    return rows


def insert_cards(rows: list[dict]) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            for r in rows:
                cur.execute(
                    """
                    INSERT INTO s_caas_sparrow_zam_base_crdrep (
                        customer_number, crd_acct_num, eff_sta_dte, eff_end_dte
                    ) VALUES (
                        %(customer_number)s, %(crd_acct_num)s, %(eff_sta_dte)s, %(eff_end_dte)s
                    )
                    """,
                    r,
                )
        conn.commit()
    print(f"  Inserted {len(rows)} card rows.")


def print_counts() -> None:
    tables = [
        "a_africa_zam_base_customer",
        "a_africa_zam_base_customers_new",
        "a_africa_zam_base_customer_employment_daily_zm",
        "a_brains_trans_zam_base_entries_zm",
        "ebox_loan_details",
        "s_caas_sparrow_zam_base_crdrep",
    ]
    print("\nRow counts:")
    with get_conn() as conn:
        with conn.cursor() as cur:
            for t in tables:
                cur.execute(f"SELECT COUNT(*) FROM {t}")
                print(f"  {t}: {cur.fetchone()[0]:,}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed minimal synthetic data to test the full Banking ML ETL"
    )
    parser.add_argument("--customers", type=int, default=15, help="Customer count (default 15)")
    parser.add_argument("--snapshot", type=str, default="2024-06-01", help="Snapshot month YYYY-MM-DD")
    parser.add_argument(
        "--history-months",
        type=int,
        default=DEFAULT_HISTORY_MONTHS,
        help=f"Months of history to generate (default {DEFAULT_HISTORY_MONTHS}, not 24)",
    )
    parser.add_argument(
        "--forward-days",
        type=int,
        default=DEFAULT_FORWARD_DAYS,
        help=f"Days after snapshot for labels (default {DEFAULT_FORWARD_DAYS})",
    )
    parser.add_argument("--seed", type=int, default=42, help="RNG seed")
    parser.add_argument(
        "--skip-schema",
        action="store_true",
        help="Truncate + reload only (do not drop/recreate tables)",
    )
    args = parser.parse_args()

    snap = month_start(parse_date(args.snapshot))
    snapshot_end = snap + relativedelta(months=1) - timedelta(days=1)
    hist_start = month_start(snap - relativedelta(months=args.history_months))
    forward_end = snapshot_end + timedelta(days=args.forward_days)

    params = get_connection_params()
    safe = {k: ("***" if k == "password" else v) for k, v in params.items()}
    print("=" * 60)
    print("Synthetic data seeder (minimal test set)")
    print(f"  DB: {safe}")
    print(f"  customers={args.customers}  snapshot={snap}  snapshot_end={snapshot_end}")
    print(f"  history_start={hist_start}  forward_end={forward_end}  seed={args.seed}")
    print("=" * 60)

    rng = random.Random(args.seed)

    try:
        if not args.skip_schema:
            create_schema()
        else:
            truncate_all()

        customers = generate_customers(args.customers, rng)
        insert_customers(customers)

        txns = generate_transactions(customers, hist_start, snapshot_end, forward_end, rng)
        insert_transactions(txns)

        loans = generate_loans(customers, hist_start, snapshot_end, forward_end, rng)
        insert_loans(loans)

        cards = generate_cards(customers, hist_start, snapshot_end, rng)
        insert_cards(cards)

        print_counts()
        print("\nDone. Next:")
        print(f"  python test_extract.py --limit 5 --snapshot {snap.isoformat()}")
        print(f"  python run_extract.py --mode training --models all --snapshot {snap.isoformat()}")
        print("=" * 60)
    except Exception as e:
        print(f"\nFAILED: {e}")
        import traceback

        traceback.print_exc()
        print("\nCheck PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD and that Postgres is running.")
        sys.exit(1)


if __name__ == "__main__":
    main()
