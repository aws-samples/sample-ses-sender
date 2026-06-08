import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";

const url = process.env.MCP_URL || "http://localhost:8808/mcp";

async function main() {
  const transport = new StreamableHTTPClientTransport(new URL(url));
  const client = new Client({ name: "test-client", version: "1.0" });
  await client.connect(transport);
  console.log("Connected!");

  const tools = await client.listTools();
  console.log(`Tools: ${tools.tools.map(t => t.name).join(", ")}`);

  console.log("\n=== Login ===");
  const login = await client.callTool({ name: "ses", arguments: { action: "login", params: '{"username":"admin","password":"admin123"}' } });
  console.log(login.content[0].text);

  console.log("\n=== Quota ===");
  const quota = await client.callTool({ name: "ses", arguments: { action: "quota" } });
  console.log(quota.content[0].text);

  console.log("\n=== Dashboard ===");
  const dash = await client.callTool({ name: "ses", arguments: { action: "dashboard" } });
  const d = JSON.parse(dash.content[0].text);
  console.log(`今日: ${d.summary.today_sent}/${d.summary.daily_limit} | 本月: ${d.summary.month_sent} | 总计: ${d.summary.total_emails}`);

  await client.close();
  console.log("\nDone!");
}

main().catch(e => { console.error(e.message); process.exit(1); });
