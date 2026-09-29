import re

with open("C:/Users/ADMIN/Desktop/uniplexity-ai/ABSA/absa-foundry-backend/customer-lifecycle-ai/run_etl.py", "r", encoding="utf-8") as f:
    content = f.read()

# Add mode to run_etl_pipeline definition
content = content.replace(
    "    triggered_by: str = \"cli\",\n) -> dict:",
    "    triggered_by: str = \"cli\",\n    mode: str = \"training\",\n) -> dict:"
)

# In Phase 3, implement scoring mode drop
transform_phase = """    # ------------------------------------------------------------------
    # PHASE 3: TRANSFORM
    # ------------------------------------------------------------------"""
scoring_logic = """    # ------------------------------------------------------------------
    # PHASE 3: TRANSFORM
    # ------------------------------------------------------------------
    logger.info("--- Phase 3/4: TRANSFORM ---")
    
    if mode == "scoring":
        logger.info("  SCORING MODE: Dropping forward-looking label columns")
        target_cols = [c for c in valid_df.columns if c.startswith("target_")]
        if target_cols:
            valid_df = valid_df.drop(columns=target_cols)
            # also remove them from target_data_columns so they are not included in SQL INSERT
            config.target_data_columns = [c for c in config.target_data_columns if not c.startswith("target_")]
"""
content = content.replace(transform_phase + '\n    logger.info("--- Phase 3/4: TRANSFORM ---")', scoring_logic)

# In main(), add --mode argument
argparse_block = """    parser.add_argument("--force", action="store_true", help="Re-process even if source was already loaded")"""
argparse_block_new = argparse_block + """\n    parser.add_argument("--mode", choices=["training", "scoring"], default="training", help="Execution mode (training keeps labels, scoring drops them)")"""
content = content.replace(argparse_block, argparse_block_new)

# In main(), pass mode to run_etl_pipeline
run_pipeline_call = """        extraction_spec=args.extraction_spec,
        dry_run=args.dry_run,
        force=args.force,
    ))"""
run_pipeline_call_new = """        extraction_spec=args.extraction_spec,
        dry_run=args.dry_run,
        force=args.force,
        mode=args.mode,
    ))"""
content = content.replace(run_pipeline_call, run_pipeline_call_new)

with open("C:/Users/ADMIN/Desktop/uniplexity-ai/ABSA/absa-foundry-backend/customer-lifecycle-ai/run_etl.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Patched successfully")
