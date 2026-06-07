Backend design note for /data/edit (not yet implemented):

- POST /data/edit {question}
- Uses Groq to classify and produce an operation routing + structured call.
- Execute using existing /data/insert,/data/update,/data/delete,/data/schema,/data/clean,/data/transform,/data/undo services.
- Returns message + updated result preview (columns/rows) so frontend shows success + refreshed table.

Will likely:
1) Generate schema with get_active_schema
2) Ask LLM: determine operation_type among [insert, update, delete, schema_add, schema_remove, schema_rename, find_replace, remove_duplicates, clean, calculated_column, transform, undo]
3) Based on operation_type, call corresponding service(s) for execution.
4) Finally query first 10 rows from active dataset and return for UI refresh.

