"""Generate a comprehensive Excel workbook containing two distinct customer profiles
with all fields required for model predictions and frontend display.

Workbook Structure:
  1. Combined_Customer_Dataset: 360-degree view (Personal, Account, AI Outputs, and all 85 Feature Store columns)
  2. Customer_Master: Exact 16 columns matching public.customers_clean (ready for ingest)
  3. Customer_Features: Exact 85 columns matching public.customer_features (ready for ingest)
  4. Data_Dictionary: Exhaustive field catalogue with types, model usage, and frontend locations
"""

import os
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# Colors (Absa Theme)
BURGUNDY_DARK = "4F0014"   # Primary Brand Deep Burgundy
BURGUNDY = "8A002E"        # Absa Red / Passion
BURGUNDY_LIGHT = "FBEAEF"  # Light tint for headers/accents
SLATE_HEADER = "1E293B"    # Dark Charcoal for technical tables
SLATE_LIGHT = "F1F5F9"     # Light grey
BORDER_GREY = "CBD5E1"     # Slate 300
ACCENT_GREEN = "15803D"    # Healthy / Low Risk
ACCENT_GREEN_BG = "DCFCE7"
ACCENT_RED = "B91C1C"      # High Risk / Churn
ACCENT_RED_BG = "FEE2E2"
ACCENT_AMBER = "B45309"    # Watch / Medium Risk
ACCENT_AMBER_BG = "FEF3C7"
ACCENT_BLUE = "1D4ED8"     # Info / General
ACCENT_BLUE_BG = "DBEAFE"

def get_border(thin=True):
    b = Side(style='thin' if thin else 'medium', color=BORDER_GREY)
    return Border(left=b, right=b, top=b, bottom=b)

def get_thick_bottom_border():
    thin = Side(style='thin', color=BORDER_GREY)
    thick = Side(style='medium', color="8A002E")
    return Border(left=thin, right=thin, top=thin, bottom=thick)

def create_dataset():
    wb = openpyxl.Workbook()
    
    # ----------------------------------------------------
    # DATA DEFINITIONS FOR BOTH CUSTOMERS
    # ----------------------------------------------------
    
    # Customer 1: Chileshe Mwape (Premier / Thriving / Low Churn Risk)
    master_c1 = {
        "customer_id": "CUST0009001",
        "account_number": "ZMW-8820-1092",
        "status": "Active",
        "full_name": "Chileshe Mwape",
        "date_of_birth": "1985-04-12",
        "national_id": "284910/11/1",
        "mobile_number": "+260977123456",
        "next_of_kin_name": "Mwape Chileshe",
        "next_of_kin_relationship": "Spouse",
        "next_of_kin_phone": "+260977654321",
        "gender": "FEMALE",
        "branch_code": "BR001",
        "customer_since_date": "2018-05-14",
        "kyc_tier": "TIER_1",
        "nationality": "ZM",
        "market_segment_code": "85",
        "market_segment": "Premier",
        "assigned_rm": "Lindiwe Banda"
    }

    features_c1 = {
        "customer_id": "CUST0009001",
        "as_of_date": "2026-07-27",
        "computed_at": "2026-07-27 10:00:00",
        "days_since_last_txn": 2,
        "days_since_first_txn": 2980,
        "txn_count_30d": 42,
        "txn_count_90d": 128,
        "txn_count_180d": 250,
        "txn_count_365d": 490,
        "avg_days_between_txn": 0.70,
        "distinct_channels_90d": 4,
        "distinct_txn_types_90d": 6,
        "dominant_channel": "MOBILE_APP",
        "total_amount_90d": 285000.00,
        "avg_amount_90d": 2226.56,
        "total_amount_180d": 540000.00,
        "amount_growth_ratio": 0.15,
        "amount_stddev_90d": 1450.20,
        "credit_sum_30d": 98000.00,
        "debit_sum_30d": 82000.00,
        "credit_to_debit_ratio_90d": 1.19,
        "balance_trend_90d": "RISING",
        "monthly_income_estimate": 95000.00,
        "has_salary_credit": True,
        "behav_txn_count_7d": 11,
        "behav_active_days_90d": 74,
        "behav_inactive_days_90d": 16,
        "behav_recency_score": 0.98,
        "behav_frequency_score": 0.92,
        "behav_diversity_score": 0.85,
        "behav_activity_consistency": 0.91,
        "fin_total_credit_90d": 310000.00,
        "fin_total_debit_90d": 260000.00,
        "fin_median_txn_amount_90d": 1800.00,
        "fin_salary_consistency": 0.96,
        "fin_income_growth": 0.08,
        "chan_mobile_ratio_90d": 0.65,
        "chan_atm_ratio_90d": 0.10,
        "chan_branch_ratio_90d": 0.05,
        "chan_digital_adoption_score": 0.88,
        "chan_channel_entropy": 1.25,
        "customer_tenure_days": 2980,
        "customer_segment": "Premier Banking",
        "age_years": 41,
        "onboarding_channel": "BRANCH",
        "target_lifecycle_stage": "GROWING",
        "engagement_score": 88.5,
        "txn_frequency_trend": 0.12,
        "inactivity_streak_days": 0,
        "balance_growth_pct": 18.50,
        "temp_weekend_txn_ratio_90d": 0.28,
        "temp_weekday_txn_ratio_90d": 0.72,
        "temp_morning_activity_ratio_90d": 0.35,
        "temp_afternoon_activity_ratio_90d": 0.45,
        "temp_evening_activity_ratio_90d": 0.20,
        "temp_payday_activity_ratio_90d": 0.38,
        "risk_high_value_txn_ratio_90d": 0.15,
        "risk_txn_volatility_90d": 0.22,
        "risk_reversal_ratio_90d": 0.00,
        "risk_cash_heavy_ratio_90d": 0.12,
        "risk_unusual_channel_flag": False,
        "risk_dormant_indicator": False,
        "rel_customer_status": "Active",
        "rel_accounts_active": 2,
        "rel_has_loan": True,
        "rel_has_savings": True,
        "rel_products_owned": 4,
        "rel_has_card": True,
        "rel_card_count": 2,
        "rel_has_unactivated_card": False,
        "rel_card_expiring_30d": 0,
        "rel_card_types": 2,
        "eng_login_count_7d": 8,
        "eng_login_count_30d": 32,
        "eng_digital_platform_preference": "MOBILE_APP",
        "eng_avg_session_duration_30d": 4.20,
        "prof_age_band": "35-44",
        "prof_primary_branch": "BR001",
        "prof_kyc_tier": "TIER_1",
        "prof_nationality": "ZM",
        "prof_employment_status": "Employed",
        "prof_education_level": "Postgraduate",
        "prof_declared_vs_observed_income_ratio": 1.02,
        "market_segment_code": "85",
        "market_segment": "Premier"
    }

    ai_outputs_c1 = {
        "health_score": 91.2,
        "health_tier": "Thriving",
        "churn_probability": 0.021,  # 2.1%
        "churn_risk_level": "Low",
        "clv_magnitude_zmw": 945000.00,
        "clv_band": "PLATINUM",
        "clv_percentile": 0.94,
        "balance_growth_forecast_pct": 14.8,
        "lifecycle_forecast_30d": "GROWING",
        "value_erosion_flag": 0,
        "next_best_action": "Wealth Portfolio Advisory & High-Yield Fixed Deposit",
        "nba_channel": "RM Call / Private Branch Lounge",
        "nba_predicted_impact": "High (Lift ZMW 45,000)",
        "boz_dormancy_alert": "No Risk (Active 2 days ago)"
    }

    # Customer 2: Mwamba Chilufya (Personal/Mass / At-Risk / High Churn Risk)
    master_c2 = {
        "customer_id": "CUST0009002",
        "account_number": "ZMW-4412-9038",
        "status": "Active",
        "full_name": "Mwamba Chilufya",
        "date_of_birth": "1993-09-28",
        "national_id": "591024/68/1",
        "mobile_number": "+260966890123",
        "next_of_kin_name": "Bwalya Chilufya",
        "next_of_kin_relationship": "Brother",
        "next_of_kin_phone": "+260966112233",
        "gender": "MALE",
        "branch_code": "BR004",
        "customer_since_date": "2021-11-10",
        "kyc_tier": "TIER_2",
        "nationality": "ZM",
        "market_segment_code": "75",
        "market_segment": "Personal",
        "assigned_rm": "Kelvin Mulenga"
    }

    features_c2 = {
        "customer_id": "CUST0009002",
        "as_of_date": "2026-07-27",
        "computed_at": "2026-07-27 10:00:00",
        "days_since_last_txn": 68,
        "days_since_first_txn": 1720,
        "txn_count_30d": 1,
        "txn_count_90d": 8,
        "txn_count_180d": 46,
        "txn_count_365d": 120,
        "avg_days_between_txn": 11.20,
        "distinct_channels_90d": 2,
        "distinct_txn_types_90d": 2,
        "dominant_channel": "ATM",
        "total_amount_90d": 4200.00,
        "avg_amount_90d": 525.00,
        "total_amount_180d": 38000.00,
        "amount_growth_ratio": -0.78,
        "amount_stddev_90d": 310.50,
        "credit_sum_30d": 500.00,
        "debit_sum_30d": 1200.00,
        "credit_to_debit_ratio_90d": 0.42,
        "balance_trend_90d": "FALLING",
        "monthly_income_estimate": 12000.00,
        "has_salary_credit": False,
        "behav_txn_count_7d": 0,
        "behav_active_days_90d": 7,
        "behav_inactive_days_90d": 83,
        "behav_recency_score": 0.22,
        "behav_frequency_score": 0.15,
        "behav_diversity_score": 0.25,
        "behav_activity_consistency": 0.18,
        "fin_total_credit_90d": 4200.00,
        "fin_total_debit_90d": 9800.00,
        "fin_median_txn_amount_90d": 450.00,
        "fin_salary_consistency": 0.20,
        "fin_income_growth": -0.45,
        "chan_mobile_ratio_90d": 0.15,
        "chan_atm_ratio_90d": 0.70,
        "chan_branch_ratio_90d": 0.15,
        "chan_digital_adoption_score": 0.22,
        "chan_channel_entropy": 0.65,
        "customer_tenure_days": 1720,
        "customer_segment": "Personal Banking",
        "age_years": 33,
        "onboarding_channel": "BRANCH",
        "target_lifecycle_stage": "AT_RISK",
        "engagement_score": 24.0,
        "txn_frequency_trend": -0.65,
        "inactivity_streak_days": 68,
        "balance_growth_pct": -52.40,
        "temp_weekend_txn_ratio_90d": 0.50,
        "temp_weekday_txn_ratio_90d": 0.50,
        "temp_morning_activity_ratio_90d": 0.20,
        "temp_afternoon_activity_ratio_90d": 0.50,
        "temp_evening_activity_ratio_90d": 0.30,
        "temp_payday_activity_ratio_90d": 0.10,
        "risk_high_value_txn_ratio_90d": 0.00,
        "risk_txn_volatility_90d": 0.65,
        "risk_reversal_ratio_90d": 0.05,
        "risk_cash_heavy_ratio_90d": 0.75,
        "risk_unusual_channel_flag": False,
        "risk_dormant_indicator": False,
        "rel_customer_status": "Active",
        "rel_accounts_active": 1,
        "rel_has_loan": False,
        "rel_has_savings": False,
        "rel_products_owned": 1,
        "rel_has_card": True,
        "rel_card_count": 1,
        "rel_has_unactivated_card": False,
        "rel_card_expiring_30d": 0,
        "rel_card_types": 1,
        "eng_login_count_7d": 0,
        "eng_login_count_30d": 1,
        "eng_digital_platform_preference": "USSD",
        "eng_avg_session_duration_30d": 0.80,
        "prof_age_band": "25-34",
        "prof_primary_branch": "BR004",
        "prof_kyc_tier": "TIER_2",
        "prof_nationality": "ZM",
        "prof_employment_status": "Self-Employed",
        "prof_education_level": "Secondary",
        "prof_declared_vs_observed_income_ratio": 0.45,
        "market_segment_code": "75",
        "market_segment": "Personal"
    }

    ai_outputs_c2 = {
        "health_score": 29.8,
        "health_tier": "High Risk",
        "churn_probability": 0.784,  # 78.4%
        "churn_risk_level": "High",
        "clv_magnitude_zmw": 14200.00,
        "clv_band": "BRONZE",
        "clv_percentile": 0.22,
        "balance_growth_forecast_pct": -48.2,
        "lifecycle_forecast_30d": "AT_RISK",
        "value_erosion_flag": 1,
        "next_best_action": "Proactive Win-Back Call & Inactivity Fee Waiver",
        "nba_channel": "RM Phone Outreach / SMS Notification",
        "nba_predicted_impact": "Critical (Protect ZMW 12,500)",
        "boz_dormancy_alert": "Watch: Inactive 68 days (Approaching Dormancy threshold)"
    }

    # ----------------------------------------------------
    # SHEET 1: Combined_Customer_Dataset
    # ----------------------------------------------------
    ws1 = wb.active
    ws1.title = "Combined_Customer_Dataset"
    ws1.views.sheetView[0].showGridLines = True

    # Title Block
    ws1.merge_cells("A1:K1")
    title_cell = ws1["A1"]
    title_cell.value = "ABSA DECISION INTELLIGENCE PLATFORM — COMPLETE CUSTOMER DATASET"
    title_cell.font = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
    title_cell.fill = PatternFill(start_color=BURGUNDY, end_color=BURGUNDY, fill_type="solid")
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws1.row_dimensions[1].height = 36

    ws1.merge_cells("A2:K2")
    sub_cell = ws1["A2"]
    sub_cell.value = "Unified View: Personal Identity & Contact Details, Core Banking Attributes, AI Predictions & 85 Feature-Store Columns for 2 Benchmark Customers"
    sub_cell.font = Font(name="Calibri", size=10, italic=True, color="FFFFFF")
    sub_cell.fill = PatternFill(start_color=BURGUNDY_DARK, end_color=BURGUNDY_DARK, fill_type="solid")
    sub_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws1.row_dimensions[2].height = 22

    # Column Category Groups
    combined_columns = [
        # (Header, Group, Type, c1_val, c2_val, num_fmt)
        # 1. Personal & Identity (Frontend Header & Cards)
        ("customer_id", "1. Personal & Identity", "string", master_c1["customer_id"], master_c2["customer_id"], None),
        ("full_name", "1. Personal & Identity", "string", master_c1["full_name"], master_c2["full_name"], None),
        ("national_id", "1. Personal & Identity", "string", master_c1["national_id"], master_c2["national_id"], None),
        ("date_of_birth", "1. Personal & Identity", "date", master_c1["date_of_birth"], master_c2["date_of_birth"], "yyyy-mm-dd"),
        ("age_years", "1. Personal & Identity", "integer", features_c1["age_years"], features_c2["age_years"], "#,##0"),
        ("gender", "1. Personal & Identity", "enum", master_c1["gender"], master_c2["gender"], None),
        ("mobile_number", "1. Personal & Identity", "string", master_c1["mobile_number"], master_c2["mobile_number"], None),
        ("nationality", "1. Personal & Identity", "string", master_c1["nationality"], master_c2["nationality"], None),
        
        # 2. Account & Relationship
        ("account_number", "2. Account & Relationship", "string", master_c1["account_number"], master_c2["account_number"], None),
        ("status", "2. Account & Relationship", "enum", master_c1["status"], master_c2["status"], None),
        ("branch_code", "2. Account & Relationship", "string", master_c1["branch_code"], master_c2["branch_code"], None),
        ("customer_since_date", "2. Account & Relationship", "date", master_c1["customer_since_date"], master_c2["customer_since_date"], "yyyy-mm-dd"),
        ("customer_tenure_days", "2. Account & Relationship", "integer", features_c1["customer_tenure_days"], features_c2["customer_tenure_days"], "#,##0"),
        ("kyc_tier", "2. Account & Relationship", "string", master_c1["kyc_tier"], master_c2["kyc_tier"], None),
        ("market_segment_code", "2. Account & Relationship", "enum", master_c1["market_segment_code"], master_c2["market_segment_code"], None),
        ("market_segment", "2. Account & Relationship", "string", master_c1["market_segment"], master_c2["market_segment"], None),
        ("assigned_rm", "2. Account & Relationship", "string", master_c1["assigned_rm"], master_c2["assigned_rm"], None),
        ("next_of_kin_name", "2. Account & Relationship", "string", master_c1["next_of_kin_name"], master_c2["next_of_kin_name"], None),
        ("next_of_kin_relationship", "2. Account & Relationship", "string", master_c1["next_of_kin_relationship"], master_c2["next_of_kin_relationship"], None),
        ("next_of_kin_phone", "2. Account & Relationship", "string", master_c1["next_of_kin_phone"], master_c2["next_of_kin_phone"], None),

        # 3. AI Model Predictions & Outputs (Displayed on Frontend Gauges & Panels)
        ("health_score", "3. Model Predictions (AI)", "decimal", ai_outputs_c1["health_score"], ai_outputs_c2["health_score"], "0.0"),
        ("health_tier", "3. Model Predictions (AI)", "string", ai_outputs_c1["health_tier"], ai_outputs_c2["health_tier"], None),
        ("churn_probability", "3. Model Predictions (AI)", "decimal", ai_outputs_c1["churn_probability"], ai_outputs_c2["churn_probability"], "0.0%"),
        ("churn_risk_level", "3. Model Predictions (AI)", "string", ai_outputs_c1["churn_risk_level"], ai_outputs_c2["churn_risk_level"], None),
        ("clv_magnitude_zmw", "3. Model Predictions (AI)", "decimal", ai_outputs_c1["clv_magnitude_zmw"], ai_outputs_c2["clv_magnitude_zmw"], "ZMW #,##0.00"),
        ("clv_band", "3. Model Predictions (AI)", "string", ai_outputs_c1["clv_band"], ai_outputs_c2["clv_band"], None),
        ("clv_percentile", "3. Model Predictions (AI)", "decimal", ai_outputs_c1["clv_percentile"], ai_outputs_c2["clv_percentile"], "0.0%"),
        ("balance_growth_forecast_pct", "3. Model Predictions (AI)", "decimal", ai_outputs_c1["balance_growth_forecast_pct"], ai_outputs_c2["balance_growth_forecast_pct"], "0.0%"),
        ("lifecycle_forecast_30d", "3. Model Predictions (AI)", "string", ai_outputs_c1["lifecycle_forecast_30d"], ai_outputs_c2["lifecycle_forecast_30d"], None),
        ("value_erosion_flag", "3. Model Predictions (AI)", "integer", ai_outputs_c1["value_erosion_flag"], ai_outputs_c2["value_erosion_flag"], "#,##0"),
        ("next_best_action", "3. Model Predictions (AI)", "string", ai_outputs_c1["next_best_action"], ai_outputs_c2["next_best_action"], None),
        ("nba_channel", "3. Model Predictions (AI)", "string", ai_outputs_c1["nba_channel"], ai_outputs_c2["nba_channel"], None),
        ("nba_predicted_impact", "3. Model Predictions (AI)", "string", ai_outputs_c1["nba_predicted_impact"], ai_outputs_c2["nba_predicted_impact"], None),
        ("boz_dormancy_alert", "3. Model Predictions (AI)", "string", ai_outputs_c1["boz_dormancy_alert"], ai_outputs_c2["boz_dormancy_alert"], None),

        # 4. Snapshot Metadata
        ("as_of_date", "4. Feature Snapshot Metadata", "date", features_c1["as_of_date"], features_c2["as_of_date"], "yyyy-mm-dd"),
        ("computed_at", "4. Feature Snapshot Metadata", "datetime", features_c1["computed_at"], features_c2["computed_at"], "yyyy-mm-dd hh:mm:ss"),

        # 5. Transaction Cadence Features (Features Store)
        ("days_since_last_txn", "5. Transaction Cadence", "integer", features_c1["days_since_last_txn"], features_c2["days_since_last_txn"], "#,##0"),
        ("days_since_first_txn", "5. Transaction Cadence", "integer", features_c1["days_since_first_txn"], features_c2["days_since_first_txn"], "#,##0"),
        ("txn_count_30d", "5. Transaction Cadence", "integer", features_c1["txn_count_30d"], features_c2["txn_count_30d"], "#,##0"),
        ("txn_count_90d", "5. Transaction Cadence", "integer", features_c1["txn_count_90d"], features_c2["txn_count_90d"], "#,##0"),
        ("txn_count_180d", "5. Transaction Cadence", "integer", features_c1["txn_count_180d"], features_c2["txn_count_180d"], "#,##0"),
        ("txn_count_365d", "5. Transaction Cadence", "integer", features_c1["txn_count_365d"], features_c2["txn_count_365d"], "#,##0"),
        ("avg_days_between_txn", "5. Transaction Cadence", "decimal", features_c1["avg_days_between_txn"], features_c2["avg_days_between_txn"], "0.00"),
        ("distinct_channels_90d", "5. Transaction Cadence", "integer", features_c1["distinct_channels_90d"], features_c2["distinct_channels_90d"], "#,##0"),
        ("distinct_txn_types_90d", "5. Transaction Cadence", "integer", features_c1["distinct_txn_types_90d"], features_c2["distinct_txn_types_90d"], "#,##0"),
        ("dominant_channel", "5. Transaction Cadence", "enum", features_c1["dominant_channel"], features_c2["dominant_channel"], None),

        # 6. Monetary & Balance Features
        ("total_amount_90d", "6. Monetary & Balance", "decimal", features_c1["total_amount_90d"], features_c2["total_amount_90d"], "ZMW #,##0.00"),
        ("avg_amount_90d", "6. Monetary & Balance", "decimal", features_c1["avg_amount_90d"], features_c2["avg_amount_90d"], "ZMW #,##0.00"),
        ("total_amount_180d", "6. Monetary & Balance", "decimal", features_c1["total_amount_180d"], features_c2["total_amount_180d"], "ZMW #,##0.00"),
        ("amount_growth_ratio", "6. Monetary & Balance", "decimal", features_c1["amount_growth_ratio"], features_c2["amount_growth_ratio"], "0.0%"),
        ("amount_stddev_90d", "6. Monetary & Balance", "decimal", features_c1["amount_stddev_90d"], features_c2["amount_stddev_90d"], "#,##0.00"),
        ("credit_sum_30d", "6. Monetary & Balance", "decimal", features_c1["credit_sum_30d"], features_c2["credit_sum_30d"], "ZMW #,##0.00"),
        ("debit_sum_30d", "6. Monetary & Balance", "decimal", features_c1["debit_sum_30d"], features_c2["debit_sum_30d"], "ZMW #,##0.00"),
        ("credit_to_debit_ratio_90d", "6. Monetary & Balance", "decimal", features_c1["credit_to_debit_ratio_90d"], features_c2["credit_to_debit_ratio_90d"], "0.00"),
        ("balance_trend_90d", "6. Monetary & Balance", "enum", features_c1["balance_trend_90d"], features_c2["balance_trend_90d"], None),
        ("balance_growth_pct", "6. Monetary & Balance", "decimal", features_c1["balance_growth_pct"], features_c2["balance_growth_pct"], "0.0%"),
        ("monthly_income_estimate", "6. Monetary & Balance", "decimal", features_c1["monthly_income_estimate"], features_c2["monthly_income_estimate"], "ZMW #,##0.00"),
        ("has_salary_credit", "6. Monetary & Balance", "boolean", features_c1["has_salary_credit"], features_c2["has_salary_credit"], None),

        # 7. Behavioural & Digital Activity
        ("behav_txn_count_7d", "7. Behavioural Activity", "integer", features_c1["behav_txn_count_7d"], features_c2["behav_txn_count_7d"], "#,##0"),
        ("behav_active_days_90d", "7. Behavioural Activity", "integer", features_c1["behav_active_days_90d"], features_c2["behav_active_days_90d"], "#,##0"),
        ("behav_inactive_days_90d", "7. Behavioural Activity", "integer", features_c1["behav_inactive_days_90d"], features_c2["behav_inactive_days_90d"], "#,##0"),
        ("behav_recency_score", "7. Behavioural Activity", "decimal", features_c1["behav_recency_score"], features_c2["behav_recency_score"], "0.00"),
        ("behav_frequency_score", "7. Behavioural Activity", "decimal", features_c1["behav_frequency_score"], features_c2["behav_frequency_score"], "0.00"),
        ("behav_diversity_score", "7. Behavioural Activity", "decimal", features_c1["behav_diversity_score"], features_c2["behav_diversity_score"], "0.00"),
        ("behav_activity_consistency", "7. Behavioural Activity", "decimal", features_c1["behav_activity_consistency"], features_c2["behav_activity_consistency"], "0.00"),
        ("engagement_score", "7. Behavioural Activity", "decimal", features_c1["engagement_score"], features_c2["engagement_score"], "0.0"),
        ("txn_frequency_trend", "7. Behavioural Activity", "decimal", features_c1["txn_frequency_trend"], features_c2["txn_frequency_trend"], "0.00"),
        ("inactivity_streak_days", "7. Behavioural Activity", "integer", features_c1["inactivity_streak_days"], features_c2["inactivity_streak_days"], "#,##0"),
        ("eng_login_count_7d", "7. Behavioural Activity", "integer", features_c1["eng_login_count_7d"], features_c2["eng_login_count_7d"], "#,##0"),
        ("eng_login_count_30d", "7. Behavioural Activity", "integer", features_c1["eng_login_count_30d"], features_c2["eng_login_count_30d"], "#,##0"),
        ("eng_digital_platform_preference", "7. Behavioural Activity", "string", features_c1["eng_digital_platform_preference"], features_c2["eng_digital_platform_preference"], None),
        ("eng_avg_session_duration_30d", "7. Behavioural Activity", "decimal", features_c1["eng_avg_session_duration_30d"], features_c2["eng_avg_session_duration_30d"], "0.00"),

        # 8. Financial Summary & Channel Mix
        ("fin_total_credit_90d", "8. Financial & Channel Mix", "decimal", features_c1["fin_total_credit_90d"], features_c2["fin_total_credit_90d"], "ZMW #,##0.00"),
        ("fin_total_debit_90d", "8. Financial & Channel Mix", "decimal", features_c1["fin_total_debit_90d"], features_c2["fin_total_debit_90d"], "ZMW #,##0.00"),
        ("fin_median_txn_amount_90d", "8. Financial & Channel Mix", "decimal", features_c1["fin_median_txn_amount_90d"], features_c2["fin_median_txn_amount_90d"], "ZMW #,##0.00"),
        ("fin_salary_consistency", "8. Financial & Channel Mix", "decimal", features_c1["fin_salary_consistency"], features_c2["fin_salary_consistency"], "0.00"),
        ("fin_income_growth", "8. Financial & Channel Mix", "decimal", features_c1["fin_income_growth"], features_c2["fin_income_growth"], "0.0%"),
        ("chan_mobile_ratio_90d", "8. Financial & Channel Mix", "decimal", features_c1["chan_mobile_ratio_90d"], features_c2["chan_mobile_ratio_90d"], "0.0%"),
        ("chan_atm_ratio_90d", "8. Financial & Channel Mix", "decimal", features_c1["chan_atm_ratio_90d"], features_c2["chan_atm_ratio_90d"], "0.0%"),
        ("chan_branch_ratio_90d", "8. Financial & Channel Mix", "decimal", features_c1["chan_branch_ratio_90d"], features_c2["chan_branch_ratio_90d"], "0.0%"),
        ("chan_digital_adoption_score", "8. Financial & Channel Mix", "decimal", features_c1["chan_digital_adoption_score"], features_c2["chan_digital_adoption_score"], "0.00"),
        ("chan_channel_entropy", "8. Financial & Channel Mix", "decimal", features_c1["chan_channel_entropy"], features_c2["chan_channel_entropy"], "0.00"),

        # 9. Temporal Patterns & Risk Flags
        ("temp_weekend_txn_ratio_90d", "9. Temporal & Risk Indicators", "decimal", features_c1["temp_weekend_txn_ratio_90d"], features_c2["temp_weekend_txn_ratio_90d"], "0.0%"),
        ("temp_weekday_txn_ratio_90d", "9. Temporal & Risk Indicators", "decimal", features_c1["temp_weekday_txn_ratio_90d"], features_c2["temp_weekday_txn_ratio_90d"], "0.0%"),
        ("temp_morning_activity_ratio_90d", "9. Temporal & Risk Indicators", "decimal", features_c1["temp_morning_activity_ratio_90d"], features_c2["temp_morning_activity_ratio_90d"], "0.0%"),
        ("temp_afternoon_activity_ratio_90d", "9. Temporal & Risk Indicators", "decimal", features_c1["temp_afternoon_activity_ratio_90d"], features_c2["temp_afternoon_activity_ratio_90d"], "0.0%"),
        ("temp_evening_activity_ratio_90d", "9. Temporal & Risk Indicators", "decimal", features_c1["temp_evening_activity_ratio_90d"], features_c2["temp_evening_activity_ratio_90d"], "0.0%"),
        ("temp_payday_activity_ratio_90d", "9. Temporal & Risk Indicators", "decimal", features_c1["temp_payday_activity_ratio_90d"], features_c2["temp_payday_activity_ratio_90d"], "0.0%"),
        ("risk_high_value_txn_ratio_90d", "9. Temporal & Risk Indicators", "decimal", features_c1["risk_high_value_txn_ratio_90d"], features_c2["risk_high_value_txn_ratio_90d"], "0.0%"),
        ("risk_txn_volatility_90d", "9. Temporal & Risk Indicators", "decimal", features_c1["risk_txn_volatility_90d"], features_c2["risk_txn_volatility_90d"], "0.00"),
        ("risk_reversal_ratio_90d", "9. Temporal & Risk Indicators", "decimal", features_c1["risk_reversal_ratio_90d"], features_c2["risk_reversal_ratio_90d"], "0.0%"),
        ("risk_cash_heavy_ratio_90d", "9. Temporal & Risk Indicators", "decimal", features_c1["risk_cash_heavy_ratio_90d"], features_c2["risk_cash_heavy_ratio_90d"], "0.0%"),
        ("risk_unusual_channel_flag", "9. Temporal & Risk Indicators", "boolean", features_c1["risk_unusual_channel_flag"], features_c2["risk_unusual_channel_flag"], None),
        ("risk_dormant_indicator", "9. Temporal & Risk Indicators", "boolean", features_c1["risk_dormant_indicator"], features_c2["risk_dormant_indicator"], None),

        # 10. Relationship & Product Holdings
        ("rel_customer_status", "10. Relationship & Products", "enum", features_c1["rel_customer_status"], features_c2["rel_customer_status"], None),
        ("rel_accounts_active", "10. Relationship & Products", "integer", features_c1["rel_accounts_active"], features_c2["rel_accounts_active"], "#,##0"),
        ("rel_has_loan", "10. Relationship & Products", "boolean", features_c1["rel_has_loan"], features_c2["rel_has_loan"], None),
        ("rel_has_savings", "10. Relationship & Products", "boolean", features_c1["rel_has_savings"], features_c2["rel_has_savings"], None),
        ("rel_products_owned", "10. Relationship & Products", "integer", features_c1["rel_products_owned"], features_c2["rel_products_owned"], "#,##0"),
        ("rel_has_card", "10. Relationship & Products", "boolean", features_c1["rel_has_card"], features_c2["rel_has_card"], None),
        ("rel_card_count", "10. Relationship & Products", "integer", features_c1["rel_card_count"], features_c2["rel_card_count"], "#,##0"),
        ("rel_has_unactivated_card", "10. Relationship & Products", "boolean", features_c1["rel_has_unactivated_card"], features_c2["rel_has_unactivated_card"], None),
        ("rel_card_expiring_30d", "10. Relationship & Products", "integer", features_c1["rel_card_expiring_30d"], features_c2["rel_card_expiring_30d"], "#,##0"),
        ("rel_card_types", "10. Relationship & Products", "integer", features_c1["rel_card_types"], features_c2["rel_card_types"], "#,##0"),

        # 11. Profile & Demographics
        ("prof_age_band", "11. Profile Demographics", "string", features_c1["prof_age_band"], features_c2["prof_age_band"], None),
        ("prof_primary_branch", "11. Profile Demographics", "string", features_c1["prof_primary_branch"], features_c2["prof_primary_branch"], None),
        ("prof_kyc_tier", "11. Profile Demographics", "string", features_c1["prof_kyc_tier"], features_c2["prof_kyc_tier"], None),
        ("prof_nationality", "11. Profile Demographics", "string", features_c1["prof_nationality"], features_c2["prof_nationality"], None),
        ("prof_employment_status", "11. Profile Demographics", "string", features_c1["prof_employment_status"], features_c2["prof_employment_status"], None),
        ("prof_education_level", "11. Profile Demographics", "string", features_c1["prof_education_level"], features_c2["prof_education_level"], None),
        ("prof_declared_vs_observed_income_ratio", "11. Profile Demographics", "decimal", features_c1["prof_declared_vs_observed_income_ratio"], features_c2["prof_declared_vs_observed_income_ratio"], "0.00"),
        ("customer_segment", "11. Profile Demographics", "string", features_c1["customer_segment"], features_c2["customer_segment"], None),
        ("onboarding_channel", "11. Profile Demographics", "string", features_c1["onboarding_channel"], features_c2["onboarding_channel"], None),
        ("target_lifecycle_stage", "11. Profile Demographics", "enum", features_c1["target_lifecycle_stage"], features_c2["target_lifecycle_stage"], None),
    ]

    # Write Headers for Sheet 1
    # We will write:
    # Row 4: Group Header
    # Row 5: Column Name Header
    ws1.row_dimensions[4].height = 20
    ws1.row_dimensions[5].height = 28
    
    current_group = None
    group_start_col = 1

    for col_idx, (col_name, group, dtype, c1_val, c2_val, num_fmt) in enumerate(combined_columns, start=1):
        # Group cell
        g_cell = ws1.cell(row=4, column=col_idx)
        g_cell.value = group
        g_cell.font = Font(name="Calibri", size=9, bold=True, color="475569")
        g_cell.fill = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")
        g_cell.alignment = Alignment(horizontal="center", vertical="center")

        # Column Header cell
        c_cell = ws1.cell(row=5, column=col_idx)
        c_cell.value = col_name
        c_cell.font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        
        # Color headers based on section
        if "Model Predictions" in group:
            c_cell.fill = PatternFill(start_color="047857", end_color="047857", fill_type="solid") # Emerald
        elif "Personal & Identity" in group:
            c_cell.fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid") # Navy Blue
        elif "Account & Relationship" in group:
            c_cell.fill = PatternFill(start_color="4338CA", end_color="4338CA", fill_type="solid") # Indigo
        else:
            c_cell.fill = PatternFill(start_color="8A002E", end_color="8A002E", fill_type="solid") # Absa Burgundy
            
        c_cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c_cell.border = get_border()

        # Row 6: Customer 1 Data
        r6 = ws1.cell(row=6, column=col_idx)
        r6.value = c1_val
        r6.font = Font(name="Calibri", size=10)
        r6.alignment = Alignment(horizontal="center" if dtype in ("date", "enum", "boolean") else "left")
        r6.border = get_border()
        r6.fill = PatternFill(start_color="F0FDF4", end_color="F0FDF4", fill_type="solid") # Subtle Green tint
        if num_fmt:
            r6.number_format = num_fmt

        # Row 7: Customer 2 Data
        r7 = ws1.cell(row=7, column=col_idx)
        r7.value = c2_val
        r7.font = Font(name="Calibri", size=10)
        r7.alignment = Alignment(horizontal="center" if dtype in ("date", "enum", "boolean") else "left")
        r7.border = get_border()
        r7.fill = PatternFill(start_color="FFF1F2", end_color="FFF1F2", fill_type="solid") # Subtle Red tint
        if num_fmt:
            r7.number_format = num_fmt

        # Column width adjustment
        val_lens = [len(str(col_name)), len(str(c1_val)), len(str(c2_val))]
        ws1.column_dimensions[get_column_letter(col_idx)].width = max(max(val_lens) + 4, 14)

    ws1.row_dimensions[6].height = 24
    ws1.row_dimensions[7].height = 24

    # ----------------------------------------------------
    # SHEET 2: Customer_Master (public.customers_clean)
    # ----------------------------------------------------
    ws2 = wb.create_sheet(title="Customer_Master")
    ws2.views.sheetView[0].showGridLines = True

    # Title
    ws2.merge_cells("A1:P1")
    t2 = ws2["A1"]
    t2.value = "CUSTOMER MASTER IDENTITY DATASET (Target Table: public.customers_clean)"
    t2.font = Font(name="Calibri", size=12, bold=True, color="FFFFFF")
    t2.fill = PatternFill(start_color=BURGUNDY, end_color=BURGUNDY, fill_type="solid")
    t2.alignment = Alignment(horizontal="center", vertical="center")
    ws2.row_dimensions[1].height = 30

    master_fields_ordered = [
        ("customer_id", "Customer ID", "string", "CUST0000001", master_c1["customer_id"], master_c2["customer_id"], None),
        ("account_number", "Account Number", "string", "ZMK-8820-192", master_c1["account_number"], master_c2["account_number"], None),
        ("status", "Account Status", "enum", "Active", master_c1["status"], master_c2["status"], None),
        ("full_name", "Full Name", "string", "Jane Curtis", master_c1["full_name"], master_c2["full_name"], None),
        ("date_of_birth", "Date of Birth", "date", "1985-04-12", master_c1["date_of_birth"], master_c2["date_of_birth"], "yyyy-mm-dd"),
        ("national_id", "ID Number (NRC)", "string", "994022/11/1", master_c1["national_id"], master_c2["national_id"], None),
        ("mobile_number", "Mobile Number", "string", "+260971234567", master_c1["mobile_number"], master_c2["mobile_number"], None),
        ("next_of_kin_name", "Next of Kin Name", "string", "Jane Curtis", master_c1["next_of_kin_name"], master_c2["next_of_kin_name"], None),
        ("next_of_kin_relationship", "Next of Kin Relationship", "string", "Spouse", master_c1["next_of_kin_relationship"], master_c2["next_of_kin_relationship"], None),
        ("next_of_kin_phone", "Next of Kin Phone", "string", "+260971234568", master_c1["next_of_kin_phone"], master_c2["next_of_kin_phone"], None),
        ("gender", "Gender", "enum", "FEMALE", master_c1["gender"], master_c2["gender"], None),
        ("branch_code", "Branch Code", "string", "BR001", master_c1["branch_code"], master_c2["branch_code"], None),
        ("customer_since_date", "Customer Since", "date", "2016-03-20", master_c1["customer_since_date"], master_c2["customer_since_date"], "yyyy-mm-dd"),
        ("kyc_tier", "KYC Tier", "string", "TIER_1", master_c1["kyc_tier"], master_c2["kyc_tier"], None),
        ("nationality", "Nationality", "string", "ZM", master_c1["nationality"], master_c2["nationality"], None),
        ("market_segment_code", "Market Segment Code", "enum", "60", master_c1["market_segment_code"], master_c2["market_segment_code"], None),
    ]

    # Row 3 Header
    ws2.row_dimensions[3].height = 26
    for col_idx, (f_name, label, dtype, ex, v1, v2, nfmt) in enumerate(master_fields_ordered, start=1):
        cell = ws2.cell(row=3, column=col_idx)
        cell.value = f_name
        cell.font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color=SLATE_HEADER, end_color=SLATE_HEADER, fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = get_thick_bottom_border()

        # Customer 1
        r4 = ws2.cell(row=4, column=col_idx)
        r4.value = v1
        r4.font = Font(name="Calibri", size=10)
        r4.alignment = Alignment(horizontal="center" if dtype in ("date", "enum") else "left")
        r4.border = get_border()
        if nfmt: r4.number_format = nfmt

        # Customer 2
        r5 = ws2.cell(row=5, column=col_idx)
        r5.value = v2
        r5.font = Font(name="Calibri", size=10)
        r5.alignment = Alignment(horizontal="center" if dtype in ("date", "enum") else "left")
        r5.border = get_border()
        if nfmt: r5.number_format = nfmt

        ws2.column_dimensions[get_column_letter(col_idx)].width = max(len(f_name) + 4, len(str(v1)) + 4, 16)

    ws2.row_dimensions[4].height = 22
    ws2.row_dimensions[5].height = 22

    # ----------------------------------------------------
    # SHEET 3: Customer_Features (public.customer_features)
    # ----------------------------------------------------
    ws3 = wb.create_sheet(title="Customer_Features")
    ws3.views.sheetView[0].showGridLines = True

    # Title
    ws3.merge_cells("A1:K1")
    t3 = ws3["A1"]
    t3.value = "CUSTOMER FEATURE STORE SNAPSHOT (Target Table: public.customer_features - 85 Ingest Columns)"
    t3.font = Font(name="Calibri", size=12, bold=True, color="FFFFFF")
    t3.fill = PatternFill(start_color=BURGUNDY, end_color=BURGUNDY, fill_type="solid")
    t3.alignment = Alignment(horizontal="center", vertical="center")
    ws3.row_dimensions[1].height = 30

    # Get exact 85 feature keys from features_c1
    feature_keys = list(features_c1.keys())

    ws3.row_dimensions[3].height = 26
    for col_idx, f_name in enumerate(feature_keys, start=1):
        cell = ws3.cell(row=3, column=col_idx)
        cell.value = f_name
        cell.font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color=SLATE_HEADER, end_color=SLATE_HEADER, fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = get_thick_bottom_border()

        v1 = features_c1[f_name]
        v2 = features_c2[f_name]

        # Customer 1
        r4 = ws3.cell(row=4, column=col_idx)
        r4.value = v1
        r4.font = Font(name="Calibri", size=10)
        r4.border = get_border()

        # Customer 2
        r5 = ws3.cell(row=5, column=col_idx)
        r5.value = v2
        r5.font = Font(name="Calibri", size=10)
        r5.border = get_border()

        # Formatting
        if isinstance(v1, float):
            if "pct" in f_name or "ratio" in f_name:
                r4.number_format = "0.00"
                r5.number_format = "0.00"
            elif "amount" in f_name or "sum" in f_name or "credit" in f_name or "debit" in f_name or "income" in f_name:
                r4.number_format = "#,##0.00"
                r5.number_format = "#,##0.00"
            else:
                r4.number_format = "0.00"
                r5.number_format = "0.00"
        elif isinstance(v1, int) and not isinstance(v1, bool):
            r4.number_format = "#,##0"
            r5.number_format = "#,##0"

        ws3.column_dimensions[get_column_letter(col_idx)].width = max(len(f_name) + 4, len(str(v1)) + 4, 15)

    ws3.row_dimensions[4].height = 22
    ws3.row_dimensions[5].height = 22

    # ----------------------------------------------------
    # SHEET 4: Data_Dictionary
    # ----------------------------------------------------
    ws4 = wb.create_sheet(title="Data_Dictionary")
    ws4.views.sheetView[0].showGridLines = True

    # Title
    ws4.merge_cells("A1:G1")
    t4 = ws4["A1"]
    t4.value = "FIELD CATALOGUE & SYSTEM MAPPING DICTIONARY"
    t4.font = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
    t4.fill = PatternFill(start_color=BURGUNDY, end_color=BURGUNDY, fill_type="solid")
    t4.alignment = Alignment(horizontal="center", vertical="center")
    ws4.row_dimensions[1].height = 34

    dict_headers = [
        "Field Name",
        "Display Label",
        "Category",
        "Data Type",
        "Target Database Table",
        "Consuming ML Model / Engine",
        "Frontend Display Location & Purpose"
    ]
    ws4.row_dimensions[3].height = 26
    for col_idx, h in enumerate(dict_headers, start=1):
        cell = ws4.cell(row=3, column=col_idx)
        cell.value = h
        cell.font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color=SLATE_HEADER, end_color=SLATE_HEADER, fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = get_thick_bottom_border()

    # Dictionary entries
    dict_rows = [
        # Personal & Master
        ("customer_id", "Customer ID", "Master & Identity", "string", "public.customers_clean / customer_features", "All Models & System Entities", "Header, URLs, Breadcrumb, Table primary key"),
        ("account_number", "Account Number", "Master & Identity", "string", "public.customers_clean", "State Engine / Core Banking Link", "Headline Fact card, Profile Header, Core Banking link"),
        ("status", "Account Status", "Master & Identity", "enum", "public.customers_clean", "Churn Label Engine (target)", "Customer State Pill, Table badge (Active, Dormant, Closed)"),
        ("full_name", "Full Name", "Master & Identity", "string", "public.customers_clean", "Reporting & UI", "Profile display name, initials avatar, CRM log"),
        ("date_of_birth", "Date of Birth", "Master & Identity", "date", "public.customers_clean", "Demographic Engine", "Profile age subtitle ('41 years old')"),
        ("national_id", "ID Number (NRC)", "Master & Identity", "string", "public.customers_clean", "Compliance & Audit", "Headline Fact card ('Verified identifier')"),
        ("mobile_number", "Mobile Number", "Master & Identity", "string", "public.customers_clean", "NBA Outreach & CRM", "Detail field grid, Log Outreach modal, SMS trigger"),
        ("gender", "Gender", "Master & Identity", "enum", "public.customers_clean", "Demographic Analysis", "Detail field grid (MALE, FEMALE, UNKNOWN)"),
        ("branch_code", "Branch Code", "Master & Identity", "string", "public.customers_clean", "Branch Manager Portfolio Filter", "Detail field grid, Branch comparison rollup"),
        ("customer_since_date", "Customer Since", "Master & Identity", "date", "public.customers_clean", "Tenure derivation", "Headline Fact card ('Since 2018-05-14')"),
        ("kyc_tier", "KYC Tier", "Master & Identity", "string", "public.customers_clean", "Compliance & Risk", "Detail field grid (TIER_1 … TIER_4)"),
        ("nationality", "Nationality", "Master & Identity", "string", "public.customers_clean", "Risk Profiling", "Detail field grid (e.g. 'ZM')"),
        ("market_segment_code", "Market Segment Code", "Master & Identity", "enum", "public.customers_clean / customer_features", "XGBoost Churn, CLV, NBA", "Segment badge, Private client tier resolution"),
        ("next_of_kin_name", "Next of Kin Name", "Master & Identity", "string", "public.customers_clean", "CRM Engagement", "Next of Kin modal & tab on Customer Profile"),
        ("next_of_kin_relationship", "Next of Kin Relationship", "Master & Identity", "string", "public.customers_clean", "CRM Engagement", "Next of Kin tab (Spouse, Brother, etc.)"),
        ("next_of_kin_phone", "Next of Kin Phone", "Master & Identity", "string", "public.customers_clean", "CRM Engagement", "Next of Kin direct contact phone number"),
        
        # AI Predictions
        ("health_score", "AI Health Score", "AI Outputs", "decimal (0-100)", "public.customer_states", "Health Fusion Engine (Weighted)", "Circular Ring Gauge (Thriving / Healthy / Watch / Critical)"),
        ("churn_probability", "Churn Probability", "AI Outputs", "decimal (0-1)", "prediction-service / customer_states", "XGBoost Churn Model (churn_v1)", "Predictive Insights card, Churn % pill (Red/Amber/Green)"),
        ("clv_magnitude_zmw", "CLV Magnitude (ZMW)", "AI Outputs", "decimal", "decision-intelligence / clv-summary", "LightGBM CLV Model", "CLV Headline card, Customer Value Intelligence band"),
        ("clv_percentile", "CLV Percentile", "AI Outputs", "decimal (0-1)", "prediction-service", "Percentile Ranking Engine", "CLV Percentile bar on Customer Profile ('94th')"),
        ("balance_growth_forecast_pct", "Predicted Balance Growth %", "AI Outputs", "decimal", "prediction-service", "LightGBM Balance Growth Model", "AUM Balance Forecast weekly scenario engine"),
        ("lifecycle_forecast_30d", "Lifecycle 30d Stage Forecast", "AI Outputs", "enum", "prediction-service", "Multi-horizon LightGBM Classifier", "Markov Lifecycle Overlay, Journey Evolution timeline"),
        ("next_best_action", "Next Best Action (NBA)", "AI Outputs", "string", "decision-intelligence / NBA Engine", "Propensity + Rules Engine + LLM", "AI Next Best Action banner with 1-click [Log Action]"),
        ("boz_dormancy_alert", "BOZ Dormancy Rule Indicator", "AI Outputs", "string", "Frontend Rule / Compliance", "Dormancy Compliance Tracker", "Urgent Amber/Red BOZ Banner when days_since_last_txn > 365"),

        # Feature Store Key Attributes
        ("days_since_last_txn", "Days Since Last Txn", "Feature Cadence", "integer", "public.customer_features", "CLV, Churn Leakage Guard, BOZ Alert", "Last Activity ('2 days ago'), BOZ Transfer countdown"),
        ("txn_count_30d", "Txn Count (30d)", "Feature Cadence", "integer", "public.customer_features", "XGBoost Churn (Top #1 importance: 0.4047)", "Activity velocity badge, Risk Drivers"),
        ("total_amount_90d", "Total Amount (90d)", "Feature Monetary", "decimal", "public.customer_features", "LightGBM CLV, Value Erosion Classifier", "Monetary Value indicators, Financial summary"),
        ("amount_growth_ratio", "Amount Growth Ratio", "Feature Monetary", "decimal", "public.customer_features", "XGBoost Churn (Top #4 importance: 0.0363)", "Transaction Value Trend driver in Risk panel"),
        ("balance_trend_90d", "Balance Trend (90d)", "Feature Monetary", "enum", "public.customer_features", "XGBoost Churn, State Engine", "Trend indicator (RISING / STABLE / FALLING)"),
        ("behav_active_days_90d", "Active Days (90d)", "Feature Behavioural", "integer", "public.customer_features", "XGBoost Churn (Top #3 importance: 0.2440)", "Behavioural score subcomponent"),
        ("behav_frequency_score", "Frequency Score", "Feature Behavioural", "decimal", "public.customer_features", "XGBoost Churn (Top #2 importance: 0.3076)", "Behavioural Score gauge on profile"),
        ("engagement_score", "Engagement Score", "Feature Behavioural", "decimal (0-100)", "public.customer_features", "Health Score Fusion (Weight: 30%)", "Behavioural Score card on Profile (0-100)"),
        ("dominant_channel", "Dominant Channel", "Feature Channel", "enum", "public.customer_features", "XGBoost Churn, NBA Channel Selector", "Channel preference icon (MOBILE_APP, ATM, USSD, etc.)"),
        ("chan_digital_adoption_score", "Digital Adoption Score", "Feature Channel", "decimal (0-1)", "public.customer_features", "XGBoost Churn, Digital Migration NBA", "Digital engagement metric"),
        ("rel_products_owned", "Products Owned Count", "Feature Relationship", "integer", "public.customer_features", "Cross-sell NBA, Portfolio Depth", "Product holding badges (Cards, Loans, Savings)"),
        ("rel_has_card", "Has Debit/Credit Card", "Feature Relationship", "boolean", "public.customer_features", "Card cross-sell NBA engine", "Product holdings list"),
        ("rel_has_loan", "Has Active Loan", "Feature Relationship", "boolean", "public.customer_features", "Lending retention engine", "Product holdings list"),
        ("rel_has_savings", "Has Savings Account", "Feature Relationship", "boolean", "public.customer_features", "Deposit growth engine", "Product holdings list"),
    ]

    for row_idx, r in enumerate(dict_rows, start=4):
        ws4.row_dimensions[row_idx].height = 20
        for col_idx, val in enumerate(r, start=1):
            c = ws4.cell(row=row_idx, column=col_idx)
            c.value = val
            c.font = Font(name="Calibri", size=9)
            c.border = get_border()
            if col_idx == 1:
                c.font = Font(name="Calibri", size=9, bold=True, color="1E293B")
                c.fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
            elif col_idx == 6:
                c.font = Font(name="Calibri", size=9, bold=True, color="8A002E")

    ws4.column_dimensions["A"].width = 28
    ws4.column_dimensions["B"].width = 28
    ws4.column_dimensions["C"].width = 22
    ws4.column_dimensions["D"].width = 16
    ws4.column_dimensions["E"].width = 32
    ws4.column_dimensions["F"].width = 36
    ws4.column_dimensions["G"].width = 45

    # Save file
    output_path = r"c:\Users\ADMIN\Desktop\uniplexity-ai\ABSA\absa_customer_dataset_prediction_ready.xlsx"
    wb.save(output_path)
    print(f"Successfully created: {output_path}")

if __name__ == "__main__":
    create_dataset()
