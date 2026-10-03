"""predict_resolution_time (docs/PLAN.md §3, §5a).

Predicts how many days an exception will take to resolve. One tool contract
with interchangeable backends; every prediction gets a prediction_id and a
source label: sap-rpt-1.6, sap-rpt-1-oss, or baseline-median.

MVP item 1 builds only the Level 2 backend: the median resolution time per
exception type and port, taken from the exception history table. The SAP
backends (Levels 0 and 1) and the automatic fallback chain come with MVP item 5.
"""
