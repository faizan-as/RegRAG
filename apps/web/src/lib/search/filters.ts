import type { components } from "@/lib/api/schema";

type SearchFilters = components["schemas"]["SearchFilters"];
type SearchRequest = components["schemas"]["SearchRequest"];

export type SearchFormValues = {
  query: string;
  center: string;
  topics: string;
  status: string;
  dateFrom: string;
  dateTo: string;
  docketId: string;
  cfr: string;
  productCode: string;
};

export type ParsedSearchState = {
  values: SearchFormValues;
  submitted: boolean;
  passthroughFilters: Record<string, string>;
};

const EMPTY_VALUES: SearchFormValues = {
  query: "",
  center: "",
  topics: "",
  status: "",
  dateFrom: "",
  dateTo: "",
  docketId: "",
  cfr: "",
  productCode: "",
};

function splitCsv(value: string): string[] {
  return value
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
}

function joinCsv(values: string[] | undefined): string {
  return (values ?? []).map((value) => value.trim()).filter(Boolean).join(", ");
}

function setIfPresent(filters: SearchFilters, key: keyof SearchFilters, value: string): void {
  if (value.trim()) {
    (filters as Record<string, unknown>)[key] = value.trim();
  }
}

export function buildSearchRequest(
  values: SearchFormValues,
  passthroughFilters: Record<string, string> = {},
): SearchRequest {
  const query = values.query.trim();
  const filters: SearchFilters = {};

  setIfPresent(filters, "center", values.center);
  setIfPresent(filters, "status", values.status);
  setIfPresent(filters, "docket_id", values.docketId);
  setIfPresent(filters, "issue_date_from", values.dateFrom);
  setIfPresent(filters, "issue_date_to", values.dateTo);

  const topics = splitCsv(values.topics);
  if (topics.length > 0) {
    filters.topics = topics;
  }

  const cfrReferences = splitCsv(values.cfr);
  if (cfrReferences.length > 0) {
    filters.cfr_references = cfrReferences;
  }

  const productCodes = splitCsv(values.productCode);
  if (productCodes.length > 0) {
    filters.product_codes = productCodes;
  }

  for (const [key, value] of Object.entries(passthroughFilters)) {
    if (value.trim()) {
      (filters as Record<string, unknown>)[key] = value.trim();
    }
  }

  const request: SearchRequest = { query };
  if (Object.keys(filters).length > 0) {
    request.filters = filters;
  }
  return request;
}

export function parseSearchState(params: URLSearchParams): ParsedSearchState {
  const passthroughFilters: Record<string, string> = {};

  for (const [key, value] of params.entries()) {
    if (!key.startsWith("filter.")) {
      continue;
    }
    const filterKey = key.slice("filter.".length).trim();
    if (!filterKey || !value.trim()) {
      continue;
    }
    passthroughFilters[filterKey] = value.trim();
  }

  return {
    submitted: params.get("submit") === "1",
    passthroughFilters,
    values: {
      query: params.get("q")?.trim() ?? EMPTY_VALUES.query,
      center: params.get("center")?.trim() ?? EMPTY_VALUES.center,
      topics: params.get("topics")?.trim() ?? EMPTY_VALUES.topics,
      status: params.get("status")?.trim() ?? EMPTY_VALUES.status,
      dateFrom: params.get("from")?.trim() ?? EMPTY_VALUES.dateFrom,
      dateTo: params.get("to")?.trim() ?? EMPTY_VALUES.dateTo,
      docketId: params.get("docket")?.trim() ?? EMPTY_VALUES.docketId,
      cfr: params.get("cfr")?.trim() ?? EMPTY_VALUES.cfr,
      productCode: params.get("product")?.trim() ?? EMPTY_VALUES.productCode,
    },
  };
}

export function serializeSearchState(
  values: SearchFormValues,
  submitted: boolean,
  passthroughFilters: Record<string, string> = {},
): URLSearchParams {
  const params = new URLSearchParams();

  if (values.query.trim()) {
    params.set("q", values.query.trim());
  }
  if (values.center.trim()) {
    params.set("center", values.center.trim());
  }
  if (values.topics.trim()) {
    params.set("topics", joinCsv(splitCsv(values.topics)));
  }
  if (values.status.trim()) {
    params.set("status", values.status.trim());
  }
  if (values.dateFrom.trim()) {
    params.set("from", values.dateFrom.trim());
  }
  if (values.dateTo.trim()) {
    params.set("to", values.dateTo.trim());
  }
  if (values.docketId.trim()) {
    params.set("docket", values.docketId.trim());
  }
  if (values.cfr.trim()) {
    params.set("cfr", joinCsv(splitCsv(values.cfr)));
  }
  if (values.productCode.trim()) {
    params.set("product", joinCsv(splitCsv(values.productCode)));
  }
  if (submitted) {
    params.set("submit", "1");
  }

  for (const [key, value] of Object.entries(passthroughFilters)) {
    if (key.trim() && value.trim()) {
      params.set(`filter.${key.trim()}`, value.trim());
    }
  }

  return params;
}

export function emptySearchFormValues(): SearchFormValues {
  return { ...EMPTY_VALUES };
}
