This repo now includes an AI Data Management editing layer (MVP) with endpoints:

- POST /data/insert
- POST /data/update
- POST /data/delete (preview when confirm=false)
- POST /data/schema (add/remove/rename via Groq)
- POST /data/clean (trim/uppercase/fillNull/removeNullRows/removeDuplicates)
- POST /data/transform (MVP: findReplace + bulkTransform)
- POST /data/undo (undo last snapshot)

SQLite editing is implemented per-session via backend/utils/active_dataset_store.py.
Undo is implemented via full table snapshot tables in the active dataset DB.

Future: extend transformation_service for calculated columns + filter & save results.
