import alignedDatasetCsv from '../../../../data/processed/2026-04-29_aligned_dataset.csv?raw';

// Change this import to point the dashboard at another CSV.
// The parser expects a timestamp-ish column and a price column such as dam_price_eur_mwh.
export const dayAheadPriceCsv = alignedDatasetCsv;
