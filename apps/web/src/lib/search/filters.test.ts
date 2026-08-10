import { describe, expect, it } from "vitest";
import { buildSearchRequest, parseSearchState, serializeSearchState } from "@/lib/search/filters";

describe("search URL filter utilities", () => {
  it("parses known and passthrough filter keys", () => {
    const params = new URLSearchParams(
      "q=sterility&center=CDER&topics=drug%20safety,status&status=Final&from=2025-01-01&to=2025-12-31&docket=FDA-2025-D-0001&cfr=21%20CFR%20820&product=ABC123&submit=1&filter.custom_mode=alpha",
    );
    const parsed = parseSearchState(params);

    expect(parsed.submitted).toBe(true);
    expect(parsed.values.query).toBe("sterility");
    expect(parsed.values.center).toBe("CDER");
    expect(parsed.passthroughFilters.custom_mode).toBe("alpha");
  });

  it("serializes filters and submit flag", () => {
    const params = serializeSearchState(
      {
        query: " aseptic processing ",
        center: " CBER ",
        topics: "cell therapy, sterility",
        status: "Draft",
        dateFrom: "2026-01-01",
        dateTo: "2026-02-01",
        docketId: "FDA-2026-D-0002",
        cfr: "21 CFR 1271",
        productCode: "HCT/P",
      },
      true,
      { custom_mode: "beta" },
    );

    expect(params.get("q")).toBe("aseptic processing");
    expect(params.get("center")).toBe("CBER");
    expect(params.get("submit")).toBe("1");
    expect(params.get("filter.custom_mode")).toBe("beta");
  });

  it("builds request with typed filter fields", () => {
    const request = buildSearchRequest(
      {
        query: "sterility assurance",
        center: "CDRH",
        topics: "device, sterility",
        status: "Final",
        dateFrom: "2024-01-01",
        dateTo: "2024-12-31",
        docketId: "FDA-2024-D-1111",
        cfr: "21 CFR 820",
        productCode: "ABC, XYZ",
      },
      { custom_mode: "strict" },
    );

    expect(request.query).toBe("sterility assurance");
    expect(request.filters?.center).toBe("CDRH");
    expect(request.filters?.topics).toEqual(["device", "sterility"]);
    expect(request.filters?.cfr_references).toEqual(["21 CFR 820"]);
    expect(request.filters?.product_codes).toEqual(["ABC", "XYZ"]);
    expect((request.filters as Record<string, unknown>)?.custom_mode).toBe("strict");
  });
});
