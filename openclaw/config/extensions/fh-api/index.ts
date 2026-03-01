const DEFAULT_BASE_URL = "http://host.docker.internal:8080/api/v1";
const DEFAULT_TIMEOUT_MS = 15000;
const MAX_SLOT_ITEMS = 10;

function toJsonText(payload: unknown): string {
  return JSON.stringify(payload, null, 2);
}

function cleanString(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function cleanNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return Math.trunc(value);
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return Math.trunc(parsed);
    }
  }
  return null;
}

function cleanPositiveNumber(value: unknown): number | null {
  const n = cleanNumber(value);
  if (n === null || n <= 0) {
    return null;
  }
  return n;
}

function sanitizeBaseUrl(value: unknown): string {
  const fallback = DEFAULT_BASE_URL;
  if (typeof value !== "string") {
    return fallback;
  }
  const trimmed = value.trim();
  if (!trimmed) {
    return fallback;
  }
  return trimmed.endsWith("/") ? trimmed.slice(0, -1) : trimmed;
}

function sanitizeTimeoutMs(value: unknown): number {
  const n = cleanNumber(value);
  if (!n || n < 1000 || n > 60000) {
    return DEFAULT_TIMEOUT_MS;
  }
  return n;
}

function resolveTelegramPatientId(ctx: { messageChannel?: string; sessionKey?: string }): number {
  if ((ctx.messageChannel || "").toLowerCase() !== "telegram") {
    throw new Error("fh_api is restricted to Telegram sessions");
  }

  const rawSessionKey = typeof ctx.sessionKey === "string" ? ctx.sessionKey : "";
  const patterns = [
    /:telegram:direct:(\d+)$/i,
    /:telegram:[^:]+:direct:(\d+)$/i,
    /^agent:[^:]+:direct:(\d+)$/i,
  ];

  for (const pattern of patterns) {
    const match = rawSessionKey.match(pattern);
    if (match && match[1]) {
      const id = Number(match[1]);
      if (Number.isFinite(id) && id > 0) {
        return Math.trunc(id);
      }
    }
  }

  throw new Error(
    "Unable to derive Telegram patient_id from session key. Keep session.dmScope=per-channel-peer and use Telegram DM sessions.",
  );
}

function buildUrl(baseUrl: string, path: string, query?: Record<string, unknown>): string {
  const url = new URL(`${baseUrl}${path}`);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null || value === "") {
        continue;
      }
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

async function requestJson(params: {
  baseUrl: string;
  timeoutMs: number;
  method: "GET" | "POST" | "DELETE";
  path: string;
  query?: Record<string, unknown>;
  body?: unknown;
}) {
  const url = buildUrl(params.baseUrl, params.path, params.query);
  const abort = AbortSignal.timeout(params.timeoutMs);
  const init: RequestInit = {
    method: params.method,
    signal: abort,
    headers: { Accept: "application/json" },
  };

  if (params.body !== undefined) {
    init.headers = {
      ...init.headers,
      "Content-Type": "application/json",
    };
    init.body = JSON.stringify(params.body);
  }

  const res = await fetch(url, init);
  const raw = await res.text();
  let parsed: unknown = raw;
  try {
    parsed = raw ? JSON.parse(raw) : {};
  } catch {
    // Keep raw text when API returns non-JSON.
  }

  if (!res.ok) {
    throw new Error(
      `fh_api ${params.method} ${params.path} failed (${res.status}): ${
        typeof parsed === "string" ? parsed : toJsonText(parsed)
      }`,
    );
  }

  return {
    ok: true,
    status: res.status,
    url,
    data: parsed,
  };
}

function requireStringParam(params: Record<string, unknown>, key: string): string {
  const value = cleanString(params[key]);
  if (!value) {
    throw new Error(`${key} is required`);
  }
  return value;
}

function requireNumberParam(params: Record<string, unknown>, key: string): number {
  const value = cleanNumber(params[key]);
  if (value === null) {
    throw new Error(`${key} is required`);
  }
  return value;
}

function normalizeSlotType(input: Record<string, unknown>): "doctor" | "service" {
  const explicitType = cleanString(input.type)?.toLowerCase();
  if (explicitType === "doctor" || explicitType === "service") {
    return explicitType;
  }

  const hasDoctor =
    cleanPositiveNumber(input.doctor_id) !== null ||
    cleanString(input.doctor_name) !== null ||
    cleanPositiveNumber(input.direction_id) !== null;
  const hasService = cleanPositiveNumber(input.service_id) !== null;

  if (hasDoctor) return "doctor";
  if (hasService) return "service";
  throw new Error("type is required (doctor|service), or provide doctor/service identifiers");
}

function normalizeVisitType(input: Record<string, unknown>): "DOCTOR" | "SERVICE" {
  const explicit = cleanString(input.visit_type)?.toUpperCase();
  if (explicit === "DOCTOR" || explicit === "SERVICE") {
    return explicit;
  }

  if (cleanPositiveNumber(input.doctor_id) !== null) return "DOCTOR";
  if (cleanPositiveNumber(input.service_id) !== null) return "SERVICE";
  throw new Error("visit_type is required (DOCTOR|SERVICE), or provide doctor_id/service_id");
}

function normalizeApiDateTime(value: string): string {
  let text = value.trim();
  text = text.replace(/\s+/g, "T");
  text = text.replace(/\.\d+/, "");
  text = text.replace(/Z$/i, "");
  text = text.replace(/[+-]\d{2}:\d{2}$/, "");
  return text;
}

function looksLikeDateOnly(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value.trim());
}

function looksLikeTimeOnly(value: string): boolean {
  return /^([01]\d|2[0-3]):[0-5]\d(:[0-5]\d)?$/.test(value.trim());
}

function mergeDateAndTime(dateText: string, timeText: string): string | null {
  const date = dateText.trim();
  const time = timeText.trim();
  if (!looksLikeDateOnly(date) || !looksLikeTimeOnly(time)) {
    return null;
  }
  const fullTime = time.length === 5 ? `${time}:00` : time;
  return `${date}T${fullTime}`;
}

function normalizeSearchDateTime(input: Record<string, unknown>, key: "time_from" | "time_to"): string {
  const raw = requireStringParam(input, key);
  const startRaw = cleanString(input.start);

  if (looksLikeTimeOnly(raw) && startRaw) {
    const startDate = startRaw.trim().split("T")[0];
    const merged = mergeDateAndTime(startDate, raw);
    if (merged) {
      return normalizeApiDateTime(merged);
    }
  }

  return normalizeApiDateTime(raw);
}

function normalizeText(value: unknown): string {
  if (typeof value !== "string") return "";
  return value
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function doctorFullName(doctor: any): string {
  return [doctor?.first_name, doctor?.last_name, doctor?.middle_name]
    .map((part) => (typeof part === "string" ? part.trim() : ""))
    .filter(Boolean)
    .join(" ");
}

function filterDoctorsByName(doctors: any[], query: string): any[] {
  const tokens = normalizeText(query).split(" ").filter(Boolean);
  if (tokens.length === 0) return doctors;
  return doctors.filter((doctor) => {
    const fullName = doctorFullName(doctor);
    const bio = typeof doctor?.bio_text === "string" ? doctor.bio_text : "";
    const haystack = normalizeText(fullName + " " + bio);
    return tokens.every((token) => haystack.includes(token));
  });
}

function compactSlotsResult(result: any) {
  if (!result || typeof result !== "object") return result;
  const data = result.data;
  if (!data || typeof data !== "object") return result;
  const items = Array.isArray(data.items) ? data.items : null;
  if (!items) return result;
  if (items.length <= MAX_SLOT_ITEMS) return result;
  return {
    ...result,
    data: {
      ...data,
      items: items.slice(0, MAX_SLOT_ITEMS),
      _truncated: true,
      _returned: MAX_SLOT_ITEMS,
      _total: items.length,
    },
  };
}

function parseApiDateTime(value: unknown): Date | null {
  if (typeof value !== "string") return null;
  const normalized = normalizeApiDateTime(value);
  const parsed = new Date(normalized);
  if (!Number.isFinite(parsed.getTime())) return null;
  return parsed;
}

function filterFutureFreeSlots(result: any) {
  if (!result || typeof result !== "object") return result;
  const data = result.data;
  if (!data || typeof data !== "object") return result;
  const items = Array.isArray(data.items) ? data.items : null;
  if (!items) return result;

  const now = new Date();
  const filtered = items.filter((item: any) => {
    if (item?.is_free === false) return false;
    const start = parseApiDateTime(item?.start);
    if (!start) return false;
    return start.getTime() >= now.getTime();
  });

  return {
    ...result,
    data: {
      ...data,
      items: filtered,
      _future_filtered: true,
      _before_filter_count: items.length,
      _after_filter_count: filtered.length,
    },
  };
}

const fhApiPlugin = {
  id: "fh-api",
  name: "Family Health API",
  description: "Clinic appointment API tooling for Family Health demo",
  register(api: any) {
    api.registerTool(
      (ctx: any) => {
        const baseUrl = sanitizeBaseUrl(api.pluginConfig?.baseUrl);
        const timeoutMs = sanitizeTimeoutMs(api.pluginConfig?.timeoutMs);

        return {
          name: "fh_api",
          description:
            "Family Health scheduling API (list clinics/directions/doctors/services, search slots, book/list/cancel visits).",
          parameters: {
            type: "object",
            additionalProperties: false,
            properties: {
              action: {
                type: "string",
                enum: [
                  "list_clinics",
                  "list_directions",
                  "list_doctors",
                  "list_services",
                  "search_slots",
                  "book_visit",
                  "list_visits",
                  "cancel_visit",
                ],
              },
              direction_id: { type: "integer" },
              clinic_id: { type: "integer" },
              service_id: { type: "integer" },
              doctor_id: { type: "integer" },
              doctor_name: { type: "string" },
              district: { type: "string" },
              name: { type: "string" },
              type: { type: "string" },
              include_busy: { type: "boolean" },
              time_from: { type: "string" },
              time_to: { type: "string" },
              scope: { type: "string" },
              visit_id: { type: "integer" },
              visit_type: { type: "string" },
              start: { type: "string" },
            },
            required: ["action"],
          },
          async execute(_toolCallId: string, input: Record<string, unknown>) {
            const action = requireStringParam(input, "action");
            const patientId = resolveTelegramPatientId(ctx);

            let result: unknown;

            if (action === "list_clinics") {
              result = await requestJson({ baseUrl, timeoutMs, method: "GET", path: "/clinics" });
            } else if (action === "list_directions") {
              result = await requestJson({
                baseUrl,
                timeoutMs,
                method: "GET",
                path: "/directions",
              });
            } else if (action === "list_doctors") {
              const requestedName = cleanString(input.name);
              const directionId = cleanPositiveNumber(input.direction_id);
              const doctorsResult = await requestJson({
                baseUrl,
                timeoutMs,
                method: "GET",
                path: "/doctors",
                query: {
                  direction_id: directionId,
                  name: requestedName,
                },
              });

              if (requestedName && Array.isArray(doctorsResult.data) && doctorsResult.data.length === 0) {
                const fallbackAll = await requestJson({
                  baseUrl,
                  timeoutMs,
                  method: "GET",
                  path: "/doctors",
                  query: {
                    direction_id: directionId,
                  },
                });
                const fallbackItems = Array.isArray(fallbackAll.data) ? fallbackAll.data : [];
                result = {
                  ...fallbackAll,
                  data: filterDoctorsByName(fallbackItems, requestedName),
                };
              } else {
                result = doctorsResult;
              }
            } else if (action === "list_services") {
              result = await requestJson({
                baseUrl,
                timeoutMs,
                method: "GET",
                path: "/services",
                query: {
                  clinic_id: cleanPositiveNumber(input.clinic_id),
                  name: cleanString(input.name),
                },
              });
            } else if (action === "search_slots") {
              const slotType = normalizeSlotType(input);
              const timeFrom = normalizeSearchDateTime(input, "time_from");
              const timeTo = normalizeSearchDateTime(input, "time_to");
              let doctorId = slotType === "doctor" ? cleanPositiveNumber(input.doctor_id) : null;
              const requestedDoctorName = cleanString(input.doctor_name);
              const directionId = cleanPositiveNumber(input.direction_id);
              if (doctorId === null && requestedDoctorName) {
                const byName = await requestJson({
                  baseUrl,
                  timeoutMs,
                  method: "GET",
                  path: "/doctors",
                  query: { name: requestedDoctorName },
                });
                let candidates = Array.isArray(byName.data) ? byName.data : [];
                if (candidates.length === 0) {
                  const allDoctors = await requestJson({
                    baseUrl,
                    timeoutMs,
                    method: "GET",
                    path: "/doctors",
                  });
                  const allItems = Array.isArray(allDoctors.data) ? allDoctors.data : [];
                  candidates = filterDoctorsByName(allItems, requestedDoctorName);
                }
                if (candidates.length === 1) {
                  doctorId = cleanPositiveNumber(candidates[0]?.id);
                }
              }
              // The demo API matches doctor_name loosely and can miss "First Last" forms.
              // Prefer filtering by doctor_id client-side when doctor_id is known.
              const doctorNameQuery = doctorId === null ? requestedDoctorName : null;

              const rawSlotsResult = await requestJson({
                baseUrl,
                timeoutMs,
                method: "GET",
                path: "/slots/search",
                query: {
                  patient_id: patientId,
                  type: slotType,
                  time_from: timeFrom,
                  time_to: timeTo,
                  district: cleanString(input.district),
                  clinic_id: cleanPositiveNumber(input.clinic_id),
                  direction_id: directionId,
                  doctor_name: slotType === "doctor" ? doctorNameQuery : null,
                  service_id: slotType === "service" ? cleanPositiveNumber(input.service_id) : null,
                  include_busy: typeof input.include_busy === "boolean" ? input.include_busy : undefined,
                },
              });
              let slotsResult = rawSlotsResult;
              if (doctorId !== null) {
                const data = rawSlotsResult?.data;
                const items = Array.isArray(data?.items) ? data.items : [];
                slotsResult = {
                  ...rawSlotsResult,
                  data: {
                    ...data,
                    items: items.filter((item: any) => cleanNumber(item?.doctor_id) === doctorId),
                  },
                };
              }

              let futureSlotsResult = filterFutureFreeSlots(slotsResult);

              // If clinic changed after a doctor was inferred earlier, doctor_id filter can hide
              // valid same-specialty slots in the new clinic. Relax to direction-level search.
              if (slotType === "doctor" && doctorId !== null && requestedDoctorName === null) {
                const filteredItems = Array.isArray((futureSlotsResult as any)?.data?.items)
                  ? (futureSlotsResult as any).data.items
                  : [];
                if (filteredItems.length === 0) {
                  let fallbackDirectionId = directionId;
                  if (fallbackDirectionId === null) {
                    const doctorsCatalog = await requestJson({
                      baseUrl,
                      timeoutMs,
                      method: "GET",
                      path: "/doctors",
                    });
                    const doctors = Array.isArray(doctorsCatalog.data) ? doctorsCatalog.data : [];
                    const matched = doctors.find((d: any) => cleanNumber(d?.id) === doctorId) as any;
                    const dirs = Array.isArray(matched?.directions) ? matched.directions : [];
                    fallbackDirectionId = cleanPositiveNumber(dirs[0]?.id);
                  }

                  if (fallbackDirectionId !== null) {
                    const broadenedRawSlots = await requestJson({
                      baseUrl,
                      timeoutMs,
                      method: "GET",
                      path: "/slots/search",
                      query: {
                        patient_id: patientId,
                        type: "doctor",
                        time_from: timeFrom,
                        time_to: timeTo,
                        district: cleanString(input.district),
                        clinic_id: cleanPositiveNumber(input.clinic_id),
                        direction_id: fallbackDirectionId,
                        include_busy: typeof input.include_busy === "boolean" ? input.include_busy : undefined,
                      },
                    });
                    const broadenedFuture = filterFutureFreeSlots(broadenedRawSlots as any);
                    const data = (broadenedFuture as any)?.data;
                    futureSlotsResult = {
                      ...(broadenedFuture as any),
                      data: {
                        ...(typeof data === "object" && data ? data : {}),
                        _doctor_filter_relaxed: true,
                        _requested_doctor_id: doctorId,
                        _fallback_direction_id: fallbackDirectionId,
                      },
                    };
                  }
                }
              }

              result = compactSlotsResult(futureSlotsResult);
            } else if (action === "book_visit") {
              const doctorId = cleanPositiveNumber(input.doctor_id);
              const serviceId = cleanPositiveNumber(input.service_id);
              result = await requestJson({
                baseUrl,
                timeoutMs,
                method: "POST",
                path: "/visits",
                query: { patient_id: patientId },
                body: {
                  visit_type: normalizeVisitType(input),
                  doctor_id: doctorId,
                  service_id: serviceId,
                  clinic_id: cleanPositiveNumber(input.clinic_id),
                  start: normalizeApiDateTime(requireStringParam(input, "start")),
                },
              });
            } else if (action === "list_visits") {
              result = await requestJson({
                baseUrl,
                timeoutMs,
                method: "GET",
                path: "/visits",
                query: {
                  patient_id: patientId,
                  time_from: cleanString(input.time_from),
                  time_to: cleanString(input.time_to),
                  scope: cleanString(input.scope) || "mine",
                },
              });
            } else if (action === "cancel_visit") {
              const visitId = requireNumberParam(input, "visit_id");
              result = await requestJson({
                baseUrl,
                timeoutMs,
                method: "DELETE",
                path: `/visits/${visitId}`,
                query: { patient_id: patientId },
              });
            } else {
              throw new Error(`Unsupported action: ${action}`);
            }

            return {
              content: [{ type: "text", text: toJsonText(result) }],
              details: result,
            };
          },
        };
      }
    );
  },
};

export default fhApiPlugin;
