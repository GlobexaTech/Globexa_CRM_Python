import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { fixture, loginUI } from "./coreFixtures";

const sizes = [
  { width: 1440, height: 900 },
  { width: 1280, height: 800 },
  { width: 768, height: 1024 },
  { width: 390, height: 844 },
];
const routes: {
  path: string;
  heading: string | RegExp;
  endpoint?: string;
  id?: string;
}[] = [
  {
    path: "/",
    heading: /Your business/,
    endpoint: "/operations/analytics/dashboard",
  },
  {
    path: "/leads",
    heading: "Leads",
    endpoint: "/leads",
    id: fixture.records.tenantA.lead,
  },
  {
    path: "/contacts",
    heading: "Contacts",
    endpoint: "/contacts",
    id: fixture.records.tenantA.contact,
  },
  {
    path: "/companies",
    heading: "Companies",
    endpoint: "/companies",
    id: fixture.records.tenantA.company,
  },
  {
    path: "/pipeline",
    heading: "Deal Pipeline",
    endpoint: "/deals",
    id: fixture.records.tenantA.deal,
  },
  {
    path: "/tasks",
    heading: "Tasks",
    endpoint: "/tasks",
    id: fixture.records.tenantA.task,
  },
  {
    path: "/conversations",
    heading: "Conversations",
    endpoint: "/operations/conversations",
    id: fixture.records.tenantA.conversation,
  },
  {
    path: "/campaigns",
    heading: "Campaigns",
    endpoint: "/campaigns",
    id: fixture.records.tenantA.campaign,
  },
  {
    path: "/automations",
    heading: "Automations",
    endpoint: "/operations/workflows",
  },
  {
    path: "/integrations",
    heading: "Integrations",
    endpoint: "/operations/providers",
  },
  {
    path: "/ai-agents",
    heading: "Controlled AI",
    endpoint: "/operations/jobs",
  },
  {
    path: "/analytics",
    heading: "Analytics",
    endpoint: "/operations/analytics/dashboard",
  },
  { path: "/search", heading: "Global search" },
  { path: "/settings", heading: "Settings", endpoint: "/auth/me" },
  { path: "/help", heading: "Workspace help" },
  {
    path: `/customers/leads/${fixture.records.tenantA.lead}`,
    heading: fixture.records.tenantA.leadTitle,
    endpoint: `/operations/customers/leads/${fixture.records.tenantA.lead}`,
  },
];
async function checkAxe(page: Page) {
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  await test.info().attach(`axe-check-${test.info().attachments.length + 1}`, {
    body: JSON.stringify({ url: page.url(), violations: result.violations }),
    contentType: "application/json",
  });
  expect(
    result.violations.filter((v) =>
      ["critical", "serious"].includes(v.impact ?? ""),
    ),
  ).toEqual([]);
  return result;
}

for (const size of sizes) {
  test(`responsive routes and WCAG checks at ${size.width}x${size.height}`, async ({
    page,
  }, testInfo) => {
    test.setTimeout(240000);
    await page.setViewportSize(size);
    await loginUI(page);
    for (const route of routes) {
      const { path } = route;
      await test.step(path, async () => {
        const responsePromise = route.endpoint
          ? page.waitForResponse(
              (response) =>
                response.request().method() === "GET" &&
                new URL(response.url()).pathname ===
                  `/api/crm${route.endpoint}`,
            )
          : null;
        await page.goto(path);
        await expect(page.locator(".session-state")).toHaveCount(0);
        await expect(
          page.getByRole("heading", {
            level: 1,
            name: route.heading,
            exact: typeof route.heading === "string",
          }),
        ).toBeVisible();
        if (responsePromise) {
          const response = await responsePromise;
          expect(
            response.ok(),
            `${path} real backend response ${response.status()}`,
          ).toBe(true);
          const data = await response.json();
          if (route.id)
            expect(
              data.items.map((row: { id: string }) => row.id),
              `${path} seeded record loaded`,
            ).toContain(route.id);
        }
        if (path === "/search") {
          const response = page.waitForResponse(
            (r) =>
              r.request().method() === "GET" &&
              new URL(r.url()).pathname === "/api/crm/operations/search",
          );
          await page
            .getByRole("searchbox", { name: "Search CRM", exact: true })
            .fill("Alpha");
          await page
            .getByRole("button", { name: "Search", exact: true })
            .click();
          expect((await response).ok()).toBe(true);
          await expect(
            page.getByRole("button", {
              name: fixture.records.tenantA.leadTitle,
              exact: true,
            }),
          ).toBeVisible();
        }
        await expect(
          page.getByText("Loading workspace data…", { exact: true }),
        ).toHaveCount(0);
        await expect(
          page.getByRole("alert").filter({ hasText: /\S/ }),
        ).toHaveCount(0);
        const name = path === "/" ? "dashboard" : path.split("/")[1];
        await page.screenshot({
          path: testInfo.outputPath(`${name}-${size.width}.png`),
          fullPage: true,
          animations: "disabled",
        });
        expect(
          await page.evaluate(
            () => document.documentElement.scrollWidth - window.innerWidth,
          ),
          `${path} viewport overflow`,
        ).toBeLessThanOrEqual(1);
        const bounds = await page
          .locator("main > section")
          .first()
          .evaluate((node) => {
            const box = node.getBoundingClientRect();
            return {
              left: box.left,
              right: box.right,
              width: box.width,
              viewport: innerWidth,
            };
          });
        expect(
          bounds.left,
          `${path} content starts inside viewport`,
        ).toBeGreaterThanOrEqual(-1);
        expect(
          bounds.right,
          `${path} content is not clipped by body overflow:hidden`,
        ).toBeLessThanOrEqual(bounds.viewport + 1);
        expect(
          bounds.width,
          `${path} usable content width`,
        ).toBeGreaterThanOrEqual(Math.min(280, size.width - 32));
        const clipped = await page.evaluate(() =>
          Array.from(
            document.querySelectorAll<HTMLElement>(
              "button,input,select,textarea",
            ),
          )
            .filter((node) => {
              if (!node.getClientRects().length) return false;
              const box = node.getBoundingClientRect();
              if (
                box.width === 0 ||
                (box.right <= innerWidth + 1 && box.left >= -1)
              )
                return false;
              for (
                let parent = node.parentElement;
                parent && parent !== document.body;
                parent = parent.parentElement
              ) {
                if (
                  ["auto", "scroll"].includes(
                    getComputedStyle(parent).overflowX,
                  ) &&
                  parent.scrollWidth > parent.clientWidth + 1
                ) {
                  const container = parent.getBoundingClientRect();
                  return (
                    container.left < -1 || container.right > innerWidth + 1
                  );
                }
              }
              return true;
            })
            .map(
              (node) =>
                node.getAttribute("aria-label") ||
                node.textContent?.trim().slice(0, 60) ||
                node.tagName,
            ),
        );
        expect(
          clipped,
          `${path} controls outside viewport without an accessible scrolling container`,
        ).toEqual([]);
        await checkAxe(page);
      });
    }
    if (size.width < 1024) {
      await page
        .getByRole("button", { name: "Open navigation", exact: true })
        .click();
      const nav = page.getByRole("dialog", { name: "Navigation", exact: true });
      await expect(nav).toBeVisible();
      await checkAxe(page);
      await nav.getByRole("link", { name: "Leads", exact: true }).click();
      await expect(nav).not.toBeVisible();
      await expect(
        page.getByRole("heading", { level: 1, name: "Leads", exact: true }),
      ).toBeVisible();
    }
  });
}

for (const size of [sizes[0], sizes[3]]) {
  test(`lead drawer, forms, focus and Escape at ${size.width}px`, async ({
    page,
  }, testInfo) => {
    test.setTimeout(90000);
    await page.setViewportSize(size);
    await loginUI(page);
    await page.goto("/leads");
    const trigger = page.getByRole("button", {
      name: fixture.records.tenantA.leadTitle,
      exact: true,
    });
    await trigger.click();
    const drawer = page.getByRole("dialog", {
      name: fixture.records.tenantA.leadTitle,
      exact: true,
    });
    await expect(drawer).toBeVisible();
    await expect(
      drawer.getByText("Loading workspace data…", { exact: true }),
    ).toHaveCount(0);
    await expect(
      drawer.getByRole("button", { name: "Create Task", exact: true }),
    ).toBeVisible();
    await expect(
      drawer.getByRole("button", { name: "Close lead profile", exact: true }),
    ).toBeFocused();
    await page.keyboard.press("Shift+Tab");
    expect(
      await drawer.evaluate((node) => node.contains(document.activeElement)),
    ).toBe(true);
    await checkAxe(page);
    await page.screenshot({
      path: testInfo.outputPath(`lead-drawer-${size.width}.png`),
      fullPage: true,
      animations: "disabled",
    });
    await drawer
      .getByRole("button", { name: "Create Task", exact: true })
      .click();
    const task = page.getByRole("dialog", { name: "Create task", exact: true });
    await expect(task).toBeVisible();
    await task
      .getByLabel("Task title", { exact: true })
      .fill("Keyboard accessible task form");
    await checkAxe(page);
    await page.keyboard.press("Escape");
    await expect(task).not.toBeVisible();
    await expect(
      drawer.getByRole("button", { name: "Create Task", exact: true }),
    ).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(drawer).not.toBeVisible();
    await expect(trigger).toBeFocused();
    await trigger.click();
    await drawer
      .getByRole("button", { name: "Edit lead", exact: true })
      .click();
    const edit = page.getByRole("dialog", { name: "Edit lead", exact: true });
    await edit
      .getByLabel("Lead title", { exact: true })
      .fill(fixture.records.tenantA.leadTitle);
    await checkAxe(page);
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
    if (size.width > 480) {
      await trigger.click();
      await page.mouse.click(10, 200);
      await expect(drawer).not.toBeVisible();
      await expect(trigger).toBeFocused();
    }
    for (const [route, name] of [
      ["/contacts", "New Contact"],
      ["/companies", "New Company"],
      ["/tasks", "New Task"],
      ["/pipeline", "New Deal"],
    ]) {
      await page.goto(route);
      await page.getByRole("button", { name, exact: true }).click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await checkAxe(page);
      expect(
        await page
          .getByRole("dialog")
          .evaluate((node) => node.scrollWidth > node.clientWidth + 1),
        `${name} dialog overflow`,
      ).toBe(false);
      await page.keyboard.press("Escape");
      await expect(page.getByRole("dialog")).not.toBeVisible();
    }
  });
}

test("reduced motion disables decorative motion and production logo loads", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await loginUI(page);
  await page.goto("/");
  await expect(page.locator(".session-state")).toHaveCount(0);
  await expect(
    page.getByRole("heading", { level: 1, name: /Your business/ }),
  ).toBeVisible();
  await expect(page.locator(".crm-hero")).toBeVisible();
  await expect(
    page.getByText("Loading workspace data…", { exact: true }),
  ).toHaveCount(0);
  const logo = await page.request.get("/Globexa-Logo.jpg");
  expect(logo.ok()).toBe(true);
  expect(logo.headers()["content-type"]).toContain("image/");
  expect(
    await page.evaluate(() => getComputedStyle(document.body).scrollBehavior),
  ).not.toBe("smooth");
  const animations = await page.evaluate(() =>
    Array.from(
      document.querySelectorAll("body,main,section,.crm-hero"),
    ).flatMap((node) =>
      ["::before", "::after", null].map(
        (pseudo) => getComputedStyle(node, pseudo).animationName,
      ),
    ),
  );
  expect(animations.every((name) => name === "none")).toBe(true);
});
