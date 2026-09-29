
import pandas as pd
import numpy as np
df = pd.DataFrame({'A': [1.0, np.nan]})
df = df.replace({np.nan: None})
print(df['A'].tolist())

