# Complex dynamic query construction: format(), %, concatenation, text().
# Lineage analyzer only resolves literal strings; these should not produce table edges.
import pandas as pd
from sqlalchemy import text

table_name = "users"
df1 = pd.read_sql("SELECT * FROM {}".format(table_name), conn)
df2 = pd.read_sql("SELECT * FROM %s" % (table_name,), conn)
df3 = pd.read_sql("SELECT * FROM " + table_name, conn)

schema = "public"
query = "SELECT * FROM " + schema + ".events"
result = conn.execute(text(query))
