
import numpy as np
import pandas as pd
df = pd.read_parquet(r'c:\Users\ADMIN\Desktop\uniplexity-ai\ABSA\absa-foundry-backend\customer-lifecycle-ai\banking_ml_python\output\clv\training\clv_training_202607.parquet')
df = df.replace({np.nan: None})
for col in df.columns:
    for v in df[col]:
        if isinstance(v, float) and (pd.isna(v) or np.isinf(v)):
            print(f'Found {v} in {col}')

