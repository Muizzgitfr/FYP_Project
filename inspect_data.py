import pandas as pd
import os

path = "/Users/mac/Downloads/courses and students/"
files = os.listdir(path)

for file in files:
    if file.endswith(".xlsx"):
        print(f"\n📄 File: {file}")
        try:
            df = pd.read_excel(os.path.join(path, file))
            print(f"   Columns: {df.columns.tolist()}")
            print(f"   First 2 rows:\n{df.head(2)}")
        except Exception as e:
            print(f"   Error: {e}")
