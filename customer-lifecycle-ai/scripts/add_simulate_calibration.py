import re

file_path = r"c:\Users\ADMIN\Desktop\uniplexity-ai\ABSA\absa-foundry-backend\customer-lifecycle-ai\services\model-management-service\app\api\routes.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

new_endpoint = """
@router.post("/simulate-calibration")
def simulate_calibration(req: dict, db: Session = Depends(get_db)):
    threshold = req.get("threshold", 0.5)
    champ = db.scalars(select(ModelRegistry).filter_by(status="CHAMPION", is_deleted=False).order_by(ModelRegistry.created_at.desc())).first()
    
    # Use real base metrics if available, else fallback to realistic baseline
    base_tp, base_fp, base_tn, base_fn = 150, 50, 800, 50
    if champ and champ.classification_metrics and "confusion_matrix" in champ.classification_metrics:
        cm = champ.classification_metrics["confusion_matrix"]
        base_tn, base_fp = cm[0]
        base_fn, base_tp = cm[1]
        
    shift = threshold - 0.5
    tp = max(0, int(base_tp * (1 - shift * 1.5)))
    fp = max(0, int(base_fp * (1 - shift * 2.0)))
    tn = max(0, int(base_tn * (1 + shift * 0.5)))
    fn = max(0, int(base_fn * (1 + shift * 1.5)))
    
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn}

@router.post("/calibration", response_model=CalibrationProposalResponse)
"""

content = content.replace("@router.post(\"/calibration\", response_model=CalibrationProposalResponse)", new_endpoint)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
