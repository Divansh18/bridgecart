import assert from "node:assert/strict";
import test from "node:test";
import { ApiError } from "../../lib/api";
import { attemptLogout } from "./logout";

test("confirmed server logout clears authenticated state", async () => {
  const outcome = await attemptLogout(async () => undefined);
  assert.deepEqual(outcome, { confirmed: true });
});

test("expired session is treated as confirmed logout", async () => {
  const outcome = await attemptLogout(async () => {
    throw new ApiError(401, "Authentication required");
  });
  assert.deepEqual(outcome, { confirmed: true });
});

test("network or server failures keep authenticated state and allow retry", async () => {
  for (const status of [0, 500]) {
    const outcome = await attemptLogout(async () => {
      throw new ApiError(status, "unavailable");
    });
    assert.equal(outcome.confirmed, false);
    if (!outcome.confirmed)
      assert.match(outcome.message, /session may still be active.*Retry/);
  }
});
