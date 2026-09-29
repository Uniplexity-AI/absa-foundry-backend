
import pandas as pd
df = pd.read_parquet(r'c:\Users\ADMIN\Desktop\uniplexity-ai\ABSA\absa-foundry-backend\customer-lifecycle-ai\banking_ml_python\output\clv\training\clv_training_202607.parquet')
for col in df.columns:
    if df[col].dtype in ['int64', 'float64']:
        max_val = df[col].max()
        if max_val > 2147483647:
            print(f'{col} has max value {max_val} which is > int32 max')

