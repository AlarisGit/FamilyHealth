import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import type { AgentMessage } from "@mariozechner/pi-agent-core";
import { SessionManager } from "@mariozechner/pi-coding-agent";
import { describe, expect, it, afterEach } from "vitest";
import {
  initializeGlobalHookRunner,
  resetGlobalHookRunner,
} from "../plugins/hook-runner-global.js";
import { loadOpenClawPlugins } from "../plugins/loader.js";
import {
  guardSessionManager,
  summarizeFhApiToolResultMessage,
} from "./session-tool-result-guard-wrapper.js";

const EMPTY_PLUGIN_SCHEMA = { type: "object", additionalProperties: false, properties: {} };

function writeTempPlugin(params: { dir: string; id: string; body: string }): string {
  const pluginDir = path.join(params.dir, params.id);
  fs.mkdirSync(pluginDir, { recursive: true });
  const file = path.join(pluginDir, `${params.id}.mjs`);
  fs.writeFileSync(file, params.body, "utf-8");
  fs.writeFileSync(
    path.join(pluginDir, "openclaw.plugin.json"),
    JSON.stringify(
      {
        id: params.id,
        configSchema: EMPTY_PLUGIN_SCHEMA,
      },
      null,
      2,
    ),
    "utf-8",
  );
  return file;
}

function appendToolCallAndResult(sm: ReturnType<typeof SessionManager.inMemory>) {
  const appendMessage = sm.appendMessage.bind(sm) as unknown as (message: AgentMessage) => void;
  appendMessage({
    role: "assistant",
    content: [{ type: "toolCall", id: "call_1", name: "read", arguments: {} }],
  } as AgentMessage);

  appendMessage({
    role: "toolResult",
    toolCallId: "call_1",
    isError: false,
    content: [{ type: "text", text: "ok" }],
    details: { big: "x".repeat(10_000) },
    // oxlint-disable-next-line typescript/no-explicit-any
  } as any);
}

function getPersistedToolResult(sm: ReturnType<typeof SessionManager.inMemory>) {
  const messages = sm
    .getEntries()
    .filter((e) => e.type === "message")
    .map((e) => (e as { message: AgentMessage }).message);

  // oxlint-disable-next-line typescript/no-explicit-any
  return messages.find((m) => (m as any).role === "toolResult") as any;
}

afterEach(() => {
  resetGlobalHookRunner();
});

describe("tool_result_persist hook", () => {
  it("does not modify persisted toolResult messages when no hook is registered", () => {
    const sm = guardSessionManager(SessionManager.inMemory(), {
      agentId: "main",
      sessionKey: "main",
    });
    appendToolCallAndResult(sm);
    const toolResult = getPersistedToolResult(sm);
    expect(toolResult).toBeTruthy();
    expect(toolResult.details).toBeTruthy();
  });

  it("loads tool_result_persist hooks without breaking persistence", () => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "openclaw-toolpersist-"));
    process.env.OPENCLAW_BUNDLED_PLUGINS_DIR = "/nonexistent/bundled/plugins";

    const pluginA = writeTempPlugin({
      dir: tmp,
      id: "persist-a",
      body: `export default { id: "persist-a", register(api) {
  api.on("tool_result_persist", (event, ctx) => {
    const msg = event.message;
    // Example: remove large diagnostic payloads before persistence.
    const { details: _details, ...rest } = msg;
    return { message: { ...rest, persistOrder: ["a"], agentSeen: ctx.agentId ?? null } };
  }, { priority: 10 });
} };`,
    });

    const pluginB = writeTempPlugin({
      dir: tmp,
      id: "persist-b",
      body: `export default { id: "persist-b", register(api) {
  api.on("tool_result_persist", (event) => {
    const prior = (event.message && event.message.persistOrder) ? event.message.persistOrder : [];
    return { message: { ...event.message, persistOrder: [...prior, "b"] } };
  }, { priority: 5 });
} };`,
    });

    const registry = loadOpenClawPlugins({
      cache: false,
      workspaceDir: tmp,
      config: {
        plugins: {
          load: { paths: [pluginA, pluginB] },
          allow: ["persist-a", "persist-b"],
        },
      },
    });
    initializeGlobalHookRunner(registry);

    const sm = guardSessionManager(SessionManager.inMemory(), {
      agentId: "main",
      sessionKey: "main",
    });

    appendToolCallAndResult(sm);
    const toolResult = getPersistedToolResult(sm);
    expect(toolResult).toBeTruthy();

    // Hook registration should preserve a valid toolResult message shape.
    expect(toolResult.role).toBe("toolResult");
    expect(toolResult.toolCallId).toBe("call_1");
    expect(Array.isArray(toolResult.content)).toBe(true);
  });

  it("summarizes fh_api list payloads before persistence", () => {
    const summarized = summarizeFhApiToolResultMessage({
      role: "toolResult",
      toolCallId: "call_fh",
      toolName: "fh_api",
      isError: false,
      content: [
        {
          type: "text",
          text: JSON.stringify({
            ok: true,
            status: 200,
            url: "http://127.0.0.1:8080/api/v1/visits?patient_id=173328158&scope=mine",
            data: {
              items: [
                {
                  visit_id: 5,
                  doctor_name: "Weber Julia",
                  clinic_name: "Family Health Pankow",
                  start: "2026-03-12T12:40:00",
                },
                {
                  visit_id: 6,
                  service_name: "MRI",
                  clinic_name: "Family Health West",
                  start: "2026-03-13T08:00:00",
                },
              ],
            },
          }),
        },
      ],
    } as AgentMessage);

    const text = ((summarized as { content: Array<{ text: string }> }).content[0] ?? {}).text;
    expect(text).toContain("fh_api ok visits: items=2");
    expect(text).toContain("#5 | Weber Julia | Family Health Pankow | 2026-03-12T12:40:00");
    expect(text).toContain("#6 | MRI | Family Health West | 2026-03-13T08:00:00");
  });

  it("summarizes fh_api booking payloads before persistence", () => {
    const summarized = summarizeFhApiToolResultMessage({
      role: "toolResult",
      toolCallId: "call_fh",
      toolName: "fh_api",
      isError: false,
      content: [
        {
          type: "text",
          text: JSON.stringify({
            ok: true,
            status: 200,
            url: "http://127.0.0.1:8080/api/v1/visits?patient_id=173328158",
            data: { visit_id: 5, status: "booked" },
          }),
        },
      ],
    } as AgentMessage);

    const text = ((summarized as { content: Array<{ text: string }> }).content[0] ?? {}).text;
    expect(text).toBe("fh_api ok visits: visit_id=5 status=booked");
  });

  it("summarizes fh_api errors before persistence", () => {
    const summarized = summarizeFhApiToolResultMessage({
      role: "toolResult",
      toolCallId: "call_fh",
      toolName: "fh_api",
      isError: true,
      content: [
        {
          type: "text",
          text: JSON.stringify({
            status: "error",
            tool: "fh_api",
            error: "fetch failed",
          }),
        },
      ],
    } as AgentMessage);

    const text = ((summarized as { content: Array<{ text: string }> }).content[0] ?? {}).text;
    expect(text).toBe("fh_api error: fetch failed");
  });

  it("applies built-in fh_api summary inside guardSessionManager", () => {
    const sm = guardSessionManager(SessionManager.inMemory(), {
      agentId: "clinic",
      sessionKey: "agent:clinic:telegram:direct:173328158",
    });
    const appendMessage = sm.appendMessage.bind(sm) as unknown as (message: AgentMessage) => void;

    appendMessage({
      role: "assistant",
      content: [{ type: "toolCall", id: "call_1", name: "fh_api", arguments: {} }],
    } as AgentMessage);
    appendMessage({
      role: "toolResult",
      toolCallId: "call_1",
      toolName: "fh_api",
      isError: false,
      content: [
        {
          type: "text",
          text: JSON.stringify({
            ok: true,
            status: 200,
            url: "http://127.0.0.1:8080/api/v1/slots/search?patient_id=173328158&type=doctor",
            data: {
              items: [
                {
                  doctor_name: "Weber Julia",
                  clinic_name: "Family Health Pankow",
                  start: "2026-03-12T12:40:00",
                },
              ],
              _total: 5,
            },
          }),
        },
      ],
    } as AgentMessage);

    const toolResult = getPersistedToolResult(sm);
    const text = toolResult.content[0].text as string;
    expect(text).toContain("fh_api ok slots/search: items=5");
    expect(text).toContain("doctor#4 | Weber Julia | clinic#3 | Family Health Pankow | 2026-03-12T12:40:00 | free");
    expect(text).not.toContain("\"doctor_name\"");
  });

  it("preserves booking-critical ids in doctors summaries", () => {
    const summarized = summarizeFhApiToolResultMessage({
      role: "toolResult",
      toolCallId: "call_fh",
      toolName: "fh_api",
      isError: false,
      content: [
        {
          type: "text",
          text: JSON.stringify({
            ok: true,
            status: 200,
            url: "http://127.0.0.1:8080/api/v1/doctors?clinic_id=1&direction_id=2",
            data: [
              {
                id: 3,
                first_name: "Peter",
                last_name: "Koch",
                clinic_id: 1,
                clinic_name: "Family Health Mitte",
                directions: [{ id: 2, name: "Cardiologist" }],
              },
              {
                id: 2,
                first_name: "Anna",
                last_name: "Schmidt",
                clinic_id: 1,
                clinic_name: "Family Health Mitte",
                directions: [{ id: 2, name: "Cardiologist" }],
              },
            ],
          }),
        },
      ],
    } as AgentMessage);

    const text = ((summarized as { content: Array<{ text: string }> }).content[0] ?? {}).text;
    expect(text).toContain("fh_api ok doctors: items=2");
    expect(text).toContain("#3 | Koch Peter | clinic#1 | Family Health Mitte | Cardiologist");
    expect(text).toContain("#2 | Schmidt Anna | clinic#1 | Family Health Mitte | Cardiologist");
  });

  it("preserves booking-critical ids in slots summaries", () => {
    const summarized = summarizeFhApiToolResultMessage({
      role: "toolResult",
      toolCallId: "call_fh",
      toolName: "fh_api",
      isError: false,
      content: [
        {
          type: "text",
          text: JSON.stringify({
            ok: true,
            status: 200,
            url: "http://127.0.0.1:8080/api/v1/slots/search?patient_id=173328158&type=doctor&doctor_id=3",
            data: {
              items: [
                {
                  doctor_id: 3,
                  doctor_name: "Koch Peter",
                  clinic_id: 1,
                  clinic_name: "Family Health Mitte",
                  start: "2026-03-13T11:00:00",
                  is_free: true,
                },
                {
                  doctor_id: 2,
                  doctor_name: "Schmidt Anna",
                  clinic_id: 1,
                  clinic_name: "Family Health Mitte",
                  start: "2026-03-13T10:00:00",
                  is_free: true,
                },
              ],
              _total: 2,
            },
          }),
        },
      ],
    } as AgentMessage);

    const text = ((summarized as { content: Array<{ text: string }> }).content[0] ?? {}).text;
    expect(text).toContain("fh_api ok slots/search: items=2");
    expect(text).toContain("doctor#3 | Koch Peter | clinic#1 | Family Health Mitte | 2026-03-13T11:00:00 | free");
    expect(text).toContain("doctor#2 | Schmidt Anna | clinic#1 | Family Health Mitte | 2026-03-13T10:00:00 | free");
  });
});

describe("before_message_write hook", () => {
  it("continues persistence when a before_message_write hook throws", () => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "openclaw-before-write-"));
    process.env.OPENCLAW_BUNDLED_PLUGINS_DIR = "/nonexistent/bundled/plugins";

    const plugin = writeTempPlugin({
      dir: tmp,
      id: "before-write-throws",
      body: `export default { id: "before-write-throws", register(api) {
  api.on("before_message_write", () => {
    throw new Error("boom");
  }, { priority: 10 });
} };`,
    });

    const registry = loadOpenClawPlugins({
      cache: false,
      workspaceDir: tmp,
      config: {
        plugins: {
          load: { paths: [plugin] },
          allow: ["before-write-throws"],
        },
      },
    });
    initializeGlobalHookRunner(registry);

    const sm = guardSessionManager(SessionManager.inMemory(), {
      agentId: "main",
      sessionKey: "main",
    });
    const appendMessage = sm.appendMessage.bind(sm) as unknown as (message: AgentMessage) => void;
    appendMessage({
      role: "user",
      content: "hello",
      timestamp: Date.now(),
    } as AgentMessage);

    const messages = sm
      .getEntries()
      .filter((e) => e.type === "message")
      .map((e) => (e as { message: AgentMessage }).message);

    expect(messages).toHaveLength(1);
    expect(messages[0]?.role).toBe("user");
  });
});
