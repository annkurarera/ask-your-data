import { expect, test, type Page, type Route } from "@playwright/test";

const schema = {
  table: "loan_portfolio",
  description: "One row per retail loan (synthetic data).",
  as_of_date: "2026-09-30",
  columns: [
    { name: "loan_id", type: "text", description: "Unique loan ID", values: [] },
    { name: "product_type", type: "text", description: "", values: ["Home Loan", "Gold Loan"] },
    { name: "dpd", type: "int", description: "Days past due", values: [] },
  ],
  sample_questions: ["What is our gross NPA % by product?", "Which 10 branches have the highest NPA %?"],
};

const base = {
  query_id: "q1",
  reasoning: "Amount-based gross NPA on the live book.",
  truncated: false,
  attempts: 1,
  latency_ms: 2300,
  cost_usd: 0.0012,
  tokens: 4100,
  steps: [
    { name: "input_guard", status: "ok", ms: 0, detail: "" },
    { name: "generate_sql#1", status: "ok", ms: 1500, detail: "plan" },
    { name: "validate#1", status: "ok", ms: 3, detail: "LIMIT 1000 applied" },
    { name: "execute#1", status: "ok", ms: 210, detail: "2 rows" },
    { name: "summarise", status: "ok", ms: 600, detail: "" },
  ],
};

const barAnswer = {
  ...base,
  status: "answered",
  answer: "Business Loans have the highest gross NPA at 5.91%.",
  sql: "SELECT product_type, gross_npa_pct FROM loan_portfolio LIMIT 1000",
  columns: ["product_type", "gross_npa_pct"],
  rows: [["Business Loan", 5.91], ["Home Loan", 0.73]],
  row_count: 2,
  chart: { type: "bar", x: "product_type", y: ["gross_npa_pct"] },
};

const kpiAnswer = {
  ...base,
  query_id: "q2",
  status: "answered",
  answer: "The live loan book is ₹70,955 crore.",
  sql: "SELECT SUM(outstanding_principal) AS loan_book FROM loan_portfolio LIMIT 1000",
  columns: ["loan_book"],
  rows: [[709546803231.32]],
  row_count: 1,
  chart: { type: "kpi", y: ["loan_book"] },
};

const refused = {
  ...base,
  query_id: "q3",
  status: "refused",
  answer: "I can only answer read-only questions about the loan portfolio.",
  reasoning: "",
  sql: null,
  columns: [],
  rows: [],
  row_count: 0,
  chart: { type: "table" },
  steps: [{ name: "input_guard", status: "ok", ms: 0, detail: "" }],
};

async function mockApi(page: Page, answers: Record<string, object>, calls: { ask: any[]; feedback: any[] }) {
  await page.route("**/api/schema", (r) => r.fulfill({ json: schema }));
  await page.route("**/api/health", (r) => r.fulfill({ json: { status: "ok", database: true, model: "gpt-4.1-mini" } }));
  await page.route("**/api/ask", async (route: Route) => {
    const body = route.request().postDataJSON();
    calls.ask.push(body);
    const answer = answers[body.question];
    if (!answer) return route.fulfill({ status: 429, json: { detail: "Too many questions. Please wait a minute." } });
    await new Promise((r) => setTimeout(r, 150));
    return route.fulfill({ json: answer });
  });
  await page.route("**/api/feedback", (route) => {
    calls.feedback.push(route.request().postDataJSON());
    return route.fulfill({ json: { ok: true } });
  });
}

test("shows a waking-up message while the server starts", async ({ page }) => {
  let healthCalls = 0;
  await page.route("**/api/schema", (r) => r.fulfill({ json: schema }));
  await page.route("**/api/health", async (r) => {
    healthCalls++;
    if (healthCalls === 1) {
      await new Promise((res) => setTimeout(res, 4000)); // first call hangs like a sleeping server
      return r.abort();
    }
    return r.fulfill({ json: { status: "ok", database: true, model: "gpt-4.1-mini" } });
  });
  await page.goto("/");
  await expect(page.getByTestId("waking")).toBeVisible();
  await expect(page.getByText("Database connected")).toBeAttached({ timeout: 15000 });
  await expect(page.getByTestId("waking")).toHaveCount(0);
});

test.describe("Ask Your Data", () => {
  let calls: { ask: any[]; feedback: any[] };

  test.beforeEach(async ({ page }) => {
    calls = { ask: [], feedback: [] };
    await mockApi(
      page,
      {
        "What is our gross NPA % by product?": barAnswer,
        "What is the total loan book?": kpiAnswer,
        "Delete all closed loans": refused,
      },
      calls,
    );
    await page.goto("/");
  });

  test("shows the empty state with starter questions", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Ask Your Data" })).toBeVisible();
    await expect(page.getByRole("button", { name: "What is our gross NPA % by product?" }).first()).toBeVisible();
  });

  test("answers a question with chart, table, SQL and steps", async ({ page }) => {
    await page.getByLabel("Your question").fill("What is our gross NPA % by product?");
    await page.keyboard.press("Enter");

    await expect(page.getByTestId("answer")).toHaveText(/Business Loans have the highest gross NPA/);
    await expect(page.getByTestId("chart-bar")).toBeVisible();
    const table = page.getByTestId("results-table");
    await expect(table).toContainText("Gross NPA %");
    await expect(table).toContainText("5.91%");

    await page.getByRole("button", { name: "Show SQL" }).click();
    await expect(page.getByTestId("sql")).toContainText("SELECT product_type");

    await page.getByRole("button", { name: "How it was answered" }).click();
    await expect(page.getByTestId("steps")).toContainText("Checked SQL is read-only");
    await expect(page.getByText("2.3 s")).toBeVisible();
  });

  test("clicking a starter question asks it", async ({ page }) => {
    await page.getByRole("button", { name: "What is our gross NPA % by product?" }).last().click();
    await expect(page.getByTestId("answer")).toBeVisible();
    expect(calls.ask[0].question).toBe("What is our gross NPA % by product?");
  });

  test("shows a single number as a KPI in Indian units", async ({ page }) => {
    await page.getByLabel("Your question").fill("What is the total loan book?");
    await page.getByRole("button", { name: "Ask", exact: true }).click();
    await expect(page.getByTestId("kpi")).toContainText("₹70,955 Cr");
    await expect(page.getByTestId("results-table")).toHaveCount(0);
  });

  test("formats counts without ₹ and large money in crore", async ({ page }) => {
    await page.unroute("**/api/ask");
    await page.route("**/api/ask", (route) => {
      const q = route.request().postDataJSON().question as string;
      const count = q.includes("last month");
      return route.fulfill({
        json: {
          ...kpiAnswer,
          answer: "ok",
          columns: [count ? "loans_disbursed_september_2026" : "disbursement_volume_q2_2026"],
          rows: [[count ? 21308 : 67500036000]],
          chart: { type: "kpi", y: [count ? "loans_disbursed_september_2026" : "disbursement_volume_q2_2026"] },
        },
      });
    });
    const input = page.getByLabel("Your question");
    await input.fill("How many loans were disbursed last month?");
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("kpi").last()).toContainText("21,308");
    await expect(page.getByTestId("kpi").last()).not.toContainText("₹");

    await input.fill("Q2 disbursements this year");
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("kpi").last()).toContainText("₹6,750 Cr");
  });

  test("shows the true total when results are capped", async ({ page }) => {
    await page.unroute("**/api/ask");
    await page.route("**/api/ask", (route) =>
      route.fulfill({
        json: {
          ...barAnswer,
          answer: "24,713 loans have no EMI paid.",
          columns: ["loan_id", "emi_amount", "emis_paid"],
          rows: Array.from({ length: 1000 }, (_, i) => [`LN${i}`, 1000 + i, 0]),
          row_count: 1000,
          truncated: true,
          total_rows: 24713,
          chart: { type: "table" },
        },
      }),
    );
    await page.getByLabel("Your question").fill("Which customers did not pay their EMI?");
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("truncated-note")).toContainText("first 1,000 of 24,713 matching rows");
    const firstRow = page.getByTestId("results-table").locator("tbody tr").first();
    await expect(firstRow.locator("td").nth(2)).toHaveText("0"); // EMIs paid is a count, not ₹0
    await expect(firstRow.locator("td").nth(1)).toHaveText("₹1,000"); // EMI amount is money
  });

  test("stamps declined questions and hides answer-only tools", async ({ page }) => {
    await page.getByLabel("Your question").fill("Delete all closed loans");
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("stamp")).toHaveText("Declined");
    await expect(page.getByRole("button", { name: "Show SQL" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Answer was right" })).toHaveCount(0);
  });

  test("sends earlier answers as context for follow-ups", async ({ page }) => {
    const input = page.getByLabel("Your question");
    await input.fill("What is our gross NPA % by product?");
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("answer")).toBeVisible();
    await input.fill("What is the total loan book?");
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("kpi")).toBeVisible();
    expect(calls.ask[1].history).toEqual([{ question: "What is our gross NPA % by product?", sql: barAnswer.sql }]);
  });

  test("records thumbs-up feedback once", async ({ page }) => {
    await page.getByLabel("Your question").fill("What is our gross NPA % by product?");
    await page.keyboard.press("Enter");
    await page.getByRole("button", { name: "Answer was right" }).click();
    await expect(page.getByText("Feedback saved")).toBeVisible();
    await expect(page.getByRole("button", { name: "Answer was wrong" })).toBeDisabled();
    expect(calls.feedback).toEqual([{ query_id: "q1", rating: 1 }]);
  });

  test("shows API errors with a way to retry", async ({ page }) => {
    await page.getByLabel("Your question").fill("Something unmocked");
    await page.keyboard.press("Enter");
    await expect(page.locator(".card-error")).toContainText("Too many questions");
    await expect(page.getByRole("button", { name: "Ask again" })).toBeVisible();
  });

  test("does not submit an empty question", async ({ page }) => {
    await expect(page.getByRole("button", { name: "Ask", exact: true })).toBeDisabled();
    await page.getByLabel("Your question").press("Enter");
    expect(calls.ask).toHaveLength(0);
  });
});
