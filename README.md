# SII-v4 FREE-ONLY

Autonomous Stock Intelligence Engine for Indian listed equities. No paid data provider, no manual stock list, no APEX dependency.

## Workflows
- SII bootstrap data layer
- SII historical falsification
- SII daily free refresh
- SII weekly blind scan

## Data contract
- NSE/BSE official public sources
- TejHQ Indian Markets public dataset on Hugging Face for free historical market data
- PIT availability timestamps; unknown data remains unknown

## Validation
The historical workflow measures outcome-only price validation when PIT financial coverage is unavailable. The production gate remains FALSE until required universe, market, fundamental, evidence and PIT coverage thresholds are actually measured.

## First run
Run **Actions → SII bootstrap data layer → Run workflow**. Inspect the artifact. Historical validation should only be run after the required PIT financial layer is populated.
