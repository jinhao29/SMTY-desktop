#!/usr/bin/env node

/**
 * GLM-4.6v-Flash MCP Server (Skill 内部)
 *
 * 提供 chat、vision、tool 等能力
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

const API_KEY = process.argv[2] || process.env.ZHIPU_API_KEY;
const MODEL = process.env.MODEL || "glm-4.6v-flash";
const API_ENDPOINT = "https://open.bigmodel.cn/api/paas/v4/chat/completions";

if (!API_KEY) {
  console.error("错误：请设置环境变量 ZHIPU_API_KEY");
  console.error("用法：node mcp-server.js YOUR_API_KEY");
  process.exit(1);
}

const server = new Server(
  {
    name: "glm-4-6v-flash",
    version: "1.0.0",
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

const TOOLS = [
  {
    name: "chat",
    description: "文本对话",
    inputSchema: {
      type: "object",
      properties: {
        messages: {
          type: "array",
          items: {
            type: "object",
            properties: {
              role: { type: "string", enum: ["user", "assistant", "system"] },
              content: { type: "string" },
            },
            required: ["role", "content"],
          },
        },
        stream: { type: "boolean", default: false },
        thinking: { type: "object", properties: { type: { type: "string", enum: ["enabled", "disabled"] } } },
      },
      required: ["messages"],
    },
  },
  {
    name: "vision",
    description: "多模态理解（图片/视频/文件）",
    inputSchema: {
      type: "object",
      properties: {
        messages: {
          type: "array",
          items: {
            type: "object",
            properties: {
              role: { type: "string", enum: ["user", "assistant", "system"] },
              content: {
                type: "array",
                items: {
                  type: "object",
                  properties: {
                    type: { type: "string", enum: ["image_url", "video_url", "file_url", "text"] },
                    image_url: { type: "object", properties: { url: { type: "string" } } },
                    video_url: { type: "object", properties: { url: { type: "string" } } },
                    file_url: { type: "object", properties: { url: { type: "string" } } },
                    text: { type: "string" },
                  },
                },
              },
            },
            required: ["role", "content"],
          },
        },
        thinking: { type: "object", properties: { type: { type: "string", enum: ["enabled", "disabled"] } } },
      },
      required: ["messages"],
    },
  },
];

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: TOOLS,
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    switch (name) {
      case "chat": {
        const { messages, stream = false, thinking = { type: "disabled" } } = args;

        if (stream) {
          const response = await fetch(API_ENDPOINT, {
            method: "POST",
            headers: {
              "Authorization": `Bearer ${API_KEY}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              model: MODEL,
              messages,
              stream: true,
              thinking,
            }),
          });

          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let fullText = "";

          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value);
            const lines = chunk.split("\n");

            for (const line of lines) {
              if (line.startsWith("data: ")) {
                const data = line.slice(6);
                if (data === "[DONE]") continue;

                try {
                  const parsed = JSON.parse(data);
                  const content = parsed.choices?.[0]?.delta?.content;
                  if (content) {
                    fullText += content;
                  }
                } catch (e) {}
              }
            }
          }

          return {
            content: [{ type: "text", text: fullText }],
          };
        } else {
          const response = await fetch(API_ENDPOINT, {
            method: "POST",
            headers: {
              "Authorization": `Bearer ${API_KEY}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              model: MODEL,
              messages,
              thinking,
            }),
          });

          if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`API 错误 (${response.status}): ${errorText}`);
          }

          const data = await response.json();
          const content = data.choices?.[0]?.message?.content || "";

          return {
            content: [{ type: "text", text: content }],
          };
        }
      }

      case "vision": {
        const { messages, thinking = { type: "disabled" } } = args;

        const response = await fetch(API_ENDPOINT, {
          method: "POST",
          headers: {
            "Authorization": `Bearer ${API_KEY}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            model: MODEL,
            messages,
            thinking,
          }),
        });

        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(`API 错误 (${response.status}): ${errorText}`);
        }

        const data = await response.json();
        const content = data.choices?.[0]?.message?.content || "";

        return {
          content: [{ type: "text", text: content }],
        };
      }

      default:
        throw new Error(`未知工具: ${name}`);
    }
  } catch (error) {
    return {
      content: [{ type: "text", text: `错误: ${error.message}` }],
      isError: true,
    };
  }
});

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("GLM-4.6v-Flash MCP Server 已启动");
}

main().catch((error) => {
  console.error("服务器启动失败:", error);
  process.exit(1);
});
