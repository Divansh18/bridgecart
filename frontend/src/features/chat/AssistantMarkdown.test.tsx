import assert from "node:assert/strict";
import { test } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import { AssistantMarkdown } from "./AssistantMarkdown";
import { safeMarkdownUrl } from "./safeMarkdownUrl";

test("renders GFM, code, and safe links without executing HTML", () => {
  const content = [
    "**Order summary**",
    "",
    "| Item | Price |",
    "| --- | ---: |",
    "| Mug | ₹499 |",
    "",
    "- Processing",
    "- Cash on delivery",
    "",
    "```text",
    "order #21",
    "```",
    "",
    "[Store](http://shop.bridgecart.local:8088/shop/) [unsafe](javascript:alert(1))",
    "",
    '<script>alert("bad")</script><img src=x onerror=alert(1)>',
  ].join("\n");
  const html = renderToStaticMarkup(<AssistantMarkdown content={content} />);
  assert.match(html, /<strong>Order summary<\/strong>/);
  assert.match(html, /<table[^>]*>/);
  assert.match(html, /<th[^>]*>Item<\/th>/);
  assert.match(html, /<td[^>]*>₹499<\/td>/);
  assert.match(html, /<li[^>]*>Processing<\/li>/);
  assert.match(html, /<pre[^>]*>/);
  assert.match(html, /order #21/);
  assert.match(html, /href="http:\/\/shop\.bridgecart\.local:8088\/shop\/"/);
  assert.match(html, /rel="noopener noreferrer"/);
  assert.match(html, /overflow-x-auto/);
  assert.doesNotMatch(html, /javascript:|<script|<img|onerror=/i);
});

test("rejects unsafe URL schemes and credential-bearing links", () => {
  for (const value of [
    "javascript:alert(1)",
    "data:text/html,hello",
    "file:///etc/passwd",
    "//unexpected.example/path",
    "https://user:password@example.com/",
    "relative/path",
  ]) {
    assert.equal(safeMarkdownUrl(value), "");
  }
  assert.equal(
    safeMarkdownUrl(" https://example.com/order/21 "),
    "https://example.com/order/21",
  );
});
