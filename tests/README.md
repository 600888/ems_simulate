# Test suite layout

The automated Python test suite follows the application boundaries:

- `protocols/`: protocol behavior and interoperability tests.
- `services/`: domain, persistence, configuration, and runtime service tests.
- `web/`: API and HTTP presentation-layer tests.
- `manual/`: tests requiring live services, network peers, or hardware.
- `diagnostics/`: one-off troubleshooting and reproduction scripts.
- `legacy/`: retained historical tests for components no longer present.

`pytest` collects only `test_*.py` files from the automated areas. Manual,
diagnostic, and legacy directories are intentionally excluded from normal runs.
Run the default suite from the repository root with `python -m pytest`.

IEC 61850 tests are further grouped by MMS, reports, GOOSE, file service,
model/SCL, datasets, and discovery. Add new tests to the narrowest applicable
directory; cross-protocol behavior belongs in `protocols/common`.
