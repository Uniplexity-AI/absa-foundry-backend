
import pandas as pd
import numpy as np
df = pd.DataFrame({'A': [1.0, np.nan]})
df = df.where(pd.notnull(df), None)
print(df['A'].tolist())

