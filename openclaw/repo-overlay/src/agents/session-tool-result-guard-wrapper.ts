import type { SessionManager } from "@mariozechner/pi-coding-agent";
import { getGlobalHookRunner } from "../plugins/hook-runner-global.js";
import {
  applyInputProvenanceToUserMessage,
  type InputProvenance,
} from "../sessions/input-provenance.js";
import { installSessionToolResultGuard } from "./session-tool-result-guard.js";
import type { AgentMessage } from "@mariozechner/pi-agent-core";

export type GuardedSessionManager = SessionManager & {
  /** Flush any synthetic tool results for pending tool calls. Idempotent. */
  flushPendingToolResults?: () => void;
  /** Clear pending tool calls without persisting synthetic tool results. Idempotent. */
  clearPendingToolResults?: () => void;
};

function extractToolResultText(message: AgentMessage): string | null {
  const content = (message as { content?: unknown }).content;
  if (typeof content === "string") {
    return content;
  }
  if (!Array.isArray(content)) {
    return null;
  }
  const parts = content
    .map((item) => {
      if (!item || typeof item !== "object") {
        return null;
      }
      const block = item as { type?: unknown; text?: unknown };
      return block.type === "text" && typeof block.text === "string" ? block.text : null;
    })
    .filter((item): item is string => typeof item === "string" && item.length > 0);
  return parts.length > 0 ? parts.join("\n") : null;
}

function toToolResultTextMessage(message: AgentMessage, text: string): AgentMessage {
  const record = message as unknown as Record<string, unknown>;
  const { details: _details, ...rest } = record;
  return {
    ...rest,
    content: [{ type: "text", text }],
  } as AgentMessage;
}

function parseJsonObject(text: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(text);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

function summarizeListItems(path: string, items: unknown[]): string {
  const samples = items
    .slice(0, 3)
    .map((item) => {
      if (!item || typeof item !== "object") {
        return null;
      }
      const row = item as Record<string, unknown>;
      const numberId = (value: unknown, prefix = "#") =>
        typeof value === "number" ? `${prefix}${value}` : null;
      const text = (value: unknown) => (typeof value === "string" && value.trim() ? value : null);

      if (path === "doctors") {
        const directions = Array.isArray(row.directions)
          ? row.directions
              .map((direction) =>
                direction && typeof direction === "object"
                  ? text((direction as Record<string, unknown>).name)
                  : null,
              )
              .filter((value): value is string => Boolean(value))
              .join(", ")
          : text(row.doctor_directions);
        return [
          numberId(row.id),
          text(row.last_name) && text(row.first_name)
            ? `${text(row.last_name)} ${text(row.first_name)}`
            : text(row.doctor_name),
          numberId(row.clinic_id, "clinic#"),
          text(row.clinic_name),
          directions,
        ]
          .filter(Boolean)
          .join(" | ");
      }

      if (path === "slots/search") {
        return [
          numberId(row.doctor_id, "doctor#"),
          text(row.doctor_name),
          numberId(row.clinic_id, "clinic#"),
          text(row.clinic_name),
          text(row.start),
          typeof row.is_free === "boolean" ? (row.is_free ? "free" : "busy") : null,
        ]
          .filter(Boolean)
          .join(" | ");
      }

      if (path === "clinics") {
        return [numberId(row.id), text(row.name), text(row.district)].filter(Boolean).join(" | ");
      }

      if (path === "directions") {
        return [numberId(row.id), text(row.name)].filter(Boolean).join(" | ");
      }

      const start = typeof row.start === "string" ? row.start : null;
      const doctor = typeof row.doctor_name === "string" ? row.doctor_name : null;
      const service = typeof row.service_name === "string" ? row.service_name : null;
      const clinic = typeof row.clinic_name === "string" ? row.clinic_name : null;
      const visitId = typeof row.visit_id === "number" ? `#${row.visit_id}` : null;
      const id = typeof row.id === "number" ? `#${row.id}` : null;
      const name = typeof row.name === "string" ? row.name : null;
      return [visitId, id, doctor, service, name, clinic, start].filter(Boolean).join(" | ");
    })
    .filter((item): item is string => typeof item === "string" && item.length > 0);
  return samples.length > 0 ? ` sample=${samples.join(" ; ")}` : "";
}

export function summarizeFhApiToolResultMessage(message: AgentMessage): AgentMessage {
  const text = extractToolResultText(message);
  if (!text) {
    return message;
  }

  const payload = parseJsonObject(text);
  if (!payload) {
    return message;
  }

  if (typeof payload.error === "string") {
    return toToolResultTextMessage(message, `fh_api error: ${payload.error}`);
  }

  const status = typeof payload.status === "number" ? payload.status : null;
  const url = typeof payload.url === "string" ? payload.url : null;
  const data = payload.data;
  const path = url ? (() => {
    try {
      return new URL(url).pathname.replace(/^\/api\/v1\//, "");
    } catch {
      return url;
    }
  })() : "unknown";

  if (data && typeof data === "object" && !Array.isArray(data)) {
    const record = data as Record<string, unknown>;
    if (typeof record.visit_id === "number") {
      const statusText = typeof record.status === "string" ? ` status=${record.status}` : "";
      return toToolResultTextMessage(
        message,
        `fh_api ok ${path}: visit_id=${record.visit_id}${statusText}`,
      );
    }
    if (Array.isArray(record.items)) {
      const total =
        typeof record._total === "number"
          ? record._total
          : typeof record._after_filter_count === "number"
            ? record._after_filter_count
            : record.items.length;
      return toToolResultTextMessage(
        message,
        `fh_api ok ${path}: items=${total}${summarizeListItems(path, record.items)}`,
      );
    }
  }

  if (Array.isArray(data)) {
    return toToolResultTextMessage(
      message,
      `fh_api ok ${path}: items=${data.length}${summarizeListItems(path, data)}`,
    );
  }

  const statusText = status !== null ? ` status=${status}` : "";
  return toToolResultTextMessage(message, `fh_api ok ${path}${statusText}`);
}

/**
 * Apply the tool-result guard to a SessionManager exactly once and expose
 * a flush method on the instance for easy teardown handling.
 */
export function guardSessionManager(
  sessionManager: SessionManager,
  opts?: {
    agentId?: string;
    sessionKey?: string;
    inputProvenance?: InputProvenance;
    allowSyntheticToolResults?: boolean;
    allowedToolNames?: Iterable<string>;
  },
): GuardedSessionManager {
  if (typeof (sessionManager as GuardedSessionManager).flushPendingToolResults === "function") {
    return sessionManager as GuardedSessionManager;
  }

  const hookRunner = getGlobalHookRunner();
  const beforeMessageWrite = hookRunner?.hasHooks("before_message_write")
    ? (event: { message: import("@mariozechner/pi-agent-core").AgentMessage }) => {
        return hookRunner.runBeforeMessageWrite(event, {
          agentId: opts?.agentId,
          sessionKey: opts?.sessionKey,
        });
      }
    : undefined;

  const transform = hookRunner?.hasHooks("tool_result_persist")
    ? // oxlint-disable-next-line typescript/no-explicit-any
      (message: any, meta: { toolCallId?: string; toolName?: string; isSynthetic?: boolean }) => {
        const baseMessage =
          meta.toolName === "fh_api" ? summarizeFhApiToolResultMessage(message) : message;
        const out = hookRunner.runToolResultPersist(
          {
            toolName: meta.toolName,
            toolCallId: meta.toolCallId,
            message: baseMessage,
            isSynthetic: meta.isSynthetic,
          },
          {
            agentId: opts?.agentId,
            sessionKey: opts?.sessionKey,
            toolName: meta.toolName,
            toolCallId: meta.toolCallId,
          },
        );
        return out?.message ?? baseMessage;
      }
    : (
        message: AgentMessage,
        meta: { toolCallId?: string; toolName?: string; isSynthetic?: boolean },
      ) => (meta.toolName === "fh_api" ? summarizeFhApiToolResultMessage(message) : message);

  const guard = installSessionToolResultGuard(sessionManager, {
    transformMessageForPersistence: (message) =>
      applyInputProvenanceToUserMessage(message, opts?.inputProvenance),
    transformToolResultForPersistence: transform,
    allowSyntheticToolResults: opts?.allowSyntheticToolResults,
    allowedToolNames: opts?.allowedToolNames,
    beforeMessageWriteHook: beforeMessageWrite,
  });
  (sessionManager as GuardedSessionManager).flushPendingToolResults = guard.flushPendingToolResults;
  (sessionManager as GuardedSessionManager).clearPendingToolResults = guard.clearPendingToolResults;
  return sessionManager as GuardedSessionManager;
}
