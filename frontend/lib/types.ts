export type CaseStatus =
  | "analyzing"
  | "awaiting_approval"
  | "executing"
  | "monitoring"
  | "needs_human_decision";
export type Event = {
  event_id: string;
  scenario: string;
  type: string;
  shipment_id: string;
  description: string;
};
export type CaseSummary = {
  case_id: string;
  shipment_id: string;
  status: CaseStatus;
};
export type Health = {
  running: boolean;
  mode: string;
  model: string;
  prediction: string;
  synthetic_data: boolean;
};
export type LogEntry = {
  seq: number;
  at: string;
  actor: string;
  kind: string;
  summary: string;
  source?: string;
  flag?: string;
};
export type Transfer = {
  quantity_t: number;
  source_plant: string;
  cost_usd: number;
  lead_time_days: number;
};
export type Assessment = {
  assessment_id: string;
  priority_level: string;
  transfer: Transfer | null;
  coverage_days: number;
  required_coverage_days: number;
  shortage_t: number;
  covered: boolean;
  deferred_orders: {
    order_id: string;
    priority: string;
    quantity_t?: number;
  }[];
};
export type Validation = {
  validation_id: string;
  valid: boolean;
  quantity: number;
  source_plant: string;
  destination_plant: string;
  violations: string[];
};
export type Action = {
  validation_id: string;
  status: "awaiting_approval" | "executed";
  validation: Validation;
  approval?: { approver: string; decision: string } | null;
  sto?: { purchase_order: string; quantity_t: number } | null;
};
export type Prediction = {
  predicted_days: number;
  source: string;
  basis: {
    fallback_reason?: string;
    cases?: number;
    context_cases?: number;
    interval_days?: number[];
  };
};
export type Plan = {
  exception: string;
  evidence: { fact: string; source: string }[];
  impact: Assessment & { prediction: Prediction };
  options: {
    name: string;
    note: string;
    assessment: Assessment;
    validation?: Validation | null;
  }[];
  recommendation: string;
  recommended_option: string | null;
  escalation: string | null;
  next_check: string;
  actions: Action[];
};
export type PlantStock = {
  plant: string;
  unrestricted_t: number;
  safety_stock_t: number;
  in_transit_t: number;
  consumption_t_per_day: Record<string, number>;
  orders: {
    order_id: string;
    product: string;
    priority: string;
    consumption_t_per_day: number;
  }[];
};
export type Case = CaseSummary & {
  running: boolean;
  status_reason: string | null;
  updated_at: string;
  shipment: {
    shipment_id: string;
    purchase_order: string;
    eta: string;
    port_of_loading: string;
    port_of_discharge: string;
    vessel?: string;
  };
  documents: {
    required_documents: string[];
    documents: { document_type: string; text: string }[];
  };
  reconciliation: {
    purchase_order: {
      source: string;
      purchase_order: string;
      material: string;
      quantity: number;
    };
    discrepancies: {
      field: string;
      purchase_order_value: string | number;
      document_values: Record<string, string | number>;
      mismatched_documents: string[];
    }[];
    verified_extractions: {
      field: string;
      document_type: string;
      quote: string;
      value: string | number;
    }[];
  } | null;
  inventory: { material: string; plants: PlantStock[] };
  plan: Plan | null;
};
