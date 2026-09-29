
import pandas as pd
import numpy as np
df = pd.read_parquet(r'c:\Users\ADMIN\Desktop\uniplexity-ai\ABSA\absa-foundry-backend\customer-lifecycle-ai\banking_ml_python\output\clv\training\clv_training_202607.parquet')
print('NaN counts:')
print(df.isna().sum()[df.isna().sum() > 0])

