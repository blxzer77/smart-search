# npm test lanes

## Full gate (`npm test`)

Runs editable install when needed, then pytest, wrapper repair, help/UTF-8 probes, and `npm pack --dry-run`.

Editable reinstall is skipped automatically when `pytest`, `pytest_asyncio`, and `smart_search` already import from `.smart-search-python`.

## Fast lane (`npm run test:fast`)

Sets `SMART_SEARCH_SKIP_EDITABLE_REINSTALL=1` and assumes the isolated runtime already has `.[dev]` installed (CI installs extras once before `npm test`).

Force a fresh editable install with:

```bash
SMART_SEARCH_FORCE_EDITABLE_REINSTALL=1 npm test
```

On Windows PowerShell:

```powershell
$env:SMART_SEARCH_FORCE_EDITABLE_REINSTALL='1'; npm test
```
