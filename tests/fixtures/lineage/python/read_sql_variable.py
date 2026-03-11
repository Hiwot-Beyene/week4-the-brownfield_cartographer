import pandas as pd
df = pd.read_sql("SELECT 1", conn)
path_var = "some/table.csv"
df2 = pd.read_csv(path_var)
